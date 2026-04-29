"""Direct CSV loading for adjusted main contract minute bars."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable

from cep.core.events import BarEvent

DATA_PROVIDER_DIR = Path(__file__).parent
PROJECT_ROOT = DATA_PROVIDER_DIR.parent
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "adjusted_main_contract"


def list_adjusted_main_contract_symbols(
    source_dir: Path = DEFAULT_SOURCE_DIR,
) -> list[str]:
    """List continuous symbols available under the adjusted main contract CSV directory."""
    csv_files = sorted(source_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(
            f"No CSV files found under {source_dir}. "
            "Expected adjusted main contract history files such as AU9999.XSGE.csv."
        )
    return [csv_path.stem.upper() for csv_path in csv_files]


def fetch_adjusted_main_contract_bars(
    symbol: str,
    start_date: str,
    end_date: str,
    source_dir: Path = DEFAULT_SOURCE_DIR,
) -> list[BarEvent]:
    """Load one symbol's adjusted main contract minute bars directly from CSV."""
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol 不能为空")

    csv_path = source_dir / f"{normalized_symbol}.csv"
    if not csv_path.exists():
        raise ValueError(f"adjusted_main_contract 中未找到标的文件: {normalized_symbol}")

    start_ts = _normalize_datetime_boundary(start_date, is_end=False)
    end_ts = _normalize_datetime_boundary(end_date, is_end=True)
    bars: list[BarEvent] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            bar_time = datetime.strptime(row["date"].strip(), "%Y-%m-%d %H:%M:%S")
            if bar_time < start_ts or bar_time > end_ts:
                continue
            bars.append(
                BarEvent(
                    symbol=normalized_symbol,
                    freq="1m",
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(float(row["volume"])),
                    turnover=float(row["money"]),
                    bar_time=bar_time,
                    timestamp=bar_time,
                )
            )

    if not bars:
        raise ValueError(
            f"adjusted_main_contract 中未找到 {normalized_symbol} 在 {start_date} 至 {end_date} 的历史数据"
        )
    return bars


def fetch_adjusted_main_contract_bars_multi(
    symbols: Iterable[str],
    start_date: str,
    end_date: str,
    source_dir: Path = DEFAULT_SOURCE_DIR,
) -> list[BarEvent]:
    """Load and merge multiple symbols' adjusted main contract bars from CSV files."""
    normalized_symbols: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized = str(symbol).strip().upper()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_symbols.append(normalized)

    if not normalized_symbols:
        raise ValueError("symbols 不能为空")

    ordering = {symbol: index for index, symbol in enumerate(normalized_symbols)}
    bars: list[BarEvent] = []
    for symbol in normalized_symbols:
        bars.extend(fetch_adjusted_main_contract_bars(symbol, start_date, end_date, source_dir=source_dir))

    bars.sort(key=lambda bar: (bar.timestamp, ordering[bar.symbol]))
    return bars


def _normalize_datetime_boundary(value: str, is_end: bool) -> datetime:
    raw = str(value).strip()
    if not raw:
        raise ValueError("start_date / end_date 不能为空")

    if len(raw) == 8 and raw.isdigit():
        dt = datetime.strptime(raw, "%Y%m%d")
        return dt.replace(hour=23, minute=59, second=59) if is_end else dt

    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        dt = datetime.strptime(raw, "%Y-%m-%d")
        return dt.replace(hour=23, minute=59, second=59) if is_end else dt

    try:
        dt = datetime.fromisoformat(raw.replace("T", " "))
    except ValueError as exc:
        raise ValueError(f"无法解析日期时间: {value}") from exc
    return dt
