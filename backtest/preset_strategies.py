"""Preset strategy registry facade and result serialization."""

from __future__ import annotations

from typing import Any

from .models import BacktestResult
from .presets import (
    CROSS_SECTION_MOMENTUM_CLOSES,
    PBX_MA_PRESET_CLOSES,
    PRESET_STRATEGIES,
    PRESET_STRATEGY_RUNNERS,
    CrossSectionMomentumTrigger,
    PbxMaEmotionTrigger,
    TDDeMark913Trigger,
    fetch_adjusted_main_contract_bars,
    fetch_adjusted_main_contract_bars_multi,
    fetch_cross_section_tushare_bars,
    fetch_tushare_daily_bars,
    make_cross_section_mock_bars,
    make_mock_bars,
    normalize_symbol_group,
    normalize_ts_code,
    run_cross_section_momentum_backtest,
    run_pbx_ma_backtest,
    run_preset_backtest,
    run_td_demark_9_13_backtest,
)

__all__ = [
    "CROSS_SECTION_MOMENTUM_CLOSES",
    "CrossSectionMomentumTrigger",
    "PBX_MA_PRESET_CLOSES",
    "PRESET_STRATEGIES",
    "PRESET_STRATEGY_RUNNERS",
    "PbxMaEmotionTrigger",
    "TDDeMark913Trigger",
    "fetch_adjusted_main_contract_bars",
    "fetch_adjusted_main_contract_bars_multi",
    "fetch_cross_section_tushare_bars",
    "fetch_tushare_daily_bars",
    "make_cross_section_mock_bars",
    "make_mock_bars",
    "normalize_symbol_group",
    "normalize_ts_code",
    "run_cross_section_momentum_backtest",
    "run_pbx_ma_backtest",
    "run_preset_backtest",
    "run_td_demark_9_13_backtest",
    "serialize_backtest_result",
]


