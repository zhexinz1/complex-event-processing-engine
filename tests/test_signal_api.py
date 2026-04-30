from pathlib import Path
import sys
from datetime import datetime

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adapters.flask_app import create_app
from database.models import UserSignalDefinition, UserSignalStatus


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

AU_SIGNAL = '''
class Signal:
    name = "Gold RSI"
    symbols = ["AU9999.XSGE"]
    bar_freq = "1m"

    def __init__(self, ctx):
        self.ctx = ctx

    def on_bar(self, bar):
        if self.ctx.rsi is not None and self.ctx.rsi < 30:
            return {"side": "BUY", "reason": "oversold", "price": bar.close}
        return None
'''

AG_SIGNAL = '''
class Signal:
    name = "Silver RSI"
    symbols = ["AG9999.XSGE"]
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


def test_run_user_signal_backtest_passes_write_trade_log_flag(client, monkeypatch) -> None:
    captured = {}

    def fake_run_user_signal_backtest(**kwargs):
        captured.update(kwargs)
        return {
            "market_events_processed": 1,
            "signals": [],
            "trades": [],
            "equity_curve": [],
            "diagnostics": [],
            "final_equity": 1_000_000.0,
            "realized_pnl": 0.0,
        }

    monkeypatch.setattr("adapters.flask_app.run_user_signal_backtest", fake_run_user_signal_backtest)

    response = client.post(
        "/api/backtests/run-user-signal",
        json={
            "source_code": VALID_SIGNAL,
            "data_source": "mock",
            "write_trade_log": False,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert captured["write_trade_log"] is False


def test_run_user_signal_backtest_passes_execution_timing_flag(client, monkeypatch) -> None:
    captured = {}

    def fake_run_user_signal_backtest(**kwargs):
        captured.update(kwargs)
        return {
            "market_events_processed": 1,
            "signals": [],
            "trades": [],
            "equity_curve": [],
            "diagnostics": [],
            "final_equity": 1_000_000.0,
            "realized_pnl": 0.0,
        }

    monkeypatch.setattr("adapters.flask_app.run_user_signal_backtest", fake_run_user_signal_backtest)

    response = client.post(
        "/api/backtests/run-user-signal",
        json={
            "source_code": VALID_SIGNAL,
            "data_source": "mock",
            "execution_timing": "current_bar",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert captured["execution_timing"] == "current_bar"


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


def test_create_user_signal_persists_adjusted_main_contract_signal(client, monkeypatch) -> None:
    saved_signals: dict[int, UserSignalDefinition] = {}

    class FakeDao:
        def create_user_signal(self, signal: UserSignalDefinition) -> int:
            saved_signals[7] = UserSignalDefinition(
                id=7,
                name=signal.name,
                symbols=list(signal.symbols),
                bar_freq=signal.bar_freq,
                source_code=signal.source_code,
                status=signal.status,
                created_by=signal.created_by,
                created_at=None,
                updated_at=None,
            )
            return 7

        def get_user_signal(self, signal_id: int):
            return saved_signals.get(signal_id)

    monkeypatch.setattr("adapters.flask_app.dao", FakeDao())

    response = client.post(
        "/api/signals",
        json={
            "name": "Gold RSI",
            "symbols": ["AU9999.XSGE"],
            "bar_freq": "1m",
            "source_code": AU_SIGNAL,
            "created_by": "research",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["message"] == "信号已保存"
    assert payload["data"]["id"] == 7
    assert payload["data"]["symbols"] == ["AU9999.XSGE"]
    assert saved_signals[7].symbols == ["AU9999.XSGE"]


def test_run_user_signal_backtest_with_saved_au_signal_on_adjusted_main_contract(client, monkeypatch) -> None:
    captured = {}

    class FakeDao:
        def get_user_signal(self, signal_id: int):
            assert signal_id == 11
            return UserSignalDefinition(
                id=11,
                name="Gold RSI",
                symbols=["AU9999.XSGE"],
                bar_freq="1m",
                source_code=AU_SIGNAL,
                status=UserSignalStatus.DISABLED,
                created_by="research",
                created_at=datetime(2026, 4, 1, 9, 30),
                updated_at=datetime(2026, 4, 1, 9, 30),
            )

    def fake_run_user_signal_backtest(**kwargs):
        captured.update(kwargs)
        return {
            "market_events_processed": 4,
            "final_equity": 1000010.0,
            "realized_pnl": 10.0,
            "equity_curve": [],
            "signals": [{"symbol": "AU9999.XSGE", "timestamp": "2025-06-09T09:01:00", "payload": {"side": "BUY"}}],
            "trades": [],
            "diagnostics": [],
        }

    monkeypatch.setattr("adapters.flask_app.dao", FakeDao())
    monkeypatch.setattr("adapters.flask_app.run_user_signal_backtest", fake_run_user_signal_backtest)

    response = client.post(
        "/api/backtests/run-user-signal",
        json={
            "signal_id": 11,
            "data_source": "adjusted_main_contract",
            "symbols": ["AU9999.XSGE"],
            "start_date": "20250601",
            "end_date": "20250630",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["signals"][0]["symbol"] == "AU9999.XSGE"
    assert captured["source_code"] == AU_SIGNAL
    assert captured["data_source"] == "adjusted_main_contract"
    assert captured["symbols"] == ["AU9999.XSGE"]
    assert captured["start_date"] == "20250601"
    assert captured["end_date"] == "20250630"


def test_run_user_signal_backtest_with_inline_ag_signal_on_adjusted_main_contract(client, monkeypatch) -> None:
    captured = {}

    def fake_run_user_signal_backtest(**kwargs):
        captured.update(kwargs)
        return {
            "market_events_processed": 5,
            "final_equity": 1000020.0,
            "realized_pnl": 20.0,
            "equity_curve": [],
            "signals": [{"symbol": "AG9999.XSGE", "timestamp": "2025-06-10T09:02:00", "payload": {"side": "BUY"}}],
            "trades": [],
            "diagnostics": [],
        }

    monkeypatch.setattr("adapters.flask_app.run_user_signal_backtest", fake_run_user_signal_backtest)

    response = client.post(
        "/api/backtests/run-user-signal",
        json={
            "source_code": AG_SIGNAL,
            "data_source": "adjusted_main_contract",
            "symbols": ["AG9999.XSGE"],
            "start_date": "20250601",
            "end_date": "20250630",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["signals"][0]["symbol"] == "AG9999.XSGE"
    assert captured["source_code"] == AG_SIGNAL
    assert captured["data_source"] == "adjusted_main_contract"
    assert captured["symbols"] == ["AG9999.XSGE"]
