import pytest

from data_provider.stock_index import ensure_stock_index_db, search_stocks
from scripts.build_stock_index import build_stock_index_db


def test_stock_index_searches_shanghai_and_shenzhen_spreadsheets(tmp_path) -> None:
    db_path = tmp_path / "stock_index.sqlite"
    build_stock_index_db(db_path=db_path)

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
