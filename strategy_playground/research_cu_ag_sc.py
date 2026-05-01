from __future__ import annotations

import argparse
import os
from math import sqrt
from statistics import mean, pstdev
from typing import Any

import requests


START_DATE = "20240101"
END_DATE = "20260422"
INITIAL_CASH = 1_000_000.0
SYMBOLS = ["CU9999.XSGE", "AG9999.XSGE", "SC9999.XINE"]
OIL_MULTIPLIER = 1000.0
DEFAULT_BASE_URL = os.environ.get("CEP_API_BASE_URL", "http://localhost:5000")
BACKTEST_PATH = "/api/backtests/run-user-signal"


BUY_HOLD_SOURCE = '''
class Signal:
    name = "SC Buy Hold Baseline"
    symbols = ["SC9999.XINE"]
    bar_freq = "1m"
    invested = False

    def __init__(self, ctx):
        self.ctx = ctx

    def on_bar(self, bar):
        cls = self.__class__
        if cls.invested:
            return None
        cls.invested = True
        return {"side": "BUY", "quantity": 1, "reason": "buy_hold_oil", "price": bar.close}
'''


def build_lagged_ratio_source(
    *,
    signal_name: str,
    buy_reason: str,
    sell_reason: str,
    min_hold_bars: int | None = None,
) -> str:
    hold_state = ""
    hold_tick = ""
    hold_reset = ""
    hold_gate = ""
    hold_payload = ""
    if min_hold_bars is not None:
        hold_state = f"    min_hold_bars = {min_hold_bars}\n    holding_bars = 0\n"
        hold_tick = "\n        if cls.invested:\n            cls.holding_bars = cls.holding_bars + 1\n"
        hold_reset = "\n            cls.holding_bars = 0"
        hold_gate = "\n            and cls.holding_bars >= cls.min_hold_bars"
        hold_payload = '\n                "holding_bars": cls.holding_bars,'

    return f'''
class Signal:
    name = "{signal_name}"
    symbols = ["CU9999.XSGE", "AG9999.XSGE", "SC9999.XINE"]
    bar_freq = "1m"
    last_cu = 0.0
    last_ag = 0.0
    pending_ratio = 0.0
    ratios = []
    invested = False
    lookback = 240
    entry_threshold = 0.004
    exit_threshold = 0.0
{hold_state}    confirmation_bars = 3
    positive_count = 0
    negative_count = 0

    def __init__(self, ctx):
        self.ctx = ctx

    def on_bar(self, bar):
        cls = self.__class__
        if bar.symbol == "CU9999.XSGE":
            cls.last_cu = bar.close
            return None
        if bar.symbol == "AG9999.XSGE":
            cls.last_ag = bar.close
            return None
        if bar.symbol != "SC9999.XINE":
            return None{hold_tick}

        ratio = cls.pending_ratio
        if cls.last_cu > 0 and cls.last_ag > 0:
            cls.pending_ratio = cls.last_cu / cls.last_ag
        if ratio <= 0:
            return None

        cls.ratios.append(ratio)
        if len(cls.ratios) > 2000:
            cls.ratios.pop(0)
        if len(cls.ratios) <= cls.lookback:
            return None

        momentum = (ratio / cls.ratios[-cls.lookback - 1]) - 1.0
        if momentum > cls.entry_threshold:
            cls.positive_count = cls.positive_count + 1
        else:
            cls.positive_count = 0
        if momentum < cls.exit_threshold:
            cls.negative_count = cls.negative_count + 1
        else:
            cls.negative_count = 0

        if not cls.invested and cls.positive_count >= cls.confirmation_bars:
            cls.invested = True{hold_reset}
            return {{
                "side": "BUY",
                "quantity": 1,
                "reason": "{buy_reason}",
                "price": bar.close,
                "ratio": ratio,
                "ratio_momentum": momentum,
            }}
        if (
            cls.invested{hold_gate}
            and cls.negative_count >= cls.confirmation_bars
        ):
            cls.invested = False
            return {{
                "side": "SELL",
                "quantity": 1,
                "reason": "{sell_reason}",
                "price": bar.close,
                "ratio": ratio,
                "ratio_momentum": momentum,{hold_payload}
            }}
        return None
'''


EXPERIMENTS = {
    "buy_hold_sc": (BUY_HOLD_SOURCE, ["SC9999.XINE"]),
    "lagged_ratio_three_bar_confirm": (
        build_lagged_ratio_source(
            signal_name="CU AG Lagged Ratio Momentum Confirmed",
            buy_reason="lagged_ratio_momentum_three_bar_confirmed",
            sell_reason="lagged_ratio_momentum_three_bar_exit",
        ),
        SYMBOLS,
    ),
    "lagged_ratio_min_hold": (
        build_lagged_ratio_source(
            signal_name="CU AG Lagged Ratio Momentum Confirmed Min Hold",
            buy_reason="lagged_ratio_momentum_three_bar_confirmed_min_hold",
            sell_reason="lagged_ratio_momentum_three_bar_exit_after_min_hold",
            min_hold_bars=120,
        ),
        SYMBOLS,
    ),
}


