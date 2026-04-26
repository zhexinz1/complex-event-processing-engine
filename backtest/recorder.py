"""绩效记录器。"""

from __future__ import annotations

from datetime import datetime

from cep.core.event_bus import EventBus
from cep.core.events import OrderEvent, SignalEvent, TradeEvent

from .models import EquitySnapshot
from .portfolio import PortfolioLedger


class PerformanceRecorder:
    """记录信号、订单、成交与权益快照。"""

    def __init__(self, event_bus: EventBus, portfolio: PortfolioLedger) -> None:
        self.event_bus = event_bus
        self.portfolio = portfolio
        self.signals: list[SignalEvent] = []
        self.orders: list[OrderEvent] = []
        self.trades: list[TradeEvent] = []
        self.snapshots: list[EquitySnapshot] = []

        self.event_bus.subscribe(SignalEvent, self.on_signal)
        self.event_bus.subscribe(OrderEvent, self.on_order)
        self.event_bus.subscribe(TradeEvent, self.on_trade)

    def on_signal(self, event: SignalEvent) -> None:
        self.signals.append(event)

    def on_order(self, event: OrderEvent) -> None:
        self.orders.append(event)

    def on_trade(self, event: TradeEvent) -> None:
        self.trades.append(event)

    def capture_snapshot(self, timestamp: datetime) -> None:
        """在一个顶层 market event 完成分发后记录权益。"""
        open_positions = sum(
            1 for position in self.portfolio.positions.values() if position.quantity != 0
        )
        self.snapshots.append(
            EquitySnapshot(
                timestamp=timestamp,
                cash=self.portfolio.cash,
                market_value=self.portfolio.market_value,
                equity=self.portfolio.equity,
                realized_pnl=self.portfolio.realized_pnl,
                open_positions=open_positions,
            )
        )
