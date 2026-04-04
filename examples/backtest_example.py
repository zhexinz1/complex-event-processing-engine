"""
backtest_example.py — 使用 backtest 模块执行事件驱动回测

演示：
  1. 构造历史 Bar 数据
  2. 注册 AST 规则
  3. 运行回测引擎
  4. 查看 Signal / Order / Trade / Equity 输出
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from backtest import BacktestEngine
from cep.core.events import BarEvent
from cep.engine.ast_engine import Operator, build_and, build_comparison

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def make_bars(symbol: str, closes: list[float]) -> list[BarEvent]:
    """生成一段可回放的 mock Bar 数据。"""
    start = datetime(2026, 4, 1, 9, 30)
    bars: list[BarEvent] = []

    prev_close = closes[0]
    for index, close in enumerate(closes):
        bar_time = start + timedelta(minutes=index)
        bars.append(
            BarEvent(
                symbol=symbol,
                freq="1m",
                open=prev_close,
                high=max(prev_close, close) + 0.2,
                low=min(prev_close, close) - 0.2,
                close=close,
                volume=1000 + index * 10,
                turnover=close * (1000 + index * 10),
                bar_time=bar_time,
                timestamp=bar_time,
            )
        )
        prev_close = close

    return bars


def main() -> None:
    symbol = "600519.SH"
    closes = [
        100.0, 99.94, 102.96, 106.85, 109.97, 106.2, 109.07, 107.78,
        106.8, 107.9, 110.91, 114.19, 112.0, 113.62, 117.2, 121.02,
        124.19, 120.4, 119.14, 118.23, 115.76, 115.51, 115.13, 116.37,
        116.75, 117.17, 115.16, 115.39, 115.39, 116.77, 117.07,
    ]
    bars = make_bars(symbol, closes)

    rule_tree = build_and(
        build_comparison("rsi", Operator.LT, 30),
        build_comparison("close", Operator.GT, "sma"),
    )

    engine = BacktestEngine(
        initial_cash=1_000_000.0,
        default_order_quantity=2.0,
        aggregate_freqs=["5m"],
    )
    engine.register_ast_rule(
        symbol=symbol,
        rule_tree=rule_tree,
        trigger_id="BACKTEST_RULE",
        rule_id="BACKTEST_RULE",
        bar_freq="1m",
    )
    engine.ingest_bars(bars)

    result = engine.run()

    logger.info("market events processed: %s", result.market_events_processed)
    logger.info("signals emitted: %s", len(result.signals))
    logger.info("orders emitted: %s", len(result.orders))
    logger.info("trades emitted: %s", len(result.trades))
    logger.info("final cash: %.2f", result.final_cash)
    logger.info("final market value: %.2f", result.final_market_value)
    logger.info("final equity: %.2f", result.final_equity)

    if result.signals:
        logger.info("last signal: %s", result.signals[-1])
    if result.trades:
        logger.info("last trade: %s", result.trades[-1])
    if symbol in result.positions:
        logger.info("final position: %s", result.positions[symbol])


if __name__ == "__main__":
    main()
