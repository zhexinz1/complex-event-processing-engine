"""PBX1 + MA$1 preset strategy."""

from __future__ import annotations

from typing import Any

from cep.core.events import BarEvent, BaseEvent, OrderSide, SignalEvent, SignalType
from cep.triggers import BaseTrigger

from ..engine import BacktestEngine
from ..models import BacktestResult
from .base import PresetBacktestRequest, load_single_symbol_bars


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


METADATA: dict[str, Any] = {
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
}


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


class PbxMaPreset:
    metadata = METADATA

    def run(self, request: PresetBacktestRequest) -> BacktestResult:
        parameters = self.metadata["parameters"]
        bars, symbol, bar_freq = load_single_symbol_bars(
            request,
            mock_symbol=str(self.metadata["symbol"]),
            mock_closes=PBX_MA_PRESET_CLOSES,
        )
        return run_pbx_ma_backtest(
            bars=bars,
            symbol=symbol,
            initial_cash=float(parameters["initial_cash"]),
            quantity=float(parameters["quantity"]),
            pbx_period=int(parameters["pbx_period"]),
            ma_period=int(parameters["ma_period"]),
            bar_freq=bar_freq,
            write_trade_log=request.write_trade_log,
        )
