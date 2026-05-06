"""虚拟撮合引擎。"""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from cep.core.event_bus import EventBus
from cep.core.events import (
    BarEvent,
    OrderEvent,
    OrderSide,
    OrderStatus,
    OrderType,
    SignalEvent,
    SignalType,
    TickEvent,
    TradeEvent,
)
from .portfolio import PortfolioLedger
from .rules import get_margin_rate, calculate_commission

ExecutionTiming = Literal["current_bar", "next_bar"]


@dataclass(frozen=True)
class PendingSignalExecution:
    """Queue a signal until the next market event for the same symbol."""

    signal: SignalEvent
    side: OrderSide
    quantity: float


def _validate_execution_timing(execution_timing: str) -> ExecutionTiming:
    if execution_timing not in {"current_bar", "next_bar"}:
        raise ValueError(
            f"Unsupported execution_timing: {execution_timing}. "
            "Expected 'current_bar' or 'next_bar'."
        )
    return execution_timing  # type: ignore[return-value]


class SimulatedBroker:
    """将交易信号转换为订单与成交事件。"""

    def __init__(
        self,
        event_bus: EventBus,
        portfolio: PortfolioLedger,
        default_quantity: float = 1.0,
        commission_rate: float = 0.0,
        contract_multipliers: dict[str, float] | None = None,
        execution_timing: ExecutionTiming = "next_bar",
    ) -> None:
        self.event_bus = event_bus
        self.portfolio = portfolio
        self.default_quantity = default_quantity
        self.commission_rate = commission_rate
        self.contract_multipliers = contract_multipliers or {}
        self.execution_timing = _validate_execution_timing(execution_timing)
        self._latest_prices: dict[str, float] = {}
        self._pending_signals: dict[str, list[PendingSignalExecution]] = {}

        self.event_bus.subscribe(BarEvent, self.on_bar)
        self.event_bus.subscribe(TickEvent, self.on_tick)
        self.event_bus.subscribe(SignalEvent, self.on_signal)

    def on_bar(self, event: BarEvent) -> None:
        if self.execution_timing == "next_bar":
            self._flush_pending_for_market_event(event, execution_price=event.open)
        self._latest_prices[event.symbol] = event.close

    def on_tick(self, event: TickEvent) -> None:
        if self.execution_timing == "next_bar":
            self._flush_pending_for_market_event(event, execution_price=event.last_price)
        self._latest_prices[event.symbol] = event.last_price

    def on_signal(self, signal: SignalEvent) -> None:
        """将交易信号转换为订单事件和成交事件。"""
        if signal.signal_type != SignalType.TRADE_OPPORTUNITY:
            return

        side_text = str(signal.payload.get("side", OrderSide.BUY.value)).upper()
        order_id = str(uuid.uuid4())
        if side_text not in {OrderSide.BUY.value, OrderSide.SELL.value}:
            self._publish_rejected_order(
                order_id=order_id,
                signal=signal,
                side=OrderSide.BUY,
                quantity=0.0,
                price=0.0,
                reason="invalid_side",
                details={"side": side_text},
            )
            return

        side = OrderSide(side_text)
        quantity = float(signal.payload.get("quantity", self.default_quantity))
        if not math.isfinite(quantity) or quantity <= 0:
            self._publish_rejected_order(
                order_id=order_id,
                signal=signal,
                side=side,
                quantity=quantity,
                price=0.0,
                reason="invalid_quantity_or_price",
            )
            return

        if self.execution_timing == "next_bar":
            pending = PendingSignalExecution(signal=signal, side=side, quantity=quantity)
            self._pending_signals.setdefault(signal.symbol, []).append(pending)
            return

        signal_price = signal.payload.get("price", signal.payload.get("close"))
        price = float(
            signal_price
            if signal_price is not None
            else self._latest_prices.get(signal.symbol, 0.0)
        )
        self._execute_signal(signal=signal, side=side, quantity=quantity, price=price)

    def finalize(self) -> None:
        """Reject queued next-bar signals that never received a later bar."""
        for pending_entries in self._pending_signals.values():
            for pending in pending_entries:
                self._publish_rejected_order(
                    order_id=str(uuid.uuid4()),
                    signal=pending.signal,
                    side=pending.side,
                    quantity=pending.quantity,
                    price=0.0,
                    reason="no_next_bar",
                )
        self._pending_signals.clear()

    def _flush_pending_for_market_event(
        self,
        event: BarEvent | TickEvent,
        *,
        execution_price: float,
    ) -> None:
        pending_entries = self._pending_signals.get(event.symbol)
        if not pending_entries:
            return

        ready_entries = [
            pending for pending in pending_entries if event.timestamp > pending.signal.timestamp
        ]
        if not ready_entries:
            return

        self._pending_signals[event.symbol] = [
            pending for pending in pending_entries if event.timestamp <= pending.signal.timestamp
        ]
        if not self._pending_signals[event.symbol]:
            self._pending_signals.pop(event.symbol, None)

        for pending in ready_entries:
            self._execute_signal(
                signal=pending.signal,
                side=pending.side,
                quantity=pending.quantity,
                price=execution_price,
                execution_timestamp=event.timestamp,
            )

    def _execute_signal(
        self,
        *,
        signal: SignalEvent,
        side: OrderSide,
        quantity: float,
        price: float,
        execution_timestamp: datetime | None = None,
    ) -> None:
        timestamp = execution_timestamp or signal.timestamp
        order_id = str(uuid.uuid4())
        if not math.isfinite(price) or price <= 0:
            self._publish_rejected_order(
                order_id=order_id,
                signal=signal,
                side=side,
                quantity=quantity,
                price=price,
                reason="invalid_quantity_or_price",
            )
            return

        multiplier = self.contract_multipliers.get(signal.symbol, 1.0)
        margin_rate = get_margin_rate(signal.symbol)
        trade_notional = quantity * price * multiplier
        estimated_commission = calculate_commission(
            signal.symbol, price, quantity, multiplier, self.commission_rate
        )

        position = self.portfolio.positions.get(signal.symbol)
        current_qty = position.quantity if position is not None else 0.0

        if side == OrderSide.BUY:
            if current_qty < 0:
                opening_qty = max(0.0, quantity - abs(current_qty))
            else:
                opening_qty = quantity
        else:
            if current_qty > 0:
                opening_qty = max(0.0, quantity - current_qty)
            else:
                opening_qty = quantity

        required_new_margin = opening_qty * price * multiplier * margin_rate
        required_funds = required_new_margin + estimated_commission

        if self.portfolio.available_funds + 1e-9 < required_funds:
            self._publish_rejected_order(
                order_id=order_id,
                signal=signal,
                side=side,
                quantity=quantity,
                price=price,
                reason="insufficient_cash",
                details={
                    "required_funds": required_funds,
                    "available_funds": self.portfolio.available_funds,
                    "margin_rate": margin_rate,
                },
            )
            return

        is_stock = signal.symbol.endswith((".SH", ".SZ", ".BJ"))
        if side == OrderSide.SELL and is_stock and quantity > current_qty + 1e-9:
            self._publish_rejected_order(
                order_id=order_id,
                signal=signal,
                side=side,
                quantity=quantity,
                price=price,
                reason="insufficient_position",
                details={
                    "available_quantity": current_qty,
                    "requested_quantity": quantity,
                },
            )
            return

        self.event_bus.publish(
            OrderEvent(
                order_id=order_id,
                symbol=signal.symbol,
                side=side,
                order_type=OrderType.MARKET,
                status=OrderStatus.SUBMITTED,
                quantity=quantity,
                price=price,
                source="SimulatedBroker",
                signal_event_id=signal.event_id,
                timestamp=timestamp,
                payload={
                    "rule_id": signal.rule_id,
                    "signal_source": signal.source,
                    "execution_timing": self.execution_timing,
                },
            )
        )

        commission = estimated_commission
        trade_id = str(uuid.uuid4())
        self.event_bus.publish(
            TradeEvent(
                trade_id=trade_id,
                order_id=order_id,
                symbol=signal.symbol,
                side=side,
                quantity=quantity,
                price=price,
                commission=commission,
                source="SimulatedBroker",
                signal_event_id=signal.event_id,
                timestamp=timestamp,
                payload={
                    "rule_id": signal.rule_id,
                    "signal_source": signal.source,
                    "execution_timing": self.execution_timing,
                },
            )
        )

        self.event_bus.publish(
            OrderEvent(
                order_id=order_id,
                symbol=signal.symbol,
                side=side,
                order_type=OrderType.MARKET,
                status=OrderStatus.FILLED,
                quantity=quantity,
                price=price,
                source="SimulatedBroker",
                signal_event_id=signal.event_id,
                timestamp=timestamp,
                payload={
                    "trade_id": trade_id,
                    "execution_timing": self.execution_timing,
                },
            )
        )

    def _publish_rejected_order(
        self,
        order_id: str,
        signal: SignalEvent,
        side: OrderSide,
        quantity: float,
        price: float,
        reason: str,
        details: dict[str, float | str] | None = None,
    ) -> None:
        payload: dict[str, float | str] = {"reason": reason}
        if details:
            payload.update(details)
        self.event_bus.publish(
            OrderEvent(
                order_id=order_id,
                symbol=signal.symbol,
                side=side,
                order_type=OrderType.MARKET,
                status=OrderStatus.REJECTED,
                quantity=quantity,
                price=price,
                source="SimulatedBroker",
                signal_event_id=signal.event_id,
                timestamp=signal.timestamp,
                payload=payload,
            )
        )
