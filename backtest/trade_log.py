"""Persist backtest trade logs to an untracked local folder."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from typing import Any

from .models import BacktestResult

BACKTEST_DIR = Path(__file__).parent
DEFAULT_LOG_DIR = BACKTEST_DIR / "logs"
LOG_ID_PATTERN = re.compile(r"[a-zA-Z0-9._-]+")


def _log_timestamp(path: Path) -> str:
    prefix = "backtest-"
    stem = path.stem
    if stem.startswith(prefix):
        raw_timestamp = stem[len(prefix):].split("-", 1)[0]
        try:
            return datetime.strptime(raw_timestamp, "%Y%m%dT%H%M%S").replace(tzinfo=UTC).isoformat()
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()


def _summarize_symbols(payload: dict[str, Any]) -> list[str]:
    symbols: set[str] = set()
    for key in ("signals", "orders", "trades", "positions"):
        rows = payload.get(key, [])
        if isinstance(rows, list):
            symbols.update(str(row.get("symbol")) for row in rows if isinstance(row, dict) and row.get("symbol"))
    return sorted(symbols)


def _first_last_timestamp(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    timestamps: list[str] = []
    for key in ("equity_curve", "signals", "orders", "trades"):
        rows = payload.get(key, [])
        if isinstance(rows, list):
            timestamps.extend(
                str(row["timestamp"])
                for row in rows
                if isinstance(row, dict) and isinstance(row.get("timestamp"), str)
            )
    if not timestamps:
        return None, None
    return min(timestamps), max(timestamps)


def _read_log_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _sample_sequence(rows: Any, limit: int | None) -> Any:
    if not isinstance(rows, list) or limit is None or limit <= 0 or len(rows) <= limit:
        return rows
    if limit == 1:
        return [rows[-1]]
    step = (len(rows) - 1) / (limit - 1)
    indexes = {round(index * step) for index in range(limit)}
    indexes.add(0)
    indexes.add(len(rows) - 1)
    return [rows[index] for index in sorted(indexes)]


def _summarize_log_payload(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    first_timestamp, last_timestamp = _first_last_timestamp(payload)
    return {
        "id": path.stem,
        "filename": path.name,
        "created_at": _log_timestamp(path),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
        "path": str(path),
        "market_events_processed": payload.get("market_events_processed", 0),
        "initial_cash": payload.get("initial_cash", 0.0),
        "final_cash": payload.get("final_cash", 0.0),
        "final_market_value": payload.get("final_market_value", 0.0),
        "final_equity": payload.get("final_equity", 0.0),
        "realized_pnl": payload.get("realized_pnl", 0.0),
        "unrealized_pnl": payload.get("unrealized_pnl", 0.0),
        "signal_count": len(payload.get("signals", [])) if isinstance(payload.get("signals"), list) else 0,
        "order_count": len(payload.get("orders", [])) if isinstance(payload.get("orders"), list) else 0,
        "trade_count": len(payload.get("trades", [])) if isinstance(payload.get("trades"), list) else 0,
        "position_count": len(payload.get("positions", [])) if isinstance(payload.get("positions"), list) else 0,
        "symbols": _summarize_symbols(payload),
        "equity_curve_count": len(payload.get("equity_curve", [])) if isinstance(payload.get("equity_curve"), list) else 0,
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
    }


def _resolve_log_path(log_id: str, log_dir: Path) -> Path:
    if log_id in {".", ".."} or not LOG_ID_PATTERN.fullmatch(log_id):
        raise ValueError("Invalid backtest log id")
    path = log_dir / f"{log_id}.json"
    if path.parent != log_dir:
        raise ValueError("Invalid backtest log id")
    return path


def list_backtest_trade_logs(log_dir: Path | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Read persisted backtest trade log summaries, newest first."""
    target_dir = log_dir or DEFAULT_LOG_DIR
    if not target_dir.exists():
        return []

    records: list[dict[str, Any]] = []
    for path in sorted(target_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        if len(records) >= limit:
            break
        payload = _read_log_payload(path)
        if payload is None:
            continue
        records.append(_summarize_log_payload(path, payload))
    return records


def read_backtest_trade_log(
    log_id: str,
    log_dir: Path | None = None,
    equity_points: int | None = 48,
) -> dict[str, Any] | None:
    """Read one persisted backtest trade log with full payload."""
    target_dir = log_dir or DEFAULT_LOG_DIR
    path = _resolve_log_path(log_id, target_dir)
    if not path.exists() or not path.is_file():
        return None
    payload = _read_log_payload(path)
    if payload is None:
        return None
    summary = _summarize_log_payload(path, payload)
    payload["equity_curve"] = _sample_sequence(payload.get("equity_curve", []), equity_points)
    summary["data"] = payload
    return summary


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
        "initial_cash": result.initial_cash,
        "final_cash": result.final_cash,
        "final_market_value": result.final_market_value,
        "final_equity": result.final_equity,
        "realized_pnl": result.realized_pnl,
        "unrealized_pnl": result.unrealized_pnl,
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
