"""Local stock index database queries."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

DATA_PROVIDER_DIR = Path(__file__).parent
DEFAULT_DB_PATH = DATA_PROVIDER_DIR / "stock_index.sqlite"


def ensure_stock_index_db(db_path: Path = DEFAULT_DB_PATH) -> Path:
    """Return the stock index DB path, or fail if it was not generated."""
    if not db_path.exists():
        raise FileNotFoundError(
            f"Stock index database not found: {db_path}. "
            "Run `uv run python scripts/build_stock_index.py` to generate it."
        )
    return db_path


def search_stocks(
    keyword: str,
    limit: int = 20,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Search stocks by ts_code, symbol, short name, full name, or industry."""
    query = keyword.strip().upper()
    if not query:
        return []

    ensure_stock_index_db(db_path)
    like = f"%{query}%"
    limit = max(1, min(limit, 100))

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT ts_code, symbol, name, exchange, board, industry, area,
                   list_date, full_name, english_name, source_file
            FROM stocks
            WHERE ts_code LIKE ?
               OR symbol LIKE ?
               OR UPPER(name) LIKE ?
               OR UPPER(full_name) LIKE ?
               OR UPPER(english_name) LIKE ?
               OR UPPER(industry) LIKE ?
            ORDER BY
                CASE
                    WHEN ts_code = ? THEN 0
                    WHEN symbol = ? THEN 1
                    WHEN ts_code LIKE ? THEN 2
                    WHEN symbol LIKE ? THEN 3
                    ELSE 4
                END,
                ts_code
            LIMIT ?
            """,
            (like, like, like, like, like, like, query, query, f"{query}%", f"{query}%", limit),
        ).fetchall()

    return [dict(row) for row in rows]
