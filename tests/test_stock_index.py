import sqlite3

import pytest

from data_provider.stock_index import ensure_stock_index_db, search_stocks


def create_test_stock_index(db_path) -> None:
    with sqlite3.connect(db_path) as conn:
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
            INSERT INTO stocks
                (ts_code, symbol, name, exchange, board, industry, area,
                 list_date, full_name, english_name, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "000001.SZ",
                    "000001",
                    "平安银行",
                    "SZ",
                    "主板",
                    "银行",
                    "深圳",
                    "19910403",
                    "平安银行股份有限公司",
                    "Ping An Bank",
                    "SZSE.xlsx",
                ),
                (
                    "600000.SH",
                    "600000",
                    "浦发银行",
                    "SH",
                    "",
                    "",
                    "",
                    "19991110",
                    "上海浦东发展银行",
                    "SHANGHAI PUDONG DEVELOPMENT BANK",
                    "SHE.xls",
                ),
            ],
        )
        conn.commit()


def test_stock_index_searches_prebuilt_database(tmp_path) -> None:
    db_path = tmp_path / "stock_index.sqlite"
    create_test_stock_index(db_path)

    sz_results = search_stocks("000001", db_path=db_path)
    assert sz_results[0]["ts_code"] == "000001.SZ"
    assert sz_results[0]["name"] == "平安银行"

    sh_results = search_stocks("600000", db_path=db_path)
    assert sh_results[0]["ts_code"] == "600000.SH"
    assert sh_results[0]["name"] == "浦发银行"

    keyword_results = search_stocks("平安", db_path=db_path)
    assert any(row["ts_code"] == "000001.SZ" for row in keyword_results)


def test_stock_index_query_requires_prebuilt_database(tmp_path) -> None:
    db_path = tmp_path / "missing_stock_index.sqlite"

    with pytest.raises(FileNotFoundError, match="build_stock_index.py"):
        ensure_stock_index_db(db_path)
