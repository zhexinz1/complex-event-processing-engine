"""虚拟撮合引擎。"""

from __future__ import annotations

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


class SimulatedBroker:
    """将交易信号转换为订单与成交事件。"""

    def __init__(
        self,
        event_bus: EventBus,
        default_quantity: float = 1.0,
        commission_rate: float = 0.0,
    ) -> None:
        self.event_bus = event_bus
        self.default_quantity = default_quantity
        self.commission_rate = commission_rate
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
        side = OrderSide.BUY if side_text != OrderSide.SELL.value else OrderSide.SELL
        quantity = float(signal.payload.get("quantity", self.default_quantity))
        signal_price = signal.payload.get("price", signal.payload.get("close"))
        price = float(
            signal_price
            if signal_price is not None
            else self._latest_prices.get(signal.symbol, 0.0)
        )

        order_id = str(uuid.uuid4())
        if quantity <= 0 or price <= 0:
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
                    payload={"reason": "invalid_quantity_or_price"},
                )
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

        commission = price * quantity * self.commission_rate
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
