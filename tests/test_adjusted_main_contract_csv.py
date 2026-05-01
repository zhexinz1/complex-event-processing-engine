from __future__ import annotations

import csv
from pathlib import Path

from data_provider import adjusted_main_contract_csv
from data_provider.adjusted_main_contract_csv import (
    CSV_CACHE_SIZE,
    fetch_adjusted_main_contract_bars,
    fetch_adjusted_main_contract_bars_multi,
    list_adjusted_main_contract_symbols,
)


def _write_csv(csv_path, rows: list[dict[str, object]]) -> None:
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["date", "open", "high", "low", "close", "volume", "money", "open_interest", "symbol"],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_adjusted_main_contract_csv_queries(tmp_path) -> None:
    adjusted_main_contract_csv._ADJUSTED_MAIN_CONTRACT_BAR_CACHE.clear()
    source_dir = tmp_path / "adjusted_main_contract"
    source_dir.mkdir()

    _write_csv(
        source_dir / "AU9999.XSGE.csv",
        [
            {
                "date": "2025-06-09 09:00:00",
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100.5,
                "volume": 10,
                "money": 1005,
                "open_interest": 88,
                "symbol": "AU2508",
            },
            {
                "date": "2025-06-09 09:01:00",
                "open": 100.5,
                "high": 102,
                "low": 100,
                "close": 101.5,
                "volume": 12,
                "money": 1218,
                "open_interest": 89,
                "symbol": "AU2508",
            },
        ],
    )
    _write_csv(
        source_dir / "IF9999.CCFX.csv",
        [
            {
                "date": "2025-06-09 09:00:00",
                "open": 3500,
                "high": 3505,
                "low": 3498,
                "close": 3502,
                "volume": 20,
                "money": 70040,
                "open_interest": 66,
                "symbol": "IF2506",
            }
        ],
    )

    symbols = list_adjusted_main_contract_symbols(source_dir=source_dir)
    assert symbols == ["AU9999.XSGE", "IF9999.CCFX"]

    bars = fetch_adjusted_main_contract_bars(
        "au9999.xsge",
        "20250609",
        "2025-06-09",
        source_dir=source_dir,
    )
    assert len(bars) == 2
    assert bars[0].symbol == "AU9999.XSGE"
    assert bars[0].freq == "1m"
    assert bars[1].close == 101.5

    merged = fetch_adjusted_main_contract_bars_multi(
        ["IF9999.CCFX", "AU9999.XSGE"],
        "2025-06-09",
        "2025-06-09",
        source_dir=source_dir,
    )
    assert [bar.symbol for bar in merged[:2]] == ["IF9999.CCFX", "AU9999.XSGE"]
    assert merged[-1].symbol == "AU9999.XSGE"


def test_adjusted_main_contract_csv_uses_lru_memory_cache(tmp_path, monkeypatch) -> None:
    adjusted_main_contract_csv._ADJUSTED_MAIN_CONTRACT_BAR_CACHE.clear()
    source_dir = tmp_path / "adjusted_main_contract"
    source_dir.mkdir()

    for index in range(CSV_CACHE_SIZE + 1):
        _write_csv(
            source_dir / f"SYM{index:02d}.TEST.csv",
            [
                {
                    "date": "2025-06-09 09:00:00",
                    "open": 100 + index,
                    "high": 101 + index,
                    "low": 99 + index,
                    "close": 100.5 + index,
                    "volume": 10 + index,
                    "money": 1005 + index,
                    "open_interest": 88 + index,
                    "symbol": f"SYM{index:02d}",
                }
            ],
        )

    open_count = 0
    original_open = Path.open

    def counting_open(self: Path, *args, **kwargs):
        nonlocal open_count
        if self.suffix == ".csv" and args and args[0] == "r":
            open_count += 1
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)

    first = fetch_adjusted_main_contract_bars(
        "sym00.test",
        "2025-06-09",
        "2025-06-09",
        source_dir=source_dir,
    )
    second = fetch_adjusted_main_contract_bars(
        "SYM00.TEST",
        "2025-06-09 09:00:00",
        "2025-06-09 09:00:00",
        source_dir=source_dir,
    )

    assert len(first) == 1
    assert len(second) == 1
    assert open_count == 1

    for index in range(1, CSV_CACHE_SIZE + 1):
        fetch_adjusted_main_contract_bars(
            f"SYM{index:02d}.TEST",
            "2025-06-09",
            "2025-06-09",
            source_dir=source_dir,
        )

    fetch_adjusted_main_contract_bars(
        "SYM00.TEST",
        "2025-06-09",
        "2025-06-09",
        source_dir=source_dir,
    )

    assert open_count == CSV_CACHE_SIZE + 2
