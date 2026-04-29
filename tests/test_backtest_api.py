from datetime import datetime, timedelta

from adapters.flask_app import create_app
from backtest.preset_strategies import PBX_MA_PRESET_CLOSES
from cep.core.events import BarEvent


def test_backtest_api_runs_pbx_ma_preset() -> None:
    app = create_app()
    client = app.test_client()

    presets_response = client.get("/api/backtests/presets")
    assert presets_response.status_code == 200
    presets_payload = presets_response.get_json()
    assert presets_payload["success"] is True
    assert presets_payload["data"][0]["id"] == "pbx_ma"

    run_response = client.post("/api/backtests/run", json={"strategy_id": "pbx_ma"})
    assert run_response.status_code == 200
    run_payload = run_response.get_json()
    assert run_payload["success"] is True

    data = run_payload["data"]
    assert data["market_events_processed"] == 38
    assert data["final_equity"] == 1_000_694.21
    assert data["realized_pnl"] == 700.0
    assert len(data["signals"]) == 2
    assert len(data["trades"]) == 2
    assert data["signals"][0]["payload"]["side"] == "BUY"
    assert data["signals"][1]["payload"]["side"] == "SELL"


def test_backtest_api_runs_pbx_ma_with_tushare_source(monkeypatch) -> None:
    def fake_fetch_tushare_daily_bars(ts_code: str, start_date: str, end_date: str):
        assert ts_code == "000001.SZ"
        assert start_date == "20240101"
        assert end_date == "20241231"

        start = datetime(2024, 1, 1, 15, 0)
        return [
            BarEvent(
                symbol=ts_code,
                freq="1d",
                open=close,
                high=close + 0.2,
                low=close - 0.2,
                close=close,
                volume=1000 + index,
                turnover=close * (1000 + index),
                bar_time=start + timedelta(days=index),
                timestamp=start + timedelta(days=index),
            )
            for index, close in enumerate(PBX_MA_PRESET_CLOSES)
        ]

    monkeypatch.setattr(
        "backtest.preset_strategies.fetch_tushare_daily_bars",
        fake_fetch_tushare_daily_bars,
    )

    app = create_app()
    client = app.test_client()
    response = client.post(
        "/api/backtests/run",
        json={
            "strategy_id": "pbx_ma",
            "data_source": "tushare",
            "ts_code": "000001",
            "start_date": "20240101",
            "end_date": "20241231",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["market_events_processed"] == 38
    assert payload["data"]["signals"][0]["symbol"] == "000001.SZ"


def test_backtest_api_runs_pbx_ma_with_adjusted_main_contract_source(monkeypatch) -> None:
    def fake_fetch_adjusted_main_contract_bars(symbol: str, start_date: str, end_date: str):
        assert symbol == "AU9999.XSGE"
        assert start_date == "20250601"
        assert end_date == "20250630"

        start = datetime(2025, 6, 1, 9, 0)
        return [
            BarEvent(
                symbol=symbol,
                freq="1m",
                open=close,
                high=close + 0.2,
                low=close - 0.2,
                close=close,
                volume=1000 + index,
                turnover=close * (1000 + index),
                bar_time=start + timedelta(minutes=index),
                timestamp=start + timedelta(minutes=index),
            )
            for index, close in enumerate(PBX_MA_PRESET_CLOSES)
        ]

    monkeypatch.setattr(
        "backtest.preset_strategies.fetch_adjusted_main_contract_bars",
        fake_fetch_adjusted_main_contract_bars,
    )

    app = create_app()
    client = app.test_client()
    response = client.post(
        "/api/backtests/run",
        json={
            "strategy_id": "pbx_ma",
            "data_source": "adjusted_main_contract",
            "ts_code": "AU9999.XSGE",
            "start_date": "20250601",
            "end_date": "20250630",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["market_events_processed"] == 38
    assert payload["data"]["signals"][0]["symbol"] == "AU9999.XSGE"


def test_backtest_api_passes_write_trade_log_flag(monkeypatch) -> None:
    captured = {}

    def fake_run_preset_backtest(**kwargs):
        captured.update(kwargs)
        return type(
            "FakeResult",
            (),
            {
                "market_events_processed": 0,
                "final_cash": 1_000_000.0,
                "final_market_value": 0.0,
                "final_equity": 1_000_000.0,
                "realized_pnl": 0.0,
                "trade_log_path": "",
                "signals": [],
                "trades": [],
                "positions": {},
                "snapshots": [],
            },
        )()

    monkeypatch.setattr("adapters.flask_app.run_preset_backtest", fake_run_preset_backtest)

    app = create_app()
    client = app.test_client()
    response = client.post(
        "/api/backtests/run",
        json={
            "strategy_id": "pbx_ma",
            "data_source": "mock",
            "write_trade_log": False,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert captured["write_trade_log"] is False


def test_backtest_api_runs_cross_section_momentum_preset() -> None:
    app = create_app()
    client = app.test_client()

    response = client.post(
        "/api/backtests/run",
        json={"strategy_id": "cross_section_momentum", "data_source": "mock"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True

    data = payload["data"]
    assert data["market_events_processed"] == 60
    assert data["signals"]
    assert data["trades"]
    assert data["signals"][0]["payload"]["side"] == "BUY"
    assert {signal["symbol"] for signal in data["signals"]} >= {"000001.SZ", "600000.SH"}


def test_backtest_api_runs_cross_section_momentum_with_tushare_source(monkeypatch) -> None:
    close_map = {
        "000001.SZ": [
            10.0, 10.1, 10.0, 10.2, 10.1, 10.3, 10.5, 10.7, 11.0, 11.4,
            11.8, 12.1, 12.4, 12.8, 13.1, 13.3,
        ],
        "600000.SH": [
            9.8, 9.9, 10.0, 10.1, 10.2, 10.3, 10.2, 10.1, 10.0, 9.9,
            9.8, 9.9, 10.0, 10.2, 10.5, 10.9,
        ],
    }

    def fake_fetch_tushare_daily_bars(ts_code: str, start_date: str, end_date: str):
        assert start_date == "20240101"
        assert end_date == "20240131"

        start = datetime(2024, 1, 1, 15, 0)
        return [
            BarEvent(
                symbol=ts_code,
                freq="1d",
                open=close,
                high=close + 0.2,
                low=close - 0.2,
                close=close,
                volume=1000 + index,
                turnover=close * (1000 + index),
                bar_time=start + timedelta(days=index),
                timestamp=start + timedelta(days=index),
            )
            for index, close in enumerate(close_map[ts_code])
        ]

    monkeypatch.setattr(
        "backtest.preset_strategies.fetch_tushare_daily_bars",
        fake_fetch_tushare_daily_bars,
    )

    app = create_app()
    client = app.test_client()
    response = client.post(
        "/api/backtests/run",
        json={
            "strategy_id": "cross_section_momentum",
            "data_source": "tushare",
            "symbols": ["000001", "600000.SH"],
            "start_date": "20240101",
            "end_date": "20240131",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["market_events_processed"] == 32
    assert payload["data"]["signals"]
    assert {signal["symbol"] for signal in payload["data"]["signals"]} <= set(close_map)


def test_backtest_api_rejects_too_many_cross_section_symbols() -> None:
    app = create_app()
    client = app.test_client()
    response = client.post(
        "/api/backtests/run",
        json={
            "strategy_id": "cross_section_momentum",
            "data_source": "tushare",
            "symbols": [f"{index:06d}.SZ" for index in range(51)],
            "start_date": "20240101",
            "end_date": "20240131",
        },
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "最多支持 50" in payload["message"]


def test_stock_search_api_returns_indexed_matches(monkeypatch) -> None:
    def fake_search_stocks(keyword: str, limit: int = 20):
        assert keyword == "600000"
        assert limit == 5
        return [
            {
                "ts_code": "600000.SH",
                "symbol": "600000",
                "name": "浦发银行",
                "exchange": "SH",
            }
        ]

    monkeypatch.setattr("adapters.flask_app.search_stocks", fake_search_stocks)

    app = create_app()
    client = app.test_client()

    response = client.get("/api/stocks/search", query_string={"q": "600000", "limit": "5"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"][0]["ts_code"] == "600000.SH"
    assert payload["data"][0]["name"] == "浦发银行"
