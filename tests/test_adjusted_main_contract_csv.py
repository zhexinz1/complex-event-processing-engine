from __future__ import annotations

import csv

from data_provider.adjusted_main_contract_csv import (
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
