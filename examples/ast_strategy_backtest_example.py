"""
ast_strategy_backtest_example.py — insert an AST strategy and backtest it.

This example treats the strategy as a JSON-like dict, as if it came from a UI,
config file, or API request. The AST rule is intentionally simple:

    close > sma AND rsi > 55

The current AstRuleTrigger is a stateless signal rule, so each bar satisfying the
condition emits a BUY trade opportunity. Stateful entry/exit rules still belong
in a purpose-built trigger.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from backtest import BacktestEngine
from cep.core.events import BarEvent
from cep.engine.ast_engine import parse_ast_from_dict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


AST_MOMENTUM_STRATEGY: dict[str, Any] = {
    "strategy_id": "ast_momentum_close_above_sma",
    "symbol": "600519.SH",
    "bar_freq": "1m",
    "initial_cash": 1_000_000.0,
    "quantity": 10.0,
    "rule": {
        "type": "logical",
        "op": "AND",
        "operands": [
            {
                "type": "operator",
                "op": ">",
                "left": {"type": "var", "name": "close"},
                "right": {"type": "var", "name": "sma"},
            },
            {
                "type": "operator",
                "op": ">",
                "left": {"type": "var", "name": "rsi"},
                "right": {"type": "const", "value": 55},
            },
        ],
    },
}


def make_momentum_bars(symbol: str) -> list[BarEvent]:
    """Create mock bars that warm up SMA/RSI, then trend upward."""
    closes = [
        100.0,
        99.8,
        100.1,
        99.9,
        100.2,
        100.0,
        100.3,
        100.1,
        100.4,
        100.2,
        100.5,
        100.3,
        100.6,
        100.4,
        100.7,
        100.5,
        100.8,
        100.6,
        100.9,
        100.7,
        101.0,
        101.8,
        102.7,
        103.5,
        104.4,
        105.2,
        106.1,
        107.0,
    ]
    start = datetime(2026, 4, 1, 9, 30)
    bars: list[BarEvent] = []

    previous_close = closes[0]
    for index, close in enumerate(closes):
        bar_time = start + timedelta(minutes=index)
        bars.append(
            BarEvent(
                symbol=symbol,
                freq="1m",
                open=previous_close,
                high=max(previous_close, close) + 0.2,
                low=min(previous_close, close) - 0.2,
                close=close,
                volume=1_000 + index * 10,
                turnover=close * (1_000 + index * 10),
                bar_time=bar_time,
                timestamp=bar_time,
            )
        )
        previous_close = close

    return bars


def run_ast_strategy_backtest(strategy_spec: dict[str, Any]) -> None:
    """Parse an AST strategy spec, register it, and run a mock backtest."""
    symbol = str(strategy_spec["symbol"])
    strategy_id = str(strategy_spec["strategy_id"])
    bar_freq = str(strategy_spec["bar_freq"])
    rule_tree = parse_ast_from_dict(strategy_spec["rule"])

    engine = BacktestEngine(
        initial_cash=float(strategy_spec["initial_cash"]),
        default_order_quantity=float(strategy_spec["quantity"]),
    )
    engine.register_ast_rule(
        symbol=symbol,
        rule_tree=rule_tree,
        trigger_id=strategy_id,
        rule_id=strategy_id,
        bar_freq=bar_freq,
    )
    engine.ingest_bars(make_momentum_bars(symbol))
    result = engine.run()

    logger.info("strategy: %s", strategy_id)
    logger.info("rule: %s", rule_tree)
    logger.info("market events processed: %s", result.market_events_processed)
    logger.info("signals emitted: %s", len(result.signals))
    logger.info("trades emitted: %s", len(result.trades))
    logger.info("final cash: %.2f", result.final_cash)
    logger.info("final market value: %.2f", result.final_market_value)
    logger.info("final equity: %.2f", result.final_equity)

    if result.signals:
        first_signal = result.signals[0]
        logger.info(
            "first signal: %s close=%.2f",
            first_signal.timestamp.isoformat(),
            first_signal.payload["close"],
        )
    if symbol in result.positions:
        logger.info("final position: %s", result.positions[symbol])


def main() -> None:
    run_ast_strategy_backtest(AST_MOMENTUM_STRATEGY)


if __name__ == "__main__":
    main()
