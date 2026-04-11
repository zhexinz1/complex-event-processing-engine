"""Tushare historical data adapter."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from cep.core.events import BarEvent
import tushare as ts


def normalize_ts_code(raw_code: str) -> str:
    """Normalize common A-share user input into a Tushare ts_code."""
    code = raw_code.strip().upper()
    if not code:
        raise ValueError("股票代码不能为空")
    if "." in code:
        return code
    if not code.isdigit() or len(code) != 6:
        raise ValueError("股票代码需为 6 位数字，或完整 ts_code，如 000001.SZ")
    if code.startswith(("000", "001", "002", "003", "300", "301")):
        return f"{code}.SZ"
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        return f"{code}.SH"
    if code.startswith(
        (
            "430",
            "830",
            "831",
            "832",
            "833",
            "834",
            "835",
            "836",
            "837",
            "838",
            "839",
            "870",
            "871",
            "872",
            "873",
            "920",
        )
    ):
        return f"{code}.BJ"
    raise ValueError(f"无法推断股票代码交易所后缀: {raw_code}")


def fetch_tushare_daily_bars(
    ts_code: str,
    start_date: str,
    end_date: str,
    token: str | None = None,
) -> list[BarEvent]:
    """Fetch Tushare daily data and convert it to chronological BarEvent objects."""
    normalized_code = normalize_ts_code(ts_code)
    _validate_yyyymmdd("start_date", start_date)
    _validate_yyyymmdd("end_date", end_date)

    resolved_token = os.getenv("TUSHARE_TOKEN")
    if not resolved_token:
        raise RuntimeError("Tushare token 未找到，请设置环境变量 TUSHARE_TOKEN")
    try:
        pro = ts.pro_api(resolved_token)
        df = pro.daily(
            ts_code=normalized_code,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as e:
        raise RuntimeError(
            f"Tushare daily 数据获取失败，请确认 token、积分/权限和日期范围。原始错误: {e}"
        ) from e

    if df is None or df.empty:
        raise ValueError(f"Tushare 未返回数据: {normalized_code} {start_date}-{end_date}")

    required_columns = {"ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"Tushare daily 返回缺少字段: {sorted(missing)}")

    rows: list[dict[str, Any]] = df.sort_values("trade_date").to_dict("records", orient="records")  # type: ignore[assignment]
    bars: list[BarEvent] = []
    for row in rows:
        trade_date = datetime.strptime(str(row["trade_date"]), "%Y%m%d")
        # Daily bars are considered complete after the A-share close.
        bar_time = trade_date.replace(hour=15, minute=0)
        bars.append(
            BarEvent(
                symbol=str(row["ts_code"]),
                freq="1d",
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(round(float(row["vol"]))),
                turnover=float(row["amount"]) * 1000.0,
                bar_time=bar_time,
                timestamp=bar_time,
            )
        )

    return bars


def _validate_yyyymmdd(name: str, value: str) -> None:
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as e:
        raise ValueError(f"{name} 必须是 YYYYMMDD 格式") from e
