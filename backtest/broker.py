"""虚拟撮合引擎。"""

from __future__ import annotations

import math
import uuid

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


class SimulatedBroker:
    """将交易信号转换为订单与成交事件。"""

    def __init__(
        self,
        event_bus: EventBus,
        portfolio: PortfolioLedger,
        default_quantity: float = 1.0,
        commission_rate: float = 0.0,
        contract_multipliers: dict[str, float] | None = None,
    ) -> None:
        self.event_bus = event_bus
        self.portfolio = portfolio
        self.default_quantity = default_quantity
        self.commission_rate = commission_rate
        self.contract_multipliers = contract_multipliers or {}
        self._latest_prices: dict[str, float] = {}

        self.event_bus.subscribe(BarEvent, self.on_bar)
        self.event_bus.subscribe(TickEvent, self.on_tick)
        self.event_bus.subscribe(SignalEvent, self.on_signal)

    def on_bar(self, event: BarEvent) -> None:
        self._latest_prices[event.symbol] = event.close

    def on_tick(self, event: TickEvent) -> None:
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
        signal_price = signal.payload.get("price", signal.payload.get("close"))
        price = float(
            signal_price
            if signal_price is not None
            else self._latest_prices.get(signal.symbol, 0.0)
        )
        if not math.isfinite(quantity) or not math.isfinite(price) or quantity <= 0 or price <= 0:
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
        estimated_commission = price * quantity * self.commission_rate
        trade_value = quantity * price * multiplier
        if side == OrderSide.BUY and self.portfolio.cash + 1e-9 < trade_value + estimated_commission:
            self._publish_rejected_order(
                order_id=order_id,
                signal=signal,
                side=side,
                quantity=quantity,
                price=price,
                reason="insufficient_cash",
                details={
                    "required_cash": trade_value + estimated_commission,
                    "available_cash": self.portfolio.cash,
                    "multiplier": multiplier,
                },
            )
            return

        position = self.portfolio.positions.get(signal.symbol)
        available_quantity = position.quantity if position is not None else 0.0
        if side == OrderSide.SELL and quantity > available_quantity + 1e-9:
            self._publish_rejected_order(
                order_id=order_id,
                signal=signal,
                side=side,
                quantity=quantity,
                price=price,
                reason="insufficient_position",
                details={
                    "available_quantity": available_quantity,
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
                timestamp=signal.timestamp,
                payload={"rule_id": signal.rule_id, "signal_source": signal.source},
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
                timestamp=signal.timestamp,
                payload={"rule_id": signal.rule_id, "signal_source": signal.source},
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
                timestamp=signal.timestamp,
                payload={"trade_id": trade_id},
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
