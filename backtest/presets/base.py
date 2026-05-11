"""Shared helpers for preset backtest strategies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from cep.core.events import BarEvent
from data_provider import (
    fetch_adjusted_main_contract_bars,
    fetch_adjusted_main_contract_bars_multi,
    fetch_tushare_daily_bars,
    normalize_ts_code,
)

from ..models import BacktestResult


@dataclass(frozen=True)
class PresetBacktestRequest:
    """Inputs passed from the public preset runner to a concrete preset."""

    data_source: str = "mock"
    ts_code: str | None = None
    symbols: Any = None
    start_date: str | None = None
    end_date: str | None = None
    write_trade_log: bool = False


class PresetBacktestStrategy(Protocol):
    """Strategy module contract used by the preset registry."""

    metadata: dict[str, Any]

    def run(self, request: PresetBacktestRequest) -> BacktestResult:
        """Run the preset with the supplied data-source request."""
        ...


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


def normalize_single_symbol(raw_symbol: Any) -> str:
    symbol = str(raw_symbol or "").strip().upper()
    if not symbol:
        raise ValueError("adjusted_main_contract 回测需要 symbol/ts_code")
    return symbol


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


def selected_single_symbol(ts_code: str | None, symbols: Any) -> Any:
    return ts_code or (symbols[0] if isinstance(symbols, list) and symbols else symbols)


def load_single_symbol_bars(
    request: PresetBacktestRequest,
    *,
    mock_symbol: str,
    mock_closes: list[float],
) -> tuple[list[BarEvent], str, str]:
    """Load bars for a single-symbol preset and return bars, symbol, bar_freq."""
    if request.data_source == "mock":
        symbol = mock_symbol
        return make_mock_bars(symbol, mock_closes), symbol, "1m"

    if request.data_source == "adjusted_main_contract":
        if not request.start_date or not request.end_date:
            raise ValueError(
                "adjusted_main_contract 回测需要 symbol/ts_code、start_date、end_date"
            )
        symbol = normalize_single_symbol(
            selected_single_symbol(request.ts_code, request.symbols)
        )
        bars = fetch_adjusted_main_contract_bars(
            symbol, request.start_date, request.end_date
        )
        return bars, symbol, "1m"

    if request.data_source == "tushare":
        if not request.ts_code or not request.start_date or not request.end_date:
            raise ValueError("Tushare 回测需要 ts_code、start_date、end_date")
        symbol = normalize_ts_code(request.ts_code)
        bars = fetch_tushare_daily_bars(
            symbol, request.start_date, request.end_date
        )
        return bars, symbol, "1d"

    raise ValueError(f"Unsupported backtest data source: {request.data_source}")


def load_cross_section_bars(
    request: PresetBacktestRequest,
    *,
    mock_closes: dict[str, list[float]],
) -> tuple[list[BarEvent], list[str], str]:
    """Load bars for a multi-symbol cross-sectional preset."""
    if request.data_source == "mock":
        selected_symbols = list(mock_closes)
        bars = make_cross_section_mock_bars(mock_closes)
        return bars, selected_symbols, "1m"

    if request.data_source == "adjusted_main_contract":
        if not request.start_date or not request.end_date:
            raise ValueError("adjusted_main_contract 横截面回测需要 start_date、end_date")
        selected_symbols = normalize_symbol_group(
            request.symbols, use_tushare_format=False
        )
        bars = fetch_adjusted_main_contract_bars_multi(
            selected_symbols, request.start_date, request.end_date
        )
        return bars, selected_symbols, "1m"

    if request.data_source == "tushare":
        if not request.start_date or not request.end_date:
            raise ValueError("Tushare 横截面回测需要 start_date、end_date")
        selected_symbols = normalize_symbol_group(request.symbols)
        bars = fetch_cross_section_tushare_bars(
            selected_symbols, request.start_date, request.end_date
        )
        return bars, selected_symbols, "1d"

    raise ValueError(f"Unsupported backtest data source: {request.data_source}")


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