def run_api(
    base_url: str,
    name: str,
    source_code: str,
    symbols: list[str],
    *,
    start_date: str,
    end_date: str,
    initial_cash: float,
    execution_timing: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    body = {
        "source_code": source_code,
        "data_source": "adjusted_main_contract",
        "start_date": start_date,
        "end_date": end_date,
        "initial_cash": initial_cash,
        "write_trade_log": False,
        "execution_timing": execution_timing,
    }
    if len(symbols) > 1:
        body["symbols"] = symbols

    endpoint = f"{base_url.rstrip('/')}{BACKTEST_PATH}"
    response = requests.post(endpoint, json=body, timeout=timeout_seconds)
    payload = response.json()
    if response.status_code != 200 or not payload.get("success"):
        raise RuntimeError(f"{name} failed: status={response.status_code} payload={payload}")
    return payload["data"]


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    curve = data["equity_curve"]
    equities = [float(point["equity"]) for point in curve]
    max_equity = equities[0] if equities else INITIAL_CASH
    max_drawdown = 0.0
    for equity in equities:
        if equity > max_equity:
            max_equity = equity
        drawdown = (equity / max_equity) - 1.0 if max_equity else 0.0
        if drawdown < max_drawdown:
            max_drawdown = drawdown

    daily_equity: dict[str, float] = {}
    for point in curve:
        daily_equity[str(point["timestamp"])[:10]] = float(point["equity"])
    daily_values = [daily_equity[key] for key in sorted(daily_equity)]
    daily_returns = [
        (daily_values[index] / daily_values[index - 1]) - 1.0
        for index in range(1, len(daily_values))
        if daily_values[index - 1] > 0
    ]
    sharpe = 0.0
    if len(daily_returns) > 1 and pstdev(daily_returns) > 0:
        sharpe = (mean(daily_returns) / pstdev(daily_returns)) * sqrt(252)

    exposure = 0.0
    if curve:
        exposure = sum(1 for point in curve if abs(float(point["market_value"])) > 0) / len(curve)

    trades = data["trades"]
    turnover = sum(float(trade["price"]) * float(trade["quantity"]) * OIL_MULTIPLIER for trade in trades) / INITIAL_CASH
    closed_pnls = []
    open_buy: dict[str, Any] | None = None
    for trade in trades:
        side = str(trade["side"]).upper()
        if side == "BUY":
            open_buy = trade
        elif side == "SELL" and open_buy is not None:
            pnl = (
                float(trade["price"]) - float(open_buy["price"])
            ) * float(trade["quantity"]) * OIL_MULTIPLIER
            closed_pnls.append(pnl)
            open_buy = None
    wins = [pnl for pnl in closed_pnls if pnl > 0]
    losses = [pnl for pnl in closed_pnls if pnl <= 0]

    return {
        "events": data["market_events_processed"],
        "signals": len(data["signals"]),
        "trades": len(trades),
        "final_equity": float(data["final_equity"]),
        "total_return": (float(data["final_equity"]) / INITIAL_CASH) - 1.0,
        "max_drawdown": max_drawdown,
        "daily_sharpe": sharpe,
        "win_rate": (len(wins) / len(closed_pnls)) if closed_pnls else 0.0,
        "avg_win": mean(wins) if wins else 0.0,
        "avg_loss": mean(losses) if losses else 0.0,
        "closed_trades": len(closed_pnls),
        "exposure": exposure,
        "turnover": turnover,
        "diagnostics": data["diagnostics"],
        "sample_signals": data["signals"][:3],
        "sample_trades": trades[:6],
    }


def print_summary(name: str, metrics: dict[str, Any]) -> None:
    print(f"## {name}")
    for key in [
        "events",
        "signals",
        "trades",
        "closed_trades",
        "final_equity",
        "total_return",
        "max_drawdown",
        "daily_sharpe",
        "win_rate",
        "avg_win",
        "avg_loss",
        "exposure",
        "turnover",
    ]:
        print(f"{key}: {metrics[key]}")
    print(f"diagnostics: {metrics['diagnostics']}")
    print(f"sample_signals: {metrics['sample_signals']}")
    print(f"sample_trades: {metrics['sample_trades']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backtest CU/AG ratio signals against SC through a running Flask API server."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Flask API base URL.")
    parser.add_argument("--start-date", default=START_DATE)
    parser.add_argument("--end-date", default=END_DATE)
    parser.add_argument("--initial-cash", type=float, default=INITIAL_CASH)
    parser.add_argument(
        "--execution-timing",
        choices=["current_bar", "next_bar"],
        default="next_bar",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=600.0,
        help="HTTP timeout per backtest request.",
    )
    parser.add_argument(
        "--only",
        choices=sorted(EXPERIMENTS),
        action="append",
        help="Run only the named experiment. Can be provided more than once.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    experiment_names = args.only or list(EXPERIMENTS)
    for name in experiment_names:
        source, symbols = EXPERIMENTS[name]
        data = run_api(
            args.base_url,
            name,
            source,
            symbols,
            start_date=args.start_date,
            end_date=args.end_date,
            initial_cash=args.initial_cash,
            execution_timing=args.execution_timing,
            timeout_seconds=args.timeout_seconds,
        )
        print_summary(name, summarize(data))


if __name__ == "__main__":
    main()
