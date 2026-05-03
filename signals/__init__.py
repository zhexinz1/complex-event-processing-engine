"""User-authored signal support."""

from .models import SignalDefinition, SignalDiagnostic, SignalStatus
from .runtime import (
    LiveSignalMonitor,
    SignalContractValidator,
    UserSignalTrigger,
    deserialize_bar_event_payload,
    load_signal_class,
    run_user_signal_backtest,
    serialize_bar_event,
    serialize_signal_event,
)

__all__ = [
    "LiveSignalMonitor",
    "SignalContractValidator",
    "SignalDefinition",
    "SignalDiagnostic",
    "SignalStatus",
    "UserSignalTrigger",
    "deserialize_bar_event_payload",
    "load_signal_class",
    "run_user_signal_backtest",
    "serialize_bar_event",
    "serialize_signal_event",
]