def _compute_performance_metrics(result: BacktestResult) -> dict[str, Any]:
    """Derive standard performance statistics from a completed backtest."""
    import math
    from collections import defaultdict

    initial_cash = float(getattr(result, "initial_cash", 1_000_000.0))
    final_equity = result.final_equity

    # Total return
    total_return = (final_equity - initial_cash) / initial_cash if initial_cash else 0.0

    # Duration & annualized return
    snapshots = result.snapshots
    if len(snapshots) >= 2:
        first_ts = snapshots[0].timestamp
        last_ts = snapshots[-1].timestamp
        days = max((last_ts - first_ts).total_seconds() / 86400, 1.0)
    else:
        days = 1.0

    years = days / 365.25
    if years > 0 and (1 + total_return) > 0:
        annualized_return = (1 + total_return) ** (1 / years) - 1
    else:
        annualized_return = 0.0

    # Max drawdown (from full snapshot series)
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    if snapshots:
        peak = snapshots[0].equity
        for snap in snapshots:
            if snap.equity > peak:
                peak = snap.equity
            dd = peak - snap.equity
            if dd > max_drawdown:
                max_drawdown = dd
                max_drawdown_pct = dd / peak if peak > 0 else 0.0

    # Sharpe ratio (per-bar returns, annualized)
    sharpe_ratio = 0.0
    if len(snapshots) >= 3:
        equities = [s.equity for s in snapshots]
        daily_returns: list[float] = []
        for i in range(1, len(equities)):
            if equities[i - 1] > 0:
                daily_returns.append(equities[i] / equities[i - 1] - 1)
        if daily_returns:
            mean_r = sum(daily_returns) / len(daily_returns)
            var_r = sum((r - mean_r) ** 2 for r in daily_returns) / len(daily_returns)
            std_r = math.sqrt(var_r) if var_r > 0 else 0.0
            if std_r > 0:
                bars_per_day = len(snapshots) / days if days > 0 else 1
                sharpe_ratio = (mean_r / std_r) * math.sqrt(bars_per_day * 252)

    # Win rate (FIFO round-trip matching)
    open_trades: dict[str, list[float]] = defaultdict(list)
    wins = 0
    losses = 0
    for trade in result.trades:
        if trade.side.value == "BUY":
            open_trades[trade.symbol].append(trade.price)
        elif trade.side.value == "SELL" and open_trades[trade.symbol]:
            entry_price = open_trades[trade.symbol].pop(0)
            if trade.price >= entry_price:
                wins += 1
            else:
                losses += 1

    round_trips = wins + losses
    win_rate = wins / round_trips if round_trips > 0 else None

    return {
        "total_return_pct": round(total_return * 100, 2),
        "annualized_return_pct": round(annualized_return * 100, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "max_drawdown": round(max_drawdown, 2),
        "max_drawdown_pct": round(max_drawdown_pct * 100, 2),
        "win_rate_pct": round(win_rate * 100, 2) if win_rate is not None else None,
        "round_trip_trades": round_trips,
        "trade_count": len(result.trades),
        "trading_days": round(days, 1),
    }


def serialize_backtest_result(
    result: BacktestResult, *, max_equity_points: int = 200
) -> dict[str, Any]:
    """Convert BacktestResult into a JSON-ready response payload.

    Parameters
    ----------
    max_equity_points:
        Maximum number of equity-curve snapshots to include.  The front-end
        only renders ~48 bars, so sending tens of thousands of points wastes
        bandwidth and blocks the browser during JSON parsing.  Defaults to
        200, which gives smooth charts while keeping the payload small.
    """
    initial_cash = float(getattr(result, "initial_cash", 1_000_000.0))
    unrealized_pnl = float(
        getattr(
            result,
            "unrealized_pnl",
            result.final_equity - initial_cash - result.realized_pnl,
        )
    )

    # Downsample equity curve to keep response compact.
    snapshots = result.snapshots
    total_snapshots = len(snapshots)
    if total_snapshots > max_equity_points:
        step = total_snapshots / max_equity_points
        indices = {0, total_snapshots - 1}
        indices.update(int(i * step) for i in range(max_equity_points))
        snapshots = [snapshots[i] for i in sorted(indices)]

    # Cap signals and trades to keep the HTTP response small.
    # The front-end only needs them for display; full details live in the
    # trade-log file when write_trade_log is enabled.
    MAX_SIGNAL_ITEMS = 500
    MAX_TRADE_ITEMS = 500

    capped_signals = result.signals[:MAX_SIGNAL_ITEMS]
    capped_trades = result.trades[:MAX_TRADE_ITEMS]

    return {
        "market_events_processed": result.market_events_processed,
        "initial_cash": round(initial_cash, 2),
        "final_cash": round(result.final_cash, 2),
        "final_market_value": round(result.final_market_value, 2),
        "final_equity": round(result.final_equity, 2),
        "realized_pnl": round(result.realized_pnl, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "trade_log_path": result.trade_log_path,
        "equity_curve_count": total_snapshots,
        "total_signals": len(result.signals),
        "total_trades": len(result.trades),
        "performance": _compute_performance_metrics(result),
        "signals": [
            {
                "timestamp": signal.timestamp.isoformat(),
                "symbol": signal.symbol,
                "source": signal.source,
                "rule_id": signal.rule_id,
                "signal_type": signal.signal_type.value,
                "payload": signal.payload,
            }
            for signal in capped_signals
        ],
        "trades": [
            {
                "timestamp": trade.timestamp.isoformat(),
                "symbol": trade.symbol,
                "side": trade.side.value,
                "quantity": trade.quantity,
                "price": trade.price,
                "commission": round(trade.commission, 2),
            }
            for trade in capped_trades
        ],
        "positions": [
            {
                "symbol": position.symbol,
                "quantity": position.quantity,
                "avg_price": position.avg_price,
                "realized_pnl": round(position.realized_pnl, 2),
            }
            for position in result.positions.values()
        ],
        "equity_curve": [
            {
                "timestamp": snapshot.timestamp.isoformat(),
                "equity": round(snapshot.equity, 2),
                "cash": round(snapshot.cash, 2),
                "market_value": round(snapshot.market_value, 2),
                "realized_pnl": round(snapshot.realized_pnl, 2),
            }
            for snapshot in snapshots
        ],
    }
