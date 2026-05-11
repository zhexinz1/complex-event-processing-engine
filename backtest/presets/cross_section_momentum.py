"""Cross-sectional momentum preset strategy."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from cep.core.events import BarEvent, BaseEvent, OrderSide, SignalEvent, SignalType
from cep.triggers import BaseTrigger

from ..engine import BacktestEngine
from ..models import BacktestResult
from .base import PresetBacktestRequest, load_cross_section_bars


CROSS_SECTION_MOMENTUM_CLOSES = {
    "000001.SZ": [
        10.0,
        10.1,
        10.0,
        10.2,
        10.1,
        10.3,
        10.5,
        10.7,
        11.0,
        11.4,
        11.8,
        12.1,
        12.4,
        12.8,
        13.1,
        13.3,
        13.2,
        13.1,
        13.0,
        12.9,
    ],
    "600000.SH": [
        9.8,
        9.9,
        10.0,
        10.1,
        10.2,
        10.3,
        10.2,
        10.1,
        10.0,
        9.9,
        9.8,
        9.9,
        10.0,
        10.2,
        10.5,
        10.9,
        11.4,
        12.0,
        12.5,
        13.0,
    ],
    "300750.SZ": [
        20.0,
        19.8,
        19.7,
        19.6,
        19.5,
        19.4,
        19.6,
        19.8,
        20.1,
        20.3,
        20.4,
        20.5,
        20.4,
        20.3,
        20.2,
        20.1,
        20.0,
        19.9,
        19.8,
        19.7,
    ],
}


METADATA: dict[str, Any] = {
    "id": "cross_section_momentum",
    "name": "横截面动量轮动",
    "description": "在多只股票之间比较最近 N 根收益率，持有横截面表现最强的一只；冠军变化时卖出旧标的并买入新标的。",
    "dataset": "cross_section_momentum_mock",
    "data_sources": ["mock", "adjusted_main_contract"],
    "symbol": "multi-stock universe",
    "symbols": list(CROSS_SECTION_MOMENTUM_CLOSES),
    "parameter_summary": [
        {"label": "动量窗口", "value": "5 bars"},
        {"label": "股票池", "value": "3 stocks"},
    ],
    "parameters": {
        "lookback": 5,
        "quantity": 100.0,
        "initial_cash": 1_000_000.0,
    },
}


class CrossSectionMomentumTrigger(BaseTrigger):
    """Pick the strongest recent performer from a stock universe."""

    def __init__(
        self,
        engine: BacktestEngine,
        symbols: list[str],
        trigger_id: str = "CROSS_SECTION_MOMENTUM",
        lookback: int = 5,
        quantity: float = 100.0,
        bar_freq: str = "1m",
    ) -> None:
        super().__init__(engine.event_bus, trigger_id)
        self.symbols = symbols
        self.symbol_set = set(symbols)
        self.lookback = lookback
        self.quantity = quantity
        self.bar_freq = bar_freq

        self._closes: dict[str, list[float]] = {symbol: [] for symbol in symbols}
        self._latest_bars: dict[str, BarEvent] = {}
        self._seen_by_time: dict[datetime, set[str]] = defaultdict(set)
        self._current_symbol: str | None = None
        self._last_rebalance_time: datetime | None = None

    def register(self) -> None:
        """Subscribe globally because this trigger compares multiple symbols."""
        self.event_bus.subscribe(BarEvent, self.on_event)

    def on_event(self, event: BaseEvent) -> None:
        if not isinstance(event, BarEvent):
            return
        if event.symbol not in self.symbol_set or event.freq != self.bar_freq:
            return

        self._closes[event.symbol].append(event.close)
        self._latest_bars[event.symbol] = event
        self._seen_by_time[event.bar_time].add(event.symbol)

        if self._last_rebalance_time == event.bar_time:
            return
        if self._seen_by_time[event.bar_time] != self.symbol_set:
            return
        if any(len(self._closes[symbol]) <= self.lookback for symbol in self.symbols):
            return

        scores = {
            symbol: (
                self._closes[symbol][-1] / self._closes[symbol][-(self.lookback + 1)]
            )
            - 1.0
            for symbol in self.symbols
        }
        winner = max(scores, key=lambda symbol: scores[symbol])
        if winner == self._current_symbol:
            self._last_rebalance_time = event.bar_time
            return

        previous_symbol = self._current_symbol
        if previous_symbol is not None:
            self._emit_trade_signal(
                self._latest_bars[previous_symbol],
                OrderSide.SELL,
                scores[previous_symbol],
                winner,
                "rotate_out",
            )

        self._emit_trade_signal(
            self._latest_bars[winner],
            OrderSide.BUY,
            scores[winner],
            winner,
            "rotate_in",
        )
        self._current_symbol = winner
        self._last_rebalance_time = event.bar_time

    def _emit_trade_signal(
        self,
        event: BarEvent,
        side: OrderSide,
        score: float,
        winner: str,
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
                "score": score,
                "winner": winner,
                "lookback": self.lookback,
                "reason": reason,
            },
        )
        self.event_bus.publish(signal)


def run_cross_section_momentum_backtest(
    bars: list[BarEvent],
    symbols: list[str],
    initial_cash: float = 1_000_000.0,
    quantity: float = 100.0,
    lookback: int = 5,
    bar_freq: str = "1m",
    write_trade_log: bool = False,
) -> BacktestResult:
    """Run a cross-sectional momentum rotation strategy."""
    engine = BacktestEngine(
        initial_cash=initial_cash,
        default_order_quantity=quantity,
        commission_rate=0.0003,
        write_trade_log=write_trade_log,
    )
    trigger = CrossSectionMomentumTrigger(
        engine=engine,
        symbols=symbols,
        lookback=lookback,
        quantity=quantity,
        bar_freq=bar_freq,
    )
    trigger.register()

    engine.ingest_bars(bars, assume_sorted=True)
    return engine.run()


class CrossSectionMomentumPreset:
    metadata = METADATA

    def run(self, request: PresetBacktestRequest) -> BacktestResult:
        parameters = self.metadata["parameters"]
        bars, selected_symbols, bar_freq = load_cross_section_bars(
            request, mock_closes=CROSS_SECTION_MOMENTUM_CLOSES
        )
        return run_cross_section_momentum_backtest(
            bars=bars,
            symbols=selected_symbols,
            initial_cash=float(parameters["initial_cash"]),
            quantity=float(parameters["quantity"]),
            lookback=int(parameters["lookback"]),
            bar_freq=bar_freq,
            write_trade_log=request.write_trade_log,
        )
