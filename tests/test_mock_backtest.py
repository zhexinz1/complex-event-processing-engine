import json
from datetime import datetime, timedelta
from pathlib import Path

from backtest import BacktestEngine
from cep.core.events import BarEvent, OrderStatus, OrderSide, SignalType
from cep.engine.ast_engine import Operator, build_and, build_comparison


def _make_bars(symbol: str, closes: list[float]) -> list[BarEvent]:
    start = datetime(2026, 4, 1, 9, 30)
    bars: list[BarEvent] = []

    prev_close = closes[0]
    for index, close in enumerate(closes):
        bar_time = start + timedelta(minutes=index)
        bar_open = prev_close
        high = max(bar_open, close) + 0.2
        low = min(bar_open, close) - 0.2
        bars.append(
            BarEvent(
                symbol=symbol,
                freq="1m",
                open=bar_open,
                high=high,
                low=low,
                close=close,
                volume=1000 + index * 10,
                turnover=close * (1000 + index * 10),
                bar_time=bar_time,
                timestamp=bar_time,
            )
        )
        prev_close = close

    return bars


def test_backtest_engine_processes_market_signal_order_and_trade_flow() -> None:
    symbol = "600519.SH"

    # 这组 close 序列满足：
    #   1. 最后 20 根的 close > SMA(20)
    #   2. 最后 15 根在简化 RSI 实现下 < 30
    closes = [
        100.0, 99.94, 102.96, 106.85, 109.97, 106.2, 109.07, 107.78,
        106.8, 107.9, 110.91, 114.19, 112.0, 113.62, 117.2, 121.02,
        124.19, 120.4, 119.14, 118.23, 115.76, 115.51, 115.13, 116.37,
        116.75, 117.17, 115.16, 115.39, 115.39, 116.77, 117.07,
    ]

    bars = _make_bars(symbol, closes)
    rule_tree = build_and(
        build_comparison("rsi", Operator.LT, 30),
        build_comparison("close", Operator.GT, "sma"),
    )

    engine = BacktestEngine(
        initial_cash=1_000_000.0,
        default_order_quantity=2.0,
        execution_timing="current_bar",
    )
    engine.register_ast_rule(
        symbol=symbol,
        rule_tree=rule_tree,
        trigger_id="BACKTEST_RULE",
        rule_id="BACKTEST_RULE",
        bar_freq="1m",
        window_size=100,
    )
    engine.ingest_bars(bars)
    result = engine.run()

    assert result.market_events_processed == len(bars)
    assert result.signals, "Expected at least one trade signal from mock replay"
    assert result.orders, "Expected simulated broker to emit order events"
    assert result.trades, "Expected simulated broker to emit trade events"
    assert result.snapshots

    submitted_orders = [order for order in result.orders if order.status == OrderStatus.SUBMITTED]
    filled_orders = [order for order in result.orders if order.status == OrderStatus.FILLED]
    assert submitted_orders
    assert filled_orders

    last_signal = result.signals[-1]
    assert last_signal.symbol == symbol
    assert last_signal.signal_type == SignalType.TRADE_OPPORTUNITY
    assert last_signal.payload["close"] == closes[-1]

    last_trade = result.trades[-1]
    assert last_trade.symbol == symbol
    assert last_trade.side == OrderSide.BUY
    assert last_trade.quantity == 2.0
    assert last_trade.price == closes[-1]

    context = engine.get_context(symbol)
    assert context is not None
    assert context.rsi is not None
    assert context.rsi < 30
    assert context.close > context.sma

    assert result.final_equity > 0
    assert result.positions[symbol].quantity == 2.0
    assert result.trade_log_path

    log_path = Path(result.trade_log_path)
    assert log_path.exists()
    payload = json.loads(log_path.read_text(encoding="utf-8"))
    assert payload["market_events_processed"] == len(bars)
    assert payload["trades"]


def test_backtest_engine_executes_trade_on_next_bar_open_by_default() -> None:
    symbol = "600519.SH"
    bars = _make_bars(symbol, [100.0, 110.0, 120.0])

    class BuyFirstBarTrigger:
        def __init__(self, event_bus):
            self.event_bus = event_bus
            self._emitted = False

        def register(self):
            from cep.core.events import BarEvent, SignalEvent

            def on_bar(event: BarEvent) -> None:
                if self._emitted:
                    return
                self._emitted = True
                self.event_bus.publish(
                    SignalEvent(
                        source="BUY_FIRST_BAR",
                        symbol=event.symbol,
                        signal_type=SignalType.TRADE_OPPORTUNITY,
                        timestamp=event.timestamp,
                        payload={
                            "side": "BUY",
                            "price": event.close,
                            "quantity": 1,
                            "bar_time": event.bar_time.isoformat(),
                        },
                    )
                )

            self.event_bus.subscribe(BarEvent, on_bar, symbol=symbol)
            self._handler = on_bar

    engine = BacktestEngine(initial_cash=1_000_000.0, write_trade_log=False)
    trigger = BuyFirstBarTrigger(engine.event_bus)
    trigger.register()
    engine._components.append(trigger)
    engine.ingest_bars(bars)
    result = engine.run()

    assert len(result.signals) == 1
    assert len(result.trades) == 1
    assert result.trades[0].price == 100.0
    assert result.trades[0].timestamp == bars[1].timestamp
    assert result.positions[symbol].quantity == 1.0
    assert result.final_equity == 1_000_020.0


