from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.flask_app import create_app


VALID_SIGNAL = '''
class Signal:
    name = "Test RSI"
    symbols = ["TEST"]
    bar_freq = "1m"

    def __init__(self, ctx):
        self.ctx = ctx

    def on_bar(self, bar):
        if self.ctx.rsi is not None and self.ctx.rsi < 30:
            return {"side": "BUY", "reason": "oversold", "price": bar.close}
        return None
'''


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("adapters.flask_app.init_db", lambda: None)
    monkeypatch.setattr("adapters.flask_app._reload_live_signal_monitor", lambda: None)
    monkeypatch.setattr(
        "adapters.flask_app.live_signal_monitor.start_redis_subscriber",
        lambda *args, **kwargs: None,
    )
    app = create_app()
    return app.test_client()


def test_validate_user_signal_accepts_valid_contract(client) -> None:
    response = client.post("/api/signals/validate", json={"source_code": VALID_SIGNAL})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["message"] == "校验通过"
    assert payload["diagnostics"] == []


def test_validate_user_signal_reports_contract_errors(client) -> None:
    response = client.post("/api/signals/validate", json={"source_code": "class Signal:\n    name = 'x'\n"})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["message"] == "校验失败"
    assert any("symbols" in item["message"] for item in payload["diagnostics"])
    assert any("on_bar" in item["message"] for item in payload["diagnostics"])


def test_signal_ctx_schema_api_returns_python_metadata(client, monkeypatch) -> None:
    expected = {
        "summary": "ctx docs from python",
        "core_fields": [{"name": "symbol", "type": "str", "description": "symbol field"}],
        "indicator_fields": [{"name": "alpha", "type": "float", "description": "alpha signal"}],
        "bar_fields": [{"name": "close", "type": "float", "description": "latest close"}],
        "tick_fields": [{"name": "last_price", "type": "float", "description": "latest tick"}],
        "notes": ["note from backend"],
        "example_code": "class Signal:\n    pass\n",
    }
    monkeypatch.setattr("adapters.flask_app.get_local_context_reference", lambda: expected)

    response = client.get("/api/signals/ctx-schema")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload == {"success": True, "data": expected}


def test_run_user_signal_backtest_requires_source_or_signal_id(client) -> None:
    response = client.post("/api/backtests/run-user-signal", json={})

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert "source_code 或 signal_id 必填" in payload["message"]


def test_run_user_signal_backtest_uses_runtime_result(client, monkeypatch) -> None:
    captured = {}

    def fake_run_user_signal_backtest(**kwargs):
        captured.update(kwargs)
        return {
            "market_events_processed": 3,
            "final_equity": 1000001.0,
            "realized_pnl": 1.0,
            "equity_curve": [],
            "signals": [],
            "trades": [],
            "diagnostics": [],
        }

    monkeypatch.setattr("adapters.flask_app.run_user_signal_backtest", fake_run_user_signal_backtest)

    response = client.post(
        "/api/backtests/run-user-signal",
        json={
            "source_code": VALID_SIGNAL,
            "data_source": "mock",
            "symbols": ["TEST"],
            "start_date": "20240101",
            "end_date": "20240131",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["message"] == "回测完成"
    assert payload["data"]["market_events_processed"] == 3
    assert captured["source_code"] == VALID_SIGNAL
    assert captured["data_source"] == "mock"
    assert captured["symbols"] == ["TEST"]


def test_run_user_signal_backtest_loads_source_code_from_signal_id(client, monkeypatch) -> None:
    captured = {}

    class FakeDao:
        def get_user_signal(self, signal_id: int):
            assert signal_id == 42
            return type(
                "SavedSignal",
                (),
                {"source_code": VALID_SIGNAL},
            )()

    def fake_run_user_signal_backtest(**kwargs):
        captured.update(kwargs)
        return {
            "market_events_processed": 1,
            "signals": [],
            "trades": [],
        }

    monkeypatch.setattr("adapters.flask_app.dao", FakeDao())
    monkeypatch.setattr("adapters.flask_app.run_user_signal_backtest", fake_run_user_signal_backtest)

    response = client.post(
        "/api/backtests/run-user-signal",
        json={
            "signal_id": 42,
            "data_source": "mock",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["message"] == "回测完成"
    assert payload["data"] == {
        "market_events_processed": 1,
        "signals": [],
        "trades": [],
    }
    assert captured["source_code"] == VALID_SIGNAL
    assert captured["data_source"] == "mock"
