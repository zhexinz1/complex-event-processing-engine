"""User-authored signal support."""

from .models import SignalDefinition, SignalDiagnostic, SignalStatus
from .runtime import (
    LiveSignalMonitor,
    SignalContractValidator,
    UserSignalTrigger,
    load_signal_class,
    run_user_signal_backtest,
    serialize_signal_event,
)

__all__ = [
    "LiveSignalMonitor",
    "SignalContractValidator",
    "SignalDefinition",
    "SignalDiagnostic",
    "SignalStatus",
    "UserSignalTrigger",
    "load_signal_class",
    "run_user_signal_backtest",
    "serialize_signal_event",
]
