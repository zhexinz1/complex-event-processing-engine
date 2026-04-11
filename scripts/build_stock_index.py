"""Build the local stock index SQLite database from exchange spreadsheets."""

from __future__ import annotations

import argparse
import sqlite3
import sys
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, cast

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PROVIDER_DIR = PROJECT_ROOT / "data_provider"
DEFAULT_DB_PATH = DATA_PROVIDER_DIR / "stock_index.sqlite"
SHE_FILE = PROJECT_ROOT / "SHE.xls"
SZSE_FILE = PROJECT_ROOT / "SZSE.xlsx"


@dataclass(frozen=True)
class StockRecord:
    ts_code: str
    symbol: str
    name: str
    exchange: str
    board: str = ""
    industry: str = ""
    area: str = ""
    list_date: str = ""
    full_name: str = ""
    english_name: str = ""
    source_file: str = ""


def main() -> None:
    args = _parse_args()
    db_path = build_stock_index_db(
        db_path=args.output,
        she_file=args.she_file,
        szse_file=args.szse_file,
    )
    with sqlite3.connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        by_exchange = conn.execute(
            "SELECT exchange, COUNT(*) FROM stocks GROUP BY exchange ORDER BY exchange"
        ).fetchall()
    print(f"Built stock index: {db_path}")
    print(f"Total stocks: {total}")
    print(f"By exchange: {by_exchange}")


def build_stock_index_db(
    db_path: Path = DEFAULT_DB_PATH,
    she_file: Path = SHE_FILE,
    szse_file: Path = SZSE_FILE,
) -> Path:
    """Merge Shanghai and Shenzhen spreadsheets into a searchable SQLite DB."""
    records = [*load_she_records(she_file), *load_szse_records(szse_file)]
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS stocks")
        conn.execute(
            """
            CREATE TABLE stocks (
                ts_code TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                exchange TEXT NOT NULL,
                board TEXT NOT NULL,
                industry TEXT NOT NULL,
                area TEXT NOT NULL,
                list_date TEXT NOT NULL,
                full_name TEXT NOT NULL,
                english_name TEXT NOT NULL,
                source_file TEXT NOT NULL
            )
            """
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO stocks
                (ts_code, symbol, name, exchange, board, industry, area,
                 list_date, full_name, english_name, source_file)
            VALUES
                (:ts_code, :symbol, :name, :exchange, :board, :industry, :area,
                 :list_date, :full_name, :english_name, :source_file)
            """,
            [asdict(record) for record in records],
        )
        conn.execute("CREATE INDEX idx_stocks_symbol ON stocks(symbol)")
        conn.execute("CREATE INDEX idx_stocks_name ON stocks(name)")
        conn.execute("CREATE INDEX idx_stocks_full_name ON stocks(full_name)")
        conn.commit()

    return db_path


def load_she_records(path: Path = SHE_FILE) -> list[StockRecord]:
    df = _read_excel(path, sheet_name="股票", dtype={"A股代码": str})
    rows = cast(list[dict[str, Any]], df.to_dict(orient="records"))
    return list(_dedupe_records(_parse_she_row(row, path) for row in rows))


def load_szse_records(path: Path = SZSE_FILE) -> list[StockRecord]:
    df = _read_excel(path, sheet_name="A股列表", dtype={"A股代码": str})
    rows = cast(list[dict[str, Any]], df.to_dict(orient="records"))
    return list(_dedupe_records(_parse_szse_row(row, path) for row in rows))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--she-file", type=Path, default=SHE_FILE)
    parser.add_argument("--szse-file", type=Path, default=SZSE_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_DB_PATH)
    return parser.parse_args()


def _parse_she_row(row: dict[str, Any], source: Path) -> StockRecord:
    symbol = _format_symbol(row.get("A股代码"))
    return StockRecord(
        ts_code=f"{symbol}.SH",
        symbol=symbol,
        name=_clean_text(row.get("证券简称")),
        exchange="SH",
        list_date=_format_date(row.get("上市日期")),
        full_name=_clean_text(row.get("扩位证券简称")),
        english_name=_clean_text(row.get("公司英文全称")),
        source_file=source.name,
    )


def _parse_szse_row(row: dict[str, Any], source: Path) -> StockRecord:
    symbol = _format_symbol(row.get("A股代码"))
    return StockRecord(
        ts_code=f"{symbol}.SZ",
        symbol=symbol,
        name=_clean_text(row.get("A股简称")),
        exchange="SZ",
        board=_clean_text(row.get("板块")),
        industry=_clean_text(row.get("所属行业")),
        area=_clean_text(row.get("地      区")),
        list_date=_format_date(row.get("A股上市日期")),
        full_name=_clean_text(row.get("公司全称")),
        english_name=_clean_text(row.get("英文名称")),
        source_file=source.name,
    )


def _dedupe_records(records: Iterable[StockRecord]) -> Iterable[StockRecord]:
    seen: set[str] = set()
    for record in records:
        if record.ts_code in seen:
            continue
        seen.add(record.ts_code)
        yield record


def _format_symbol(value: Any) -> str:
    text = _clean_text(value).split(".")[0]
    if not text:
        raise ValueError("股票代码为空")
    return text.zfill(6)


def _format_date(value: Any) -> str:
    text = _clean_text(value)
    if not text or text.lower() == "nat":
        return ""
    if "-" in text:
        return text[:10].replace("-", "")
    if "." in text:
        text = text.split(".")[0]
    return text[:8]


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "-"}:
        return ""
    return text


def _read_excel(path: Path, sheet_name: str, dtype: dict[str, Any]) -> Any:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Workbook contains no default style")
        return pd.read_excel(path, sheet_name=sheet_name, dtype=cast(Any, dtype))


if __name__ == "__main__":
    sys.path.insert(0, str(PROJECT_ROOT))
    main()
