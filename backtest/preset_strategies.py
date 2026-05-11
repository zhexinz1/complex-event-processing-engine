"""Preset strategies and datasets for demo backtests."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from cep.core.events import BarEvent, BaseEvent, OrderSide, SignalEvent, SignalType
from cep.triggers import BaseTrigger
from data_provider import (
    fetch_adjusted_main_contract_bars,
    fetch_adjusted_main_contract_bars_multi,
    fetch_tushare_daily_bars,
    normalize_ts_code,
)

from .engine import BacktestEngine
from .models import BacktestResult


PBX_MA_PRESET_CLOSES = [
    100.0,
    99.0,
    98.0,
    97.0,
    96.0,
    95.0,
    94.0,
    93.0,
    92.0,
    91.0,
    90.0,
    89.0,
    88.0,
    87.0,
    86.0,
    85.0,
    86.0,
    87.0,
    88.0,
    90.0,
    93.0,
    96.0,
    100.0,
    104.0,
    108.0,
    111.0,
    113.0,
    115.0,
    116.0,
    115.0,
    113.0,
    110.0,
    107.0,
    104.0,
    100.0,
    96.0,
    93.0,
    91.0,
]

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

PRESET_STRATEGIES = {
    "pbx_ma": {
        "id": "pbx_ma",
        "name": "PBX1 + MA$1 情绪周期",
        "description": "PBX1 瀑布线短线情绪轨配合 MA$1 参照线，使用预设 mock 数据回测启动与退潮信号。",
        "dataset": "emotion_cycle_mock / tushare_daily / adjusted_main_contract_1m",
        "data_sources": ["mock", "tushare", "adjusted_main_contract"],
        "symbol": "600519.SH",
        "parameter_summary": [
            {"label": "PBX 参数", "value": "M1=4"},
            {"label": "MA$1", "value": "MA10"},
        ],
        "parameters": {
            "pbx_period": 4,
            "ma_period": 10,
            "quantity": 100.0,
            "initial_cash": 1_000_000.0,
        },
    },
    "td_demark_9_13": {
        "id": "td_demark_9_13",
        "name": "TD DeMark 9+13 参考信号",
        "description": "复刻 TradingView Pine 的 TD Setup 9 + Countdown 13 参考信号；低位 9+13 买入，高位 9+13 卖出。",
        "dataset": "td_demark_mock / tushare_daily / adjusted_main_contract_1m",
        "data_sources": ["mock", "tushare", "adjusted_main_contract"],
        "symbol": "000680.SZ",
        "parameter_summary": [
            {"label": "Setup", "value": "9 bars vs close[4]"},
            {"label": "Countdown", "value": "13 bars vs low/high[2]"},
        ],
        "parameters": {
            "setup_bars": 9,
            "setup_lookback": 4,
            "countdown_bars": 13,
            "countdown_lookback": 2,
            "weak_position_units": 5.0,
            "full_position_units": 10.0,
            "initial_cash": 1_000_000.0,
        },
    },
    "cross_section_momentum": {
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
    },
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


def make_cross_section_mock_bars(
    symbol_closes: dict[str, list[float]],
) -> list[BarEvent]:
    """Generate synchronized multi-symbol bars for cross-sectional strategies."""
    start = datetime(2026, 4, 1, 9, 30)
    bars: list[BarEvent] = []

    for symbol, closes in symbol_closes.items():
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

    bars.sort(key=lambda bar: (bar.timestamp, symbol_order(symbol_closes, bar.symbol)))
    return bars


def symbol_order(symbol_closes: dict[str, list[float]], symbol: str) -> int:
    return list(symbol_closes).index(symbol)


def normalize_symbol_group(
    raw_symbols: Any, *, use_tushare_format: bool = True
) -> list[str]:
    """Normalize a dynamic symbol universe for cross-sectional backtests."""
    if raw_symbols is None:
        raise ValueError("横截面动量策略需要 symbols / ts_codes 股票池")

    if isinstance(raw_symbols, str):
        candidates = [part.strip() for part in raw_symbols.split(",")]
    elif isinstance(raw_symbols, list):
        candidates = [str(part).strip() for part in raw_symbols]
    else:
        raise ValueError("symbols 必须是股票代码数组，或逗号分隔字符串")

    symbols: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        symbol = (
            normalize_ts_code(candidate) if use_tushare_format else candidate.upper()
        )
        if symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)

    if len(symbols) < 2:
        raise ValueError("横截面动量策略至少需要 2 只股票")
    if len(symbols) > 50:
        raise ValueError("横截面动量策略最多支持 50 只股票")
    return symbols


def fetch_cross_section_tushare_bars(
    symbols: list[str],
    start_date: str,
    end_date: str,
) -> list[BarEvent]:
    """Fetch and merge daily bars for a dynamic stock universe."""
    bars: list[BarEvent] = []
    for symbol in symbols:
        bars.extend(fetch_tushare_daily_bars(symbol, start_date, end_date))
    bars.sort(key=lambda bar: (bar.timestamp, symbols.index(bar.symbol)))
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


class TDDeMark913Trigger(BaseTrigger):
    """TD Setup 9 + Countdown 13 trigger using a reference OHLC stream."""

    BUY_COUNTDOWN = 1
    SELL_COUNTDOWN = -1

    def __init__(
        self,
        engine: BacktestEngine,
        symbol: str,
        trigger_id: str = "TD_DEMARK_9_13",
        setup_bars: int = 9,
        setup_lookback: int = 4,
        countdown_bars: int = 13,
        countdown_lookback: int = 2,
        weak_position_units: float = 5.0,
        full_position_units: float = 10.0,
        bar_freq: str = "1m",
    ) -> None:
        super().__init__(engine.event_bus, trigger_id)
        self.symbol = symbol
        self.setup_bars = setup_bars
        self.setup_lookback = setup_lookback
        self.countdown_bars = countdown_bars
        self.countdown_lookback = countdown_lookback
        self.weak_position_units = weak_position_units
        self.full_position_units = full_position_units
        self.bar_freq = bar_freq

        self._closes: list[float] = []
        self._highs: list[float] = []
        self._lows: list[float] = []
        self._buy_setup = 0
        self._sell_setup = 0
        self._active_countdown = 0
        self._countdown = 0
        self._position_units = 0.0

    def register(self) -> None:
        """Subscribe to BarEvent for the configured reference symbol."""
        self.event_bus.subscribe(BarEvent, self.on_event, symbol=self.symbol)

    def on_event(self, event: BaseEvent) -> None:
        if not isinstance(event, BarEvent):
            return
        if event.symbol != self.symbol or event.freq != self.bar_freq:
            return

        self._closes.append(event.close)
        self._highs.append(event.high)
        self._lows.append(event.low)
        index = len(self._closes) - 1

        if index < max(self.setup_lookback, self.countdown_lookback):
            return

        lookback_close = self._closes[index - self.setup_lookback]
        self._buy_setup = self._buy_setup + 1 if event.close < lookback_close else 0
        self._sell_setup = self._sell_setup + 1 if event.close > lookback_close else 0

        buy_setup_done = self._buy_setup == self.setup_bars
        sell_setup_done = self._sell_setup == self.setup_bars

        if buy_setup_done:
            self._emit_position_signal(event, OrderSide.BUY, "weak", "td_buy_setup_9")
            self._active_countdown = self.BUY_COUNTDOWN
            self._countdown = 0
        if sell_setup_done:
            self._emit_position_signal(
                event, OrderSide.SELL, "weak", "td_sell_setup_9"
            )
            self._active_countdown = self.SELL_COUNTDOWN
            self._countdown = 0

        buy_countdown_qualifies = (
            self._active_countdown == self.BUY_COUNTDOWN
            and not buy_setup_done
            and event.close <= self._lows[index - self.countdown_lookback]
        )
        sell_countdown_qualifies = (
            self._active_countdown == self.SELL_COUNTDOWN
            and not sell_setup_done
            and event.close >= self._highs[index - self.countdown_lookback]
        )

        if buy_countdown_qualifies or sell_countdown_qualifies:
            self._countdown += 1

        buy_signal = (
            self._active_countdown == self.BUY_COUNTDOWN
            and self._countdown == self.countdown_bars
        )
        sell_signal = (
            self._active_countdown == self.SELL_COUNTDOWN
            and self._countdown == self.countdown_bars
        )

        if buy_signal:
            self._emit_position_signal(event, OrderSide.BUY, "strong", "td_buy_9_13")
            self._active_countdown = 0
            self._countdown = 0
        elif sell_signal:
            self._emit_position_signal(event, OrderSide.SELL, "strong", "td_sell_9_13")
            self._active_countdown = 0
            self._countdown = 0

    def _emit_position_signal(
        self,
        event: BarEvent,
        side: OrderSide,
        strength: str,
        reason: str,
    ) -> None:
        target_units = self._target_position_units(side, strength)
        delta = target_units - self._position_units
        if abs(delta) <= 1e-9:
            return

        trade_side = OrderSide.BUY if delta > 0 else OrderSide.SELL
        quantity = abs(delta)
        signal = SignalEvent(
            source=self.trigger_id,
            symbol=event.symbol,
            signal_type=SignalType.TRADE_OPPORTUNITY,
            rule_id=self.trigger_id,
            timestamp=event.timestamp,
            payload={
                "bar_time": event.bar_time.isoformat(),
                "side": trade_side.value,
                "quantity": quantity,
                "price": event.close,
                "close": event.close,
                "td_side": side.value,
                "strength": strength,
                "target_position_units": target_units,
                "previous_position_units": self._position_units,
                "setup_bars": self.setup_bars,
                "setup_lookback": self.setup_lookback,
                "countdown_bars": self.countdown_bars,
                "countdown_lookback": self.countdown_lookback,
                "countdown": self.countdown_bars,
                "reason": reason,
            },
        )
        self._position_units = target_units
        self.event_bus.publish(signal)

    def _target_position_units(self, side: OrderSide, strength: str) -> float:
        if side == OrderSide.BUY:
            if strength == "strong":
                return self.full_position_units
            return max(self._position_units, self.weak_position_units)
        if strength == "strong":
            return 0.0
        return min(self._position_units, self.weak_position_units)


def run_pbx_ma_backtest(
    bars: list[BarEvent],
    symbol: str,
    initial_cash: float = 1_000_000.0,
    quantity: float = 100.0,
    pbx_period: int = 4,
    ma_period: int = 10,
    bar_freq: str = "1m",
    write_trade_log: bool = False,
) -> BacktestResult:
    """Run PBX/MA strategy on caller-provided bars."""
    engine = BacktestEngine(
        initial_cash=initial_cash,
        default_order_quantity=quantity,
        commission_rate=0.0003,
        write_trade_log=write_trade_log,
    )
    trigger = PbxMaEmotionTrigger(
        engine=engine,
        symbol=symbol,
        pbx_period=pbx_period,
        ma_period=ma_period,
        quantity=quantity,
        bar_freq=bar_freq,
    )
    trigger.register()

    engine.ingest_bars(bars, assume_sorted=True)
    return engine.run()


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


def run_td_demark_9_13_backtest(
    bars: list[BarEvent],
    symbol: str,
    initial_cash: float = 1_000_000.0,
    weak_position_units: float = 5.0,
    full_position_units: float = 10.0,
    setup_bars: int = 9,
    setup_lookback: int = 4,
    countdown_bars: int = 13,
    countdown_lookback: int = 2,
    bar_freq: str = "1m",
    write_trade_log: bool = False,
) -> BacktestResult:
    """Run the TD DeMark 9+13 reference-signal strategy."""
    engine = BacktestEngine(
        initial_cash=initial_cash,
        default_order_quantity=full_position_units,
        commission_rate=0.0003,
        write_trade_log=write_trade_log,
    )
    trigger = TDDeMark913Trigger(
        engine=engine,
        symbol=symbol,
        setup_bars=setup_bars,
        setup_lookback=setup_lookback,
        countdown_bars=countdown_bars,
        countdown_lookback=countdown_lookback,
        weak_position_units=weak_position_units,
        full_position_units=full_position_units,
        bar_freq=bar_freq,
    )
    trigger.register()

    engine.ingest_bars(bars, assume_sorted=True)
    return engine.run()


def run_preset_backtest(
    strategy_id: str,
    data_source: str = "mock",
    ts_code: str | None = None,
    symbols: Any = None,
    start_date: str | None = None,
    end_date: str | None = None,
    write_trade_log: bool = False,
) -> BacktestResult:
    """Run a supported preset strategy against its preset dataset."""
    if strategy_id not in PRESET_STRATEGIES:
        raise ValueError(f"Unsupported preset strategy: {strategy_id}")

    preset = PRESET_STRATEGIES[strategy_id]
    parameters = preset["parameters"]

    if strategy_id == "cross_section_momentum":
        if data_source == "mock":
            selected_symbols = list(preset["symbols"])
            bars = make_cross_section_mock_bars(CROSS_SECTION_MOMENTUM_CLOSES)
            bar_freq = "1m"
        elif data_source == "adjusted_main_contract":
            if not start_date or not end_date:
                raise ValueError(
                    "adjusted_main_contract 横截面回测需要 start_date、end_date"
                )
            selected_symbols = normalize_symbol_group(symbols, use_tushare_format=False)
            bars = fetch_adjusted_main_contract_bars_multi(
                selected_symbols, start_date, end_date
            )
            bar_freq = "1m"
        elif data_source == "tushare":
            if not start_date or not end_date:
                raise ValueError("Tushare 横截面回测需要 start_date、end_date")
            selected_symbols = normalize_symbol_group(symbols)
            bars = fetch_cross_section_tushare_bars(
                selected_symbols, start_date, end_date
            )
            bar_freq = "1d"
        else:
            raise ValueError(f"Unsupported backtest data source: {data_source}")

        return run_cross_section_momentum_backtest(
            bars=bars,
            symbols=selected_symbols,
            initial_cash=float(parameters["initial_cash"]),
            quantity=float(parameters["quantity"]),
            lookback=int(parameters["lookback"]),
            bar_freq=bar_freq,
            write_trade_log=write_trade_log,
        )

    if strategy_id == "td_demark_9_13":
        if data_source == "tushare":
            if not ts_code or not start_date or not end_date:
                raise ValueError("Tushare 回测需要 ts_code、start_date、end_date")
            symbol = normalize_ts_code(ts_code)
            bars = fetch_tushare_daily_bars(symbol, start_date, end_date)
            bar_freq = "1d"
        else:
            raise ValueError(f"Unsupported backtest data source: {data_source}")

        return run_td_demark_9_13_backtest(
            bars=bars,
            symbol=symbol,
            initial_cash=float(parameters["initial_cash"]),
            weak_position_units=float(parameters["weak_position_units"]),
            full_position_units=float(parameters["full_position_units"]),
            setup_bars=int(parameters["setup_bars"]),
            setup_lookback=int(parameters["setup_lookback"]),
            countdown_bars=int(parameters["countdown_bars"]),
            countdown_lookback=int(parameters["countdown_lookback"]),
            bar_freq=bar_freq,
            write_trade_log=write_trade_log,
        )

    if data_source == "mock":
        symbol = str(preset["symbol"])
        bar_freq = "1m"
        bars = make_mock_bars(symbol, PBX_MA_PRESET_CLOSES)
    elif data_source == "adjusted_main_contract":
        if not start_date or not end_date:
            raise ValueError(
                "adjusted_main_contract 回测需要 symbol/ts_code、start_date、end_date"
            )
        symbol = (
            str(
                ts_code
                or (
                    symbols[0]
                    if isinstance(symbols, list) and symbols
                    else symbols or ""
                )
            )
            .strip()
            .upper()
        )
        if not symbol:
            raise ValueError("adjusted_main_contract 回测需要 symbol/ts_code")
        bars = fetch_adjusted_main_contract_bars(symbol, start_date, end_date)
        bar_freq = "1m"
    elif data_source == "tushare":
        if not ts_code or not start_date or not end_date:
            raise ValueError("Tushare 回测需要 ts_code、start_date、end_date")
        symbol = normalize_ts_code(ts_code)
        bars = fetch_tushare_daily_bars(symbol, start_date, end_date)
        bar_freq = "1d"
    else:
        raise ValueError(f"Unsupported backtest data source: {data_source}")

    return run_pbx_ma_backtest(
        bars=bars,
        symbol=symbol,
        initial_cash=float(parameters["initial_cash"]),
        quantity=float(parameters["quantity"]),
        pbx_period=int(parameters["pbx_period"]),
        ma_period=int(parameters["ma_period"]),
        bar_freq=bar_freq,
        write_trade_log=write_trade_log,
    )


def _compute_performance_metrics(result: BacktestResult) -> dict[str, Any]:
    """Derive standard performance statistics from a completed backtest."""
    import math
    from collections import defaultdict

    initial_cash = float(getattr(result, "initial_cash", 1_000_000.0))
    final_equity = result.final_equity

    # Total return
    total_return = (final_equity - initial_cash) / initial_cash if initial_cash else 0.0

    # Duration & annualized return
    snapshots = result.snapshots
    if len(snapshots) >= 2:
        first_ts = snapshots[0].timestamp
        last_ts = snapshots[-1].timestamp
        days = max((last_ts - first_ts).total_seconds() / 86400, 1.0)
    else:
        days = 1.0

    years = days / 365.25
    if years > 0 and (1 + total_return) > 0:
        annualized_return = (1 + total_return) ** (1 / years) - 1
    else:
        annualized_return = 0.0

    # Max drawdown (from full snapshot series)
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    if snapshots:
        peak = snapshots[0].equity
        for snap in snapshots:
            if snap.equity > peak:
                peak = snap.equity
            dd = peak - snap.equity
            if dd > max_drawdown:
                max_drawdown = dd
                max_drawdown_pct = dd / peak if peak > 0 else 0.0

    # Sharpe ratio (per-bar returns, annualized)
    sharpe_ratio = 0.0
    if len(snapshots) >= 3:
        equities = [s.equity for s in snapshots]
        daily_returns: list[float] = []
        for i in range(1, len(equities)):
            if equities[i - 1] > 0:
                daily_returns.append(equities[i] / equities[i - 1] - 1)
        if daily_returns:
            mean_r = sum(daily_returns) / len(daily_returns)
            var_r = sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns)
            std_r = math.sqrt(var_r) if var_r > 0 else 0.0
            if std_r > 0:
                bars_per_day = len(snapshots) / days if days > 0 else 1
                sharpe_ratio = (mean_r / std_r) * math.sqrt(bars_per_day * 252)

    # Win rate (FIFO round-trip matching)
    open_trades: dict[str, list[float]] = defaultdict(list)
    wins = 0
    losses = 0
    for trade in result.trades:
        if trade.side.value == "BUY":
            open_trades[trade.symbol].append(trade.price)
        elif trade.side.value == "SELL" and open_trades[trade.symbol]:
            entry_price = open_trades[trade.symbol].pop(0)
            if trade.price >= entry_price:
                wins += 1
            else:
                losses += 1

    round_trips = wins + losses
    win_rate = wins / round_trips if round_trips > 0 else None

    return {
        "total_return_pct": round(total_return * 100, 2),
        "annualized_return_pct": round(annualized_return * 100, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "max_drawdown": round(max_drawdown, 2),
        "max_drawdown_pct": round(max_drawdown_pct * 100, 2),
        "win_rate_pct": round(win_rate * 100, 2) if win_rate is not None else None,
        "round_trip_trades": round_trips,
        "trade_count": len(result.trades),
        "trading_days": round(days, 1),
    }


def serialize_backtest_result(
    result: BacktestResult, *, max_equity_points: int = 200
) -> dict[str, Any]:
    """Convert BacktestResult into a JSON-ready response payload.

    Parameters
    ----------
    max_equity_points:
        Maximum number of equity-curve snapshots to include.  The front-end
        only renders ~48 bars, so sending tens of thousands of points wastes
        bandwidth and blocks the browser during JSON parsing.  Defaults to
        200, which gives smooth charts while keeping the payload small.
    """
    initial_cash = float(getattr(result, "initial_cash", 1_000_000.0))
    unrealized_pnl = float(
        getattr(
            result,
            "unrealized_pnl",
            result.final_equity - initial_cash - result.realized_pnl,
        )
    )

    # Downsample equity curve to keep response compact.
    snapshots = result.snapshots
    total_snapshots = len(snapshots)
    if total_snapshots > max_equity_points:
        step = total_snapshots / max_equity_points
        indices = {0, total_snapshots - 1}
        indices.update(int(i * step) for i in range(max_equity_points))
        snapshots = [snapshots[i] for i in sorted(indices)]

    # Cap signals and trades to keep the HTTP response small.
    # The front-end only needs them for display; full details live in the
    # trade-log file when write_trade_log is enabled.
    MAX_SIGNAL_ITEMS = 500
    MAX_TRADE_ITEMS = 500

    capped_signals = result.signals[:MAX_SIGNAL_ITEMS]
    capped_trades = result.trades[:MAX_TRADE_ITEMS]

    return {
        "market_events_processed": result.market_events_processed,
        "initial_cash": round(initial_cash, 2),
        "final_cash": round(result.final_cash, 2),
        "final_market_value": round(result.final_market_value, 2),
        "final_equity": round(result.final_equity, 2),
        "realized_pnl": round(result.realized_pnl, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "trade_log_path": result.trade_log_path,
        "equity_curve_count": total_snapshots,
        "total_signals": len(result.signals),
        "total_trades": len(result.trades),
        "performance": _compute_performance_metrics(result),
        "signals": [
            {
                "timestamp": signal.timestamp.isoformat(),
                "symbol": signal.symbol,
                "source": signal.source,
                "rule_id": signal.rule_id,
                "signal_type": signal.signal_type.value,
                "payload": signal.payload,
            }
            for signal in capped_signals
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
            for trade in capped_trades
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
            for snapshot in snapshots
        ],
    }
