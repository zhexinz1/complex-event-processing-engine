"""TD DeMark 9+13 preset strategy."""

from __future__ import annotations

from typing import Any

from cep.core.events import BarEvent, BaseEvent, OrderSide, SignalEvent, SignalType
from cep.triggers import BaseTrigger

from ..engine import BacktestEngine
from ..models import BacktestResult
from .base import PresetBacktestRequest, fetch_tushare_daily_bars, normalize_ts_code


METADATA: dict[str, Any] = {
    "id": "td_demark_9_13",
    "name": "TD DeMark 9+13 参考信号",
    "description": "复刻 TradingView Pine 的 TD Setup 9 + Countdown 13 参考信号；低位 9+13 买入，高位 9+13 卖出。",
    "dataset": "tushare_daily",
    "data_sources": ["tushare"],
    "symbol": "000680.SZ",
    "parameter_summary": [
        {"label": "Setup", "value": "9 bars vs close[4]"},
        {"label": "Countdown", "value": "13 bars vs low/high[2]"},
        {"label": "仓位映射", "value": "weak=5/10, strong=10/10"},
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
}


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


class TDDeMark913Preset:
    metadata = METADATA

    def run(self, request: PresetBacktestRequest) -> BacktestResult:
        if request.data_source != "tushare":
            raise ValueError(f"Unsupported backtest data source: {request.data_source}")
        if not request.ts_code or not request.start_date or not request.end_date:
            raise ValueError("Tushare 回测需要 ts_code、start_date、end_date")

        parameters = self.metadata["parameters"]
        symbol = normalize_ts_code(request.ts_code)
        bars = fetch_tushare_daily_bars(symbol, request.start_date, request.end_date)
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
            bar_freq="1d",
            write_trade_log=request.write_trade_log,
        )
