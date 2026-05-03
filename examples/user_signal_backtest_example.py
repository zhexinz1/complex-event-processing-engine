"""
Run a researcher-authored user signal against existing mock stock bars.

Usage:
    uv run -m examples.user_signal_backtest_example
"""

from __future__ import annotations

import logging

from signals import run_user_signal_backtest


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


MOCK_USER_SIGNAL_CODE = '''
class Signal:
    name = "贵州茅台RSI均值回归"
    symbols = ["600519.SH"]
    bar_freq = "1m"

    def __init__(self, ctx):
        self.ctx = ctx
        self.in_position = False

    def on_bar(self, bar):
        rsi = self.ctx.rsi
        if rsi is None:
            return None

        if not self.in_position and rsi < 30:
            self.in_position = True
            return {
                "side": "BUY",
                "reason": "rsi_oversold",
                "price": bar.close,
                "quantity": 100,
                "rsi": round(rsi, 2),
            }

        if self.in_position and rsi > 70:
            self.in_position = False
            return {
                "side": "SELL",
                "reason": "rsi_recovered",
                "price": bar.close,
                "quantity": 100,
                "rsi": round(rsi, 2),
            }

        return None
'''


def main() -> None:
    result = run_user_signal_backtest(
        source_code=MOCK_USER_SIGNAL_CODE,
        data_source="mock",
        initial_cash=1_000_000.0,
    )

    logger.info("Backtest summary")
    logger.info("  market_events_processed=%s", result["market_events_processed"])
    logger.info("  signals=%s", len(result["signals"]))
    logger.info("  trades=%s", len(result["trades"]))
    logger.info("  final_cash=%s", result["final_cash"])
    logger.info("  final_market_value=%s", result["final_market_value"])
    logger.info("  final_equity=%s", result["final_equity"])
    logger.info("  diagnostics=%s", result["diagnostics"])

    for index, signal in enumerate(result["signals"], start=1):
        payload = signal["payload"]
        logger.info(
            "Signal %s: time=%s symbol=%s side=%s price=%s rsi=%s reason=%s",
            index,
            payload.get("bar_time"),
            signal["symbol"],
            payload.get("side"),
            payload.get("price"),
            payload.get("rsi"),
            payload.get("reason"),
        )

    if result["trades"]:
        logger.info("Last trade: %s", result["trades"][-1])
    if result["positions"]:
        logger.info("Final positions: %s", result["positions"])


if __name__ == "__main__":
    main()
