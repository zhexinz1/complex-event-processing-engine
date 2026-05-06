"""回测组合账本。"""

from __future__ import annotations

from typing import Optional

from cep.core.event_bus import EventBus
from cep.core.events import BarEvent, OrderSide, TickEvent, TradeEvent

from .models import BacktestPosition
from .rules import get_margin_rate


class PortfolioLedger:
    """虚拟投资组合账本。"""

    def __init__(
        self,
        event_bus: EventBus,
        initial_cash: float,
        contract_multipliers: Optional[dict[str, float]] = None,
    ) -> None:
        self.event_bus = event_bus
        self.balance = initial_cash
        self.realized_pnl = 0.0
        self.contract_multipliers = contract_multipliers or {}
        self.positions: dict[str, BacktestPosition] = {}
        self.latest_prices: dict[str, float] = {}

        self.event_bus.subscribe(BarEvent, self.on_bar)
        self.event_bus.subscribe(TickEvent, self.on_tick)
        self.event_bus.subscribe(TradeEvent, self.on_trade)

    def on_bar(self, event: BarEvent) -> None:
        self.latest_prices[event.symbol] = event.close

    def on_tick(self, event: TickEvent) -> None:
        self.latest_prices[event.symbol] = event.last_price

    def on_trade(self, event: TradeEvent) -> None:
        """根据成交事件更新持仓和资金。"""
        multiplier = self.contract_multipliers.get(event.symbol, 1.0)
        signed_quantity = (
            event.quantity if event.side == OrderSide.BUY else -event.quantity
        )

        # Commission is always deducted from the balance
        self.balance -= event.commission

        position = self.positions.setdefault(
            event.symbol, BacktestPosition(symbol=event.symbol)
        )
        current_qty = position.quantity
        new_qty = current_qty + signed_quantity

        if current_qty == 0 or current_qty * signed_quantity > 0:
            total_abs_qty = abs(current_qty) + abs(signed_quantity)
            if total_abs_qty > 0:
                position.avg_price = (
                    (abs(current_qty) * position.avg_price)
                    + (abs(signed_quantity) * event.price)
                ) / total_abs_qty
        else:
            closed_qty = min(abs(current_qty), abs(signed_quantity))
            if current_qty > 0:
                pnl = closed_qty * (event.price - position.avg_price) * multiplier
            else:
                pnl = closed_qty * (position.avg_price - event.price) * multiplier

            position.realized_pnl += pnl
            self.realized_pnl += pnl
            self.balance += pnl  # Realized PnL adjusts balance directly

            if new_qty == 0:
                position.avg_price = 0.0
            elif abs(signed_quantity) > abs(current_qty):
                position.avg_price = event.price

        position.quantity = new_qty

    @property
    def unrealized_pnl(self) -> float:
        """当前浮动盈亏。"""
        total = 0.0
        for symbol, position in self.positions.items():
            if position.quantity == 0:
                continue
            latest_price = self.latest_prices.get(symbol, position.avg_price)
            multiplier = self.contract_multipliers.get(symbol, 1.0)
            total += (
                position.quantity * (latest_price - position.avg_price) * multiplier
            )
        return total

    @property
    def equity(self) -> float:
        """当前组合动态权益（Balance + Unrealized PnL）。"""
        return self.balance + self.unrealized_pnl

    @property
    def margin_occupied(self) -> float:
        """当前占用保证金总额。"""
        total = 0.0
        for symbol, position in self.positions.items():
            if position.quantity == 0:
                continue
            latest_price = self.latest_prices.get(symbol, position.avg_price)
            multiplier = self.contract_multipliers.get(symbol, 1.0)
            margin_rate = get_margin_rate(symbol)
            total += abs(position.quantity) * latest_price * multiplier * margin_rate
        return total

    @property
    def available_funds(self) -> float:
        """当前可用资金（Equity - Margin Occupied）。"""
        return self.equity - self.margin_occupied

    @property
    def cash(self) -> float:
        """兼容性字段：等同于可用资金。"""
        return self.available_funds

    @property
    def market_value(self) -> float:
        """兼容性字段：等同于占用的保证金，保证 cash + market_value = equity 恒等式。"""
        return self.margin_occupied

    def snapshot_positions(self) -> dict[str, BacktestPosition]:
        """返回持仓快照。"""
        return {
            symbol: BacktestPosition(
                symbol=position.symbol,
                quantity=position.quantity,
                avg_price=position.avg_price,
                realized_pnl=position.realized_pnl,
            )
            for symbol, position in self.positions.items()
        }
