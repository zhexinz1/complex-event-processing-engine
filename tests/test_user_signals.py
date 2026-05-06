import json
from datetime import datetime, timedelta

import pytest

from cep.core.event_bus import EventBus
from cep.core.events import BarEvent, SignalEvent
from signals import (
    SignalContractValidator,
    UserSignalTrigger,
    load_signal_class,
    run_user_signal_backtest,
)
from signals.runtime import deserialize_bar_event_payload, serialize_bar_event


VALID_SIGNAL = """
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
"""


def make_bar(index: int, close: float, symbol: str = "TEST") -> BarEvent:
    timestamp = datetime(2026, 4, 1, 9, 30) + timedelta(minutes=index)
    return BarEvent(
        symbol=symbol,
        freq="1m",
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=100,
        turnover=close * 100,
        bar_time=timestamp,
        timestamp=timestamp,
    )


def test_validator_accepts_valid_signal_contract():
    is_valid, diagnostics = SignalContractValidator().validate(VALID_SIGNAL)

    assert is_valid
    assert diagnostics == []


def test_validator_rejects_missing_contract_parts():
    is_valid, diagnostics = SignalContractValidator().validate(
        "class Signal:\n    name = 'x'\n"
    )

    assert not is_valid
    assert any("symbols" in item.message for item in diagnostics)
    assert any("on_bar" in item.message for item in diagnostics)


def test_loader_blocks_imports():
    source = VALID_SIGNAL + "\nimport os\n"

    with pytest.raises(ValueError):
        load_signal_class(source)


@pytest.mark.parametrize(
    "payload",
    [
        "return ().__class__",
        "return type.__subclasses__()",
        "return self.__dict__",
    ],
)
def test_validator_blocks_dunder_attribute_access(payload: str) -> None:
    source = VALID_SIGNAL.replace(
        'return {"side": "BUY", "reason": "oversold", "price": bar.close}', payload
    )

    is_valid, diagnostics = SignalContractValidator().validate(source)

    assert not is_valid
    assert any("dunder attribute access" in item.message for item in diagnostics)


def test_user_signal_trigger_emits_signal_event():
    source = """
class Signal:
    name = "Close below"
    symbols = ["TEST"]
    bar_freq = "1m"

    def __init__(self, ctx):
        self.ctx = ctx

    def on_bar(self, bar):
        if bar.close < 10:
            return {"side": "BUY", "reason": "cheap", "price": bar.close}
        return None
"""
    signal_class, _ = load_signal_class(source)
    bus = EventBus()
    captured: list[SignalEvent] = []

    def on_signal(event: SignalEvent) -> None:
        captured.append(event)

    bus.subscribe(SignalEvent, on_signal)
    trigger = UserSignalTrigger(bus, "TEST_SIGNAL", signal_class)
    trigger.register()

    bar = make_bar(0, 9.0)
    bus.publish(bar)

    assert len(captured) == 1
    assert captured[0].symbol == "TEST"
    assert captured[0].timestamp == bar.timestamp
    assert captured[0].payload["side"] == "BUY"


def test_user_signal_backtest_returns_result_payload():
    data = run_user_signal_backtest(
        source_code=VALID_SIGNAL.replace(
            'symbols = ["TEST"]', 'symbols = ["600519.SH"]'
        ),
        data_source="mock",
    )

    assert data["market_events_processed"] > 0
    assert "equity_curve" in data
    assert "signals" in data
    assert "diagnostics" in data


def test_user_signal_backtest_supports_adjusted_main_contract(monkeypatch):
    def fake_fetch_adjusted_main_contract_bars(
        symbol: str, start_date: str, end_date: str
    ):
        assert symbol == "AU9999.XSGE"
        assert start_date == "20250601"
        assert end_date == "20250630"
        return [
            make_bar(index, close, symbol=symbol)
            for index, close in enumerate([10.0, 9.0, 8.0, 7.0])
        ]

    monkeypatch.setattr(
        "signals.runtime.fetch_adjusted_main_contract_bars",
        fake_fetch_adjusted_main_contract_bars,
    )

    data = run_user_signal_backtest(
        source_code=VALID_SIGNAL.replace(
            'symbols = ["TEST"]', 'symbols = ["AU9999.XSGE"]'
        ),
        data_source="adjusted_main_contract",
        symbols=["AU9999.XSGE"],
        start_date="20250601",
        end_date="20250630",
    )

    assert data["market_events_processed"] == 4
    assert "equity_curve" in data
    assert "signals" in data
    assert data["diagnostics"] == []