def test_backtest_engine_rejects_next_bar_signal_without_following_bar() -> None:
    symbol = "600519.SH"
    bars = _make_bars(symbol, [100.0])

    class BuyOnlyTrigger:
        def __init__(self, event_bus):
            self.event_bus = event_bus

        def register(self):
            from cep.core.events import BarEvent, SignalEvent

            def on_bar(event: BarEvent) -> None:
                self.event_bus.publish(
                    SignalEvent(
                        source="BUY_ONLY",
                        symbol=event.symbol,
                        signal_type=SignalType.TRADE_OPPORTUNITY,
                        timestamp=event.timestamp,
                        payload={
                            "side": "BUY",
                            "price": event.close,
                            "quantity": 1,
                            "bar_time": event.bar_time.isoformat(),
                        },
                    )
                )

            self.event_bus.subscribe(BarEvent, on_bar, symbol=symbol)
            self._handler = on_bar

    engine = BacktestEngine(initial_cash=1_000_000.0, write_trade_log=False)
    trigger = BuyOnlyTrigger(engine.event_bus)
    trigger.register()
    engine._components.append(trigger)
    engine.ingest_bars(bars)
    result = engine.run()

    rejected_orders = [order for order in result.orders if order.status == OrderStatus.REJECTED]
    assert result.trades == []
    assert rejected_orders
    assert rejected_orders[0].payload["reason"] == "no_next_bar"


def test_backtest_engine_rejects_buy_signal_when_cash_is_insufficient() -> None:
    symbol = "AG9999.XSGE"
    bars = _make_bars(symbol, [100.0, 101.0, 102.0])
    rule_tree = build_and(
        build_comparison("close", Operator.GT, 0),
        build_comparison("close", Operator.GT, 0),
    )

    engine = BacktestEngine(
        initial_cash=1_000.0,
        contract_multipliers={symbol: 15.0},
        default_order_quantity=10.0,
        execution_timing="current_bar",
    )
    engine.register_ast_rule(
        symbol=symbol,
        rule_tree=rule_tree,
        trigger_id="BACKTEST_RULE",
        rule_id="BACKTEST_RULE",
        bar_freq="1m",
        window_size=100,
    )
    engine.ingest_bars(bars)
    result = engine.run()

    rejected_orders = [order for order in result.orders if order.status == OrderStatus.REJECTED]
    assert rejected_orders
    assert rejected_orders[0].payload["reason"] == "insufficient_cash"
    assert result.trades == []
    assert symbol not in result.positions


def test_backtest_engine_rejects_sell_signal_without_position() -> None:
    symbol = "600519.SH"
    bars = _make_bars(symbol, [100.0])

    class SellOnlyTrigger:
        def __init__(self, event_bus):
            self.event_bus = event_bus

        def register(self):
            from cep.core.events import BarEvent, SignalEvent

            def on_bar(event: BarEvent) -> None:
                self.event_bus.publish(
                    SignalEvent(
                        source="SELL_ONLY",
                        symbol=event.symbol,
                        signal_type=SignalType.TRADE_OPPORTUNITY,
                        timestamp=event.timestamp,
                        payload={
                            "side": "SELL",
                            "price": event.close,
                            "quantity": 1,
                            "bar_time": event.bar_time.isoformat(),
                        },
                    )
                )

            self.event_bus.subscribe(BarEvent, on_bar, symbol=symbol)
            self._handler = on_bar

    engine = BacktestEngine(initial_cash=1_000_000.0, execution_timing="current_bar")
    trigger = SellOnlyTrigger(engine.event_bus)
    trigger.register()
    engine._components.append(trigger)
    engine.ingest_bars(bars)
    result = engine.run()

    rejected_orders = [order for order in result.orders if order.status == OrderStatus.REJECTED]
    assert rejected_orders
    assert rejected_orders[0].payload["reason"] == "insufficient_position"
    assert result.trades == []
    assert symbol not in result.positions


def test_backtest_engine_can_skip_trade_log(monkeypatch) -> None:
    symbol = "600519.SH"
    bars = _make_bars(symbol, [100.0, 101.0])

    def fail_if_called(_result) -> None:
        raise AssertionError("trade log writer should be skipped")

    monkeypatch.setattr("backtest.engine.write_backtest_trade_log", fail_if_called)

    engine = BacktestEngine(initial_cash=1_000_000.0, write_trade_log=False)
    engine.ingest_bars(bars, assume_sorted=True)
    result = engine.run()

    assert result.market_events_processed == len(bars)
    assert result.trade_log_path == ""


def test_backtest_engine_ingest_bars_uses_sorted_fast_path(monkeypatch) -> None:
    engine = BacktestEngine(initial_cash=1_000_000.0, write_trade_log=False)
    bars = _make_bars("600519.SH", [100.0, 101.0])
    captured: dict[str, object] = {}

    def fake_parse_bars(raw_bars, *, assume_sorted: bool = False):
        captured["parse_input"] = list(raw_bars)
        captured["parse_assume_sorted"] = assume_sorted
        return bars

    def fake_extend_sorted(events):
        captured["extend_sorted"] = list(events)

    def fake_extend(events):
        captured["extend"] = list(events)

    monkeypatch.setattr(engine.parser, "parse_bars", fake_parse_bars)
    monkeypatch.setattr(engine.event_queue, "extend_sorted", fake_extend_sorted)
    monkeypatch.setattr(engine.event_queue, "extend", fake_extend)

    engine.ingest_bars(bars, assume_sorted=True)

    assert captured["parse_input"] == bars
    assert captured["parse_assume_sorted"] is True
    assert captured["extend_sorted"] == bars
    assert "extend" not in captured
