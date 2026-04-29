"""回测结果与状态模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from cep.core.events import OrderEvent, SignalEvent, TradeEvent


@dataclass
class BacktestPosition:
    """回测持仓状态。"""

    symbol: str
    quantity: float = 0.0
    avg_price: float = 0.0
    realized_pnl: float = 0.0


@dataclass(frozen=True)
class EquitySnapshot:
    """组合权益快照。"""

    timestamp: datetime
    cash: float
    market_value: float
    equity: float
    realized_pnl: float
    open_positions: int


@dataclass
class BacktestResult:
    """回测输出结果。"""

    market_events_processed: int
    signals: list[SignalEvent] = field(default_factory=list)
    orders: list[OrderEvent] = field(default_factory=list)
    trades: list[TradeEvent] = field(default_factory=list)
    snapshots: list[EquitySnapshot] = field(default_factory=list)
    final_cash: float = 0.0
    final_market_value: float = 0.0
    final_equity: float = 0.0
    realized_pnl: float = 0.0
    positions: dict[str, BacktestPosition] = field(default_factory=dict)
    trade_log_path: str = ""
