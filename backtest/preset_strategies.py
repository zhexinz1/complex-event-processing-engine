"""Preset strategies and datasets for demo backtests."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from cep.core.events import BarEvent, BaseEvent, OrderSide, SignalEvent, SignalType
from cep.triggers import BaseTrigger

from .engine import BacktestEngine
from .models import BacktestResult


PBX_MA_PRESET_CLOSES = [
    100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0, 91.0,
    90.0, 89.0, 88.0, 87.0, 86.0, 85.0, 86.0, 87.0, 88.0, 90.0,
    93.0, 96.0, 100.0, 104.0, 108.0, 111.0, 113.0, 115.0, 116.0,
    115.0, 113.0, 110.0, 107.0, 104.0, 100.0, 96.0, 93.0, 91.0,
]

PRESET_STRATEGIES = {
    "pbx_ma": {
        "id": "pbx_ma",
        "name": "PBX1 + MA$1 情绪周期",
        "description": "PBX1 瀑布线短线情绪轨配合 MA$1 参照线，使用预设 mock 数据回测启动与退潮信号。",
        "dataset": "emotion_cycle_mock",
        "symbol": "600519.SH",
        "parameters": {
            "pbx_period": 4,
            "ma_period": 10,
            "quantity": 100.0,
            "initial_cash": 1_000_000.0,
        },
    }
}


def make_mock_bars(symbol: str, closes: list[float]) -> list[BarEvent]:
    """Generate replayable mock Bar data."""
    start = datetime(2026, 4, 1, 9, 30)
    bars: list[BarEvent] = []

    prev_close = closes[0]
    for index, close in enumerate(closes):
        bar_time = start + timedelta(minutes=index)
        bars.append(
            BarEvent(
                symbol=symbol,
                freq="1m",
                open=prev_close,
                high=max(prev_close, close) + 0.2,
                low=min(prev_close, close) - 0.2,
                close=close,
                volume=1000 + index * 10,
                turnover=close * (1000 + index * 10),
                bar_time=bar_time,
                timestamp=bar_time,
            )
        )
        prev_close = close

    return bars


# This strategy is intentionally implemented as a Trigger instead of an AST rule.
# The current AST engine evaluates point-in-time boolean expressions against the
# latest LocalContext. PBX/MA emotion-cycle logic needs temporal state: previous
# PBX1/MA$1 values for turn-up/turn-down checks, a price-vs-lines regime change,
# and whether the strategy is already in position so BUY/SELL signals are not
# emitted repeatedly. That makes it a small state machine rather than a pure
# stateless predicate.
class PbxMaEmotionTrigger(BaseTrigger):
    """PBX1 + MA$1 emotion-cycle trigger."""

    def __init__(
        self,
        engine: BacktestEngine,
        symbol: str,
        trigger_id: str = "PBX_MA_EMOTION",
        pbx_period: int = 4,
        ma_period: int = 10,
        quantity: float = 100.0,
        bar_freq: str = "1m",
    ) -> None:
        super().__init__(engine.event_bus, trigger_id)
        self.symbol = symbol
        self.pbx_period = pbx_period
        self.ma_period = ma_period
        self.quantity = quantity
        self.bar_freq = bar_freq

        self._closes: list[float] = []
        self._previous_pbx1: float | None = None
        self._previous_ma1: float | None = None
        self._in_position = False

    def register(self) -> None:
        """Subscribe to BarEvent for the configured symbol."""
        self.event_bus.subscribe(BarEvent, self.on_event, symbol=self.symbol)

    def on_event(self, event: BaseEvent) -> None:
        """Update PBX1/MA$1 and emit a trade signal on emotion-cycle turns."""
        if not isinstance(event, BarEvent):
            return
        if event.symbol != self.symbol or event.freq != self.bar_freq:
            return

        self._closes.append(event.close)
        if len(self._closes) < max(self.pbx_period * 4, self.ma_period):
            return

        pbx1 = self._pbx1()
        ma1 = self._ma(self.ma_period)

        if self._previous_pbx1 is None or self._previous_ma1 is None:
            self._previous_pbx1 = pbx1
            self._previous_ma1 = ma1
            return

        lines_up = pbx1 > self._previous_pbx1 and ma1 > self._previous_ma1
        lines_down = pbx1 < self._previous_pbx1 and ma1 < self._previous_ma1
        price_above_both = event.close > max(pbx1, ma1)
        price_below_both = event.close < min(pbx1, ma1)

        if not self._in_position and price_above_both and lines_up:
            self._emit_trade_signal(event, pbx1, ma1, OrderSide.BUY, "ice_to_start")
            self._in_position = True
        elif self._in_position and price_below_both and lines_down:
            self._emit_trade_signal(event, pbx1, ma1, OrderSide.SELL, "climax_to_ebb")
            self._in_position = False

        self._previous_pbx1 = pbx1
        self._previous_ma1 = ma1

    def _ma(self, period: int) -> float:
        return sum(self._closes[-period:]) / period

    def _pbx1(self) -> float:
        return (
            self._ma(self.pbx_period)
            + self._ma(self.pbx_period * 2)
            + self._ma(self.pbx_period * 4)
        ) / 3

    def _emit_trade_signal(
        self,
        event: BarEvent,
        pbx1: float,
        ma1: float,
        side: OrderSide,
        reason: str,
    ) -> None:
        signal = SignalEvent(
            source=self.trigger_id,
            symbol=event.symbol,
            signal_type=SignalType.TRADE_OPPORTUNITY,
            rule_id=self.trigger_id,
            timestamp=event.timestamp,
            payload={
                "bar_time": event.bar_time.isoformat(),
                "side": side.value,
                "quantity": self.quantity,
                "price": event.close,
                "close": event.close,
                "pbx1": pbx1,
                "ma1": ma1,
                "reason": reason,
            },
        )
        self.event_bus.publish(signal)


def run_preset_backtest(strategy_id: str) -> BacktestResult:
    """Run a supported preset strategy against its preset dataset."""
    if strategy_id != "pbx_ma":
        raise ValueError(f"Unsupported preset strategy: {strategy_id}")

    preset = PRESET_STRATEGIES[strategy_id]
    parameters = preset["parameters"]
    symbol = str(preset["symbol"])

    engine = BacktestEngine(
        initial_cash=float(parameters["initial_cash"]),
        default_order_quantity=float(parameters["quantity"]),
        commission_rate=0.0003,
    )
    trigger = PbxMaEmotionTrigger(
        engine=engine,
        symbol=symbol,
        pbx_period=int(parameters["pbx_period"]),
        ma_period=int(parameters["ma_period"]),
        quantity=float(parameters["quantity"]),
    )
    trigger.register()

    engine.ingest_bars(make_mock_bars(symbol, PBX_MA_PRESET_CLOSES))
    return engine.run()


def serialize_backtest_result(result: BacktestResult) -> dict[str, Any]:
    """Convert BacktestResult into a JSON-ready response payload."""
    return {
        "market_events_processed": result.market_events_processed,
        "final_cash": round(result.final_cash, 2),
        "final_market_value": round(result.final_market_value, 2),
        "final_equity": round(result.final_equity, 2),
        "realized_pnl": round(result.realized_pnl, 2),
        "signals": [
            {
                "timestamp": signal.timestamp.isoformat(),
                "symbol": signal.symbol,
                "source": signal.source,
                "rule_id": signal.rule_id,
                "signal_type": signal.signal_type.value,
                "payload": signal.payload,
            }
            for signal in result.signals
        ],
        "trades": [
            {
                "timestamp": trade.timestamp.isoformat(),
                "symbol": trade.symbol,
                "side": trade.side.value,
                "quantity": trade.quantity,
                "price": trade.price,
                "commission": round(trade.commission, 2),
            }
            for trade in result.trades
        ],
        "positions": [
            {
                "symbol": position.symbol,
                "quantity": position.quantity,
                "avg_price": position.avg_price,
                "realized_pnl": round(position.realized_pnl, 2),
            }
            for position in result.positions.values()
        ],
        "equity_curve": [
            {
                "timestamp": snapshot.timestamp.isoformat(),
                "equity": round(snapshot.equity, 2),
                "cash": round(snapshot.cash, 2),
                "market_value": round(snapshot.market_value, 2),
                "realized_pnl": round(snapshot.realized_pnl, 2),
            }
            for snapshot in result.snapshots
        ],
    }
