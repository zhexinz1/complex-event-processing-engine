from datetime import datetime, timedelta

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

    engine = BacktestEngine(initial_cash=1_000_000.0, default_order_quantity=2.0)
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
