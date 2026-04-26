"""
tushare_pbx_ma_backtest_example.py - 使用 Tushare daily 数据回测 PBX/MA 策略

环境变量：
  TUSHARE_TOKEN
  TS_CODE=000001.SZ
  START_DATE=20240101
  END_DATE=20241231
"""

from __future__ import annotations

import logging
import os

from backtest.preset_strategies import run_preset_backtest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    ts_code = os.getenv("TS_CODE", "002594.SZ")
    start_date = os.getenv("START_DATE", "20250101")
    end_date = os.getenv("END_DATE", "20251231")

    try:
        result = run_preset_backtest(
            "pbx_ma",
            data_source="tushare",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        raise SystemExit(
            "Tushare 回测无法运行，请确认 token、积分/权限和日期范围。"
            f"原始错误: {e}"
        ) from e

    logger.info("ts_code: %s", ts_code)
    logger.info("date range: %s - %s", start_date, end_date)
    logger.info("market events processed: %s", result.market_events_processed)
    logger.info("signals emitted: %s", len(result.signals))
    logger.info("trades emitted: %s", len(result.trades))
    logger.info("final equity: %.2f", result.final_equity)
    logger.info("realized pnl: %.2f", result.realized_pnl)

    for signal in result.signals:
        logger.info(
            "signal: %s %s close=%.2f pbx1=%.2f ma1=%.2f",
            signal.payload["bar_time"],
            signal.payload["side"],
            signal.payload["close"],
            signal.payload["pbx1"],
            signal.payload["ma1"],
        )


if __name__ == "__main__":
    main()
