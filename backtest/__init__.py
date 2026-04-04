"""事件驱动回测模块。"""

from .aggregation import MultiTimeframeBarAggregator
from .broker import SimulatedBroker
from .engine import BacktestEngine
from .models import BacktestPosition, BacktestResult, EquitySnapshot
from .parser import HistoricalDataParser
from .portfolio import PortfolioLedger
from .queue import Dispatcher, EventQueue
from .recorder import PerformanceRecorder

__all__ = [
    "BacktestEngine",
    "BacktestPosition",
    "BacktestResult",
    "Dispatcher",
    "EquitySnapshot",
    "EventQueue",
    "HistoricalDataParser",
    "MultiTimeframeBarAggregator",
    "PerformanceRecorder",
    "PortfolioLedger",
    "SimulatedBroker",
]
