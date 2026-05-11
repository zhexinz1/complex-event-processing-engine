"""Preset backtest strategy registry."""

from __future__ import annotations

from typing import Any

from ..models import BacktestResult
from .base import (
    PresetBacktestRequest,
    fetch_adjusted_main_contract_bars,
    fetch_adjusted_main_contract_bars_multi,
    fetch_cross_section_tushare_bars,
    fetch_tushare_daily_bars,
    make_cross_section_mock_bars,
    make_mock_bars,
    normalize_symbol_group,
    normalize_ts_code,
)
from .cross_section_momentum import (
    CROSS_SECTION_MOMENTUM_CLOSES,
    CrossSectionMomentumPreset,
    CrossSectionMomentumTrigger,
    run_cross_section_momentum_backtest,
)
from .pbx_ma import PBX_MA_PRESET_CLOSES, PbxMaEmotionTrigger, PbxMaPreset
from .pbx_ma import run_pbx_ma_backtest
from .td_demark_9_13 import (
    TDDeMark913Preset,
    TDDeMark913Trigger,
    run_td_demark_9_13_backtest,
)


PRESET_STRATEGY_RUNNERS = {
    "pbx_ma": PbxMaPreset(),
    "td_demark_9_13": TDDeMark913Preset(),
    "cross_section_momentum": CrossSectionMomentumPreset(),
}

PRESET_STRATEGIES: dict[str, dict[str, Any]] = {
    strategy_id: runner.metadata
    for strategy_id, runner in PRESET_STRATEGY_RUNNERS.items()
}


def run_preset_backtest(
    strategy_id: str,
    data_source: str = "mock",
    ts_code: str | None = None,
    symbols: Any = None,
    start_date: str | None = None,
    end_date: str | None = None,
    write_trade_log: bool = False,
) -> BacktestResult:
    """Run a supported preset strategy through the registry."""
    try:
        runner = PRESET_STRATEGY_RUNNERS[strategy_id]
    except KeyError as exc:
        raise ValueError(f"Unsupported preset strategy: {strategy_id}") from exc

    request = PresetBacktestRequest(
        data_source=data_source,
        ts_code=ts_code,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        write_trade_log=write_trade_log,
    )
    return runner.run(request)


__all__ = [
    "CROSS_SECTION_MOMENTUM_CLOSES",
    "CrossSectionMomentumTrigger",
    "PBX_MA_PRESET_CLOSES",
    "PRESET_STRATEGIES",
    "PRESET_STRATEGY_RUNNERS",
    "PbxMaEmotionTrigger",
    "TDDeMark913Trigger",
    "fetch_adjusted_main_contract_bars",
    "fetch_adjusted_main_contract_bars_multi",
    "fetch_cross_section_tushare_bars",
    "fetch_tushare_daily_bars",
    "make_cross_section_mock_bars",
    "make_mock_bars",
    "normalize_symbol_group",
    "normalize_ts_code",
    "run_cross_section_momentum_backtest",
    "run_pbx_ma_backtest",
    "run_preset_backtest",
    "run_td_demark_9_13_backtest",
]