def test_user_signal_backtest_uses_futures_contract_multiplier(monkeypatch):
    source = """
class Signal:
    name = "Silver flip"
    symbols = ["AG9999.XSGE"]
    bar_freq = "1m"

    def __init__(self, ctx):
        self.ctx = ctx
        self.step = 0

    def on_bar(self, bar):
        self.step += 1
        if self.step == 1:
            return {"side": "BUY", "reason": "enter", "price": bar.close, "quantity": 2}
        if self.step == 2:
            return {"side": "SELL", "reason": "exit", "price": bar.close, "quantity": 2}
        return None
"""

    def fake_fetch_adjusted_main_contract_bars(
        symbol: str, start_date: str, end_date: str
    ):
        assert symbol == "AG9999.XSGE"
        assert start_date == "20250601"
        assert end_date == "20250630"
        return [
            make_bar(index, close, symbol=symbol)
            for index, close in enumerate([100.0, 110.0])
        ]

    monkeypatch.setattr(
        "signals.runtime.fetch_adjusted_main_contract_bars",
        fake_fetch_adjusted_main_contract_bars,
    )

    data = run_user_signal_backtest(
        source_code=source,
        data_source="adjusted_main_contract",
        start_date="20250601",
        end_date="20250630",
        initial_cash=1_000_000.0,
        execution_timing="current_bar",
    )

    assert data["market_events_processed"] == 2
    assert data["realized_pnl"] == 300.0
    assert data["final_cash"] == 1_000_300.0
    assert data["final_equity"] == 1_000_300.0


def test_user_signal_backtest_executes_on_next_bar_open(monkeypatch):
    source = """
class Signal:
    name = "Silver flip"
    symbols = ["AG9999.XSGE"]
    bar_freq = "1m"

    def __init__(self, ctx):
        self.ctx = ctx
        self.step = 0

    def on_bar(self, bar):
        self.step += 1
        if self.step == 1:
            return {"side": "BUY", "reason": "enter", "price": bar.close, "quantity": 2}
        if self.step == 2:
            return {"side": "SELL", "reason": "exit", "price": bar.close, "quantity": 2}
        return None
"""

    def fake_fetch_adjusted_main_contract_bars(
        symbol: str, start_date: str, end_date: str
    ):
        return [
            make_bar(index, close, symbol=symbol)
            for index, close in enumerate([100.0, 110.0, 120.0])
        ]

    monkeypatch.setattr(
        "signals.runtime.fetch_adjusted_main_contract_bars",
        fake_fetch_adjusted_main_contract_bars,
    )

    data = run_user_signal_backtest(
        source_code=source,
        data_source="adjusted_main_contract",
        start_date="20250601",
        end_date="20250630",
        initial_cash=1_000_000.0,
        execution_timing="next_bar",
    )

    assert data["trades"][0]["price"] == 110.0
    assert (
        data["trades"][0]["timestamp"]
        == make_bar(1, 110.0, symbol="AG9999.XSGE").timestamp.isoformat()
    )
    assert data["trades"][1]["price"] == 120.0
    assert (
        data["trades"][1]["timestamp"]
        == make_bar(2, 120.0, symbol="AG9999.XSGE").timestamp.isoformat()
    )
    assert data["realized_pnl"] == 300.0
    assert data["final_equity"] == 1_000_300.0


def test_runtime_exception_is_captured_without_stopping_bus():
    source = """
class Signal:
    name = "Broken"
    symbols = ["TEST"]
    bar_freq = "1m"

    def __init__(self, ctx):
        self.ctx = ctx

    def on_bar(self, bar):
        return 1 / 0
"""
    signal_class, _ = load_signal_class(source)
    bus = EventBus()
    trigger = UserSignalTrigger(bus, "BROKEN_SIGNAL", signal_class)
    trigger.register()

    bus.publish(make_bar(0, 9.0))
    bus.publish(make_bar(1, 8.0))

    assert len(trigger.diagnostics) == 2
    assert all("on_bar failed" in item.message for item in trigger.diagnostics)


def test_bar_event_json_payload_round_trips_for_live_monitor() -> None:
    bar = make_bar(3, 12.5, symbol="AU9999.XSGE")

    decoded = deserialize_bar_event_payload(
        json.dumps(serialize_bar_event(bar)).encode("utf-8")
    )

    assert decoded == bar


def test_bar_event_json_payload_rejects_missing_required_fields() -> None:
    with pytest.raises(ValueError, match="missing fields"):
        deserialize_bar_event_payload(json.dumps({"symbol": "AU9999.XSGE"}))
