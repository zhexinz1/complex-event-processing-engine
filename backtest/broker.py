"""虚拟撮合引擎。"""

from __future__ import annotations

import math
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
    quantity: float | None
    target_position_pct: float | None = None


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
        target_asset_size: float | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.portfolio = portfolio
        self.default_quantity = default_quantity
        self.commission_rate = commission_rate
        self.contract_multipliers = contract_multipliers or {}
        self.execution_timing = _validate_execution_timing(execution_timing)
        self.target_asset_size = target_asset_size
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
            self._flush_pending_for_market_event(
                event, execution_price=event.last_price
            )
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
        has_target_position_pct = "target_position_pct" in signal.payload
        target_position_pct = self._parse_target_position_pct(signal)
        if has_target_position_pct and target_position_pct is None:
            return

        if not has_target_position_pct:
            quantity = float(signal.payload.get("quantity", self.default_quantity))
        else:
            quantity = None

        if quantity is not None and (not math.isfinite(quantity) or quantity <= 0):
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
            pending = PendingSignalExecution(
                signal=signal,
                side=side,
                quantity=quantity,
                target_position_pct=target_position_pct,
            )
            self._pending_signals.setdefault(signal.symbol, []).append(pending)
            return

        signal_price = signal.payload.get("price", signal.payload.get("close"))
        price = float(
            signal_price
            if signal_price is not None
            else self._latest_prices.get(signal.symbol, 0.0)
        )
        self._execute_signal(
            signal=signal,
            side=side,
            quantity=quantity,
            target_position_pct=target_position_pct,
            price=price,
        )

    def finalize(self) -> None:
        """Reject queued next-bar signals that never received a later bar."""
        for pending_entries in self._pending_signals.values():
            for pending in pending_entries:
                self._publish_rejected_order(
                    order_id=str(uuid.uuid4()),
                    signal=pending.signal,
                    side=pending.side,
                    quantity=pending.quantity or 0.0,
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
            pending
            for pending in pending_entries
            if event.timestamp > pending.signal.timestamp
        ]
        if not ready_entries:
            return

        self._pending_signals[event.symbol] = [
            pending
            for pending in pending_entries
            if event.timestamp <= pending.signal.timestamp
        ]
        if not self._pending_signals[event.symbol]:
            self._pending_signals.pop(event.symbol, None)

        for pending in ready_entries:
            self._execute_signal(
                signal=pending.signal,
                side=pending.side,
                quantity=pending.quantity,
                target_position_pct=pending.target_position_pct,
                price=execution_price,
                execution_timestamp=event.timestamp,
            )

    def _execute_signal(
        self,
        *,
        signal: SignalEvent,
        side: OrderSide,
        quantity: float | None,
        target_position_pct: float | None,
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
                quantity=quantity or 0.0,
                price=price,
                reason="invalid_quantity_or_price",
            )
            return

        resolved = self._resolve_order_quantity(
            signal=signal,
            side=side,
            requested_quantity=quantity,
            target_position_pct=target_position_pct,
            price=price,
        )
        if resolved is None:
            return
        side, quantity, sizing_payload = resolved

        multiplier = self.contract_multipliers.get(signal.symbol, 1.0)
        margin_rate = get_margin_rate(signal.symbol)
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
                    **sizing_payload,
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
                    **sizing_payload,
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
                    **sizing_payload,
                },
            )
        )

    def _parse_target_position_pct(self, signal: SignalEvent) -> float | None:
        raw_value = signal.payload.get("target_position_pct")
        if raw_value is None:
            return None
        target_position_pct = float(raw_value)
        if (
            not math.isfinite(target_position_pct)
            or target_position_pct < 0
            or target_position_pct > 1
        ):
            self._publish_rejected_order(
                order_id=str(uuid.uuid4()),
                signal=signal,
                side=OrderSide.BUY,
                quantity=0.0,
                price=0.0,
                reason="invalid_target_position_pct",
                details={"target_position_pct": str(raw_value)},
            )
            return None
        return target_position_pct

    def _resolve_order_quantity(
        self,
        *,
        signal: SignalEvent,
        side: OrderSide,
        requested_quantity: float | None,
        target_position_pct: float | None,
        price: float,
    ) -> tuple[OrderSide, float, dict[str, float | str]] | None:
        if target_position_pct is None:
            if requested_quantity is None:
                return side, self.default_quantity, {}
            return side, requested_quantity, {}

        multiplier = self.contract_multipliers.get(signal.symbol, 1.0)
        margin_rate = get_margin_rate(signal.symbol)
        asset_size = self.target_asset_size or self.portfolio.equity
        raw_target_quantity = asset_size * target_position_pct / (
            price * multiplier * margin_rate
        )
        lot_size = self._lot_size(signal.symbol)
        target_quantity = self._round_down_to_lot(raw_target_quantity, lot_size)

        position = self.portfolio.positions.get(signal.symbol)
        current_quantity = position.quantity if position is not None else 0.0
        if side == OrderSide.BUY:
            desired_quantity = max(current_quantity, target_quantity)
        else:
            desired_quantity = min(max(current_quantity, 0.0), target_quantity)

        delta_quantity = desired_quantity - current_quantity
        if abs(delta_quantity) <= 1e-9:
            return None

        resolved_side = OrderSide.BUY if delta_quantity > 0 else OrderSide.SELL
        sizing_payload: dict[str, float | str] = {
            "target_position_pct": target_position_pct,
            "target_asset_size": asset_size,
            "target_quantity": target_quantity,
            "previous_quantity": current_quantity,
            "lot_size": lot_size,
        }
        return resolved_side, abs(delta_quantity), sizing_payload

    def _lot_size(self, symbol: str) -> float:
        if symbol.endswith((".SH", ".SZ", ".BJ")):
            return 100.0
        return 1.0

    def _round_down_to_lot(self, quantity: float, lot_size: float) -> float:
        if lot_size <= 0:
            return quantity
        return math.floor(quantity / lot_size) * lot_size

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
