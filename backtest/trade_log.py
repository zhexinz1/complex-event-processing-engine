"""Persist backtest trade logs to an untracked local folder."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .models import BacktestResult

BACKTEST_DIR = Path(__file__).parent
DEFAULT_LOG_DIR = BACKTEST_DIR / "logs"


def write_backtest_trade_log(
    result: BacktestResult,
    log_dir: Path = DEFAULT_LOG_DIR,
) -> Path:
    """Write a JSON trade log for a completed backtest run."""
    log_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:8]}"
    log_path = log_dir / f"backtest-{run_id}.json"

    payload = {
        "market_events_processed": result.market_events_processed,
        "final_cash": result.final_cash,
        "final_market_value": result.final_market_value,
        "final_equity": result.final_equity,
        "realized_pnl": result.realized_pnl,
        "positions": [
            {
                "symbol": position.symbol,
                "quantity": position.quantity,
                "avg_price": position.avg_price,
                "realized_pnl": position.realized_pnl,
            }
            for position in result.positions.values()
        ],
        "signals": [
            {
                "timestamp": signal.timestamp.isoformat(),
                "symbol": signal.symbol,
                "source": signal.source,
                "rule_id": signal.rule_id,
                "signal_type": signal.signal_type.value,
                "payload": signal.payload,
            }
            for signal in result.signals
        ],
        "orders": [
            {
                "timestamp": order.timestamp.isoformat(),
                "order_id": order.order_id,
                "symbol": order.symbol,
                "side": order.side.value,
                "order_type": order.order_type.value,
                "status": order.status.value,
                "quantity": order.quantity,
                "price": order.price,
                "source": order.source,
                "signal_event_id": order.signal_event_id,
                "payload": order.payload,
            }
            for order in result.orders
        ],
        "trades": [
            {
                "timestamp": trade.timestamp.isoformat(),
                "trade_id": trade.trade_id,
                "order_id": trade.order_id,
                "symbol": trade.symbol,
                "side": trade.side.value,
                "quantity": trade.quantity,
                "price": trade.price,
                "commission": trade.commission,
                "source": trade.source,
                "signal_event_id": trade.signal_event_id,
                "payload": trade.payload,
            }
            for trade in result.trades
        ],
        "equity_curve": [
            {
                "timestamp": snapshot.timestamp.isoformat(),
                "cash": snapshot.cash,
                "market_value": snapshot.market_value,
                "equity": snapshot.equity,
                "realized_pnl": snapshot.realized_pnl,
                "open_positions": snapshot.open_positions,
            }
            for snapshot in result.snapshots
        ],
    }

    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return log_path
