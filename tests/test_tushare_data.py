from types import SimpleNamespace

import pandas as pd
import tushare as ts

from data_provider.tushare_data import fetch_tushare_daily_bars, normalize_ts_code


def test_normalize_ts_code_infers_common_a_share_suffixes() -> None:
    assert normalize_ts_code("000001") == "000001.SZ"
    assert normalize_ts_code("600000") == "600000.SH"
    assert normalize_ts_code("000001.SZ") == "000001.SZ"


def test_fetch_tushare_daily_bars_converts_daily_rows(monkeypatch) -> None:
    calls = {}

    def fake_pro_api(token=None):
        calls["token"] = token

        def daily(ts_code: str, start_date: str, end_date: str):
            calls["daily_args"] = (ts_code, start_date, end_date)
            return pd.DataFrame(
                [
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": "20240103",
                        "open": 10.0,
                        "high": 10.5,
                        "low": 9.8,
                        "close": 10.2,
                        "vol": 123.4,
                        "amount": 456.7,
                    },
                    {
                        "ts_code": "000001.SZ",
                        "trade_date": "20240102",
                        "open": 9.8,
                        "high": 10.1,
                        "low": 9.6,
                        "close": 10.0,
                        "vol": 100.0,
                        "amount": 400.0,
                    },
                ]
            )

        return SimpleNamespace(daily=daily)

    monkeypatch.setattr(ts, "pro_api", fake_pro_api)

    bars = fetch_tushare_daily_bars(
        ts_code="000001",
        start_date="20240101",
        end_date="20240103",
        token="test-token",
    )

    assert calls["token"] == "test-token"
    assert calls["daily_args"] == ("000001.SZ", "20240101", "20240103")
    assert [bar.bar_time.strftime("%Y%m%d") for bar in bars] == ["20240102", "20240103"]
    assert all(bar.freq == "1d" for bar in bars)
    assert bars[0].close == 10.0
    assert bars[0].turnover == 400_000.0
