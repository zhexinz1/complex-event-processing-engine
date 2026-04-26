"""Models for researcher-authored signal definitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class SignalStatus(str, Enum):
    """Lifecycle state for a saved user signal."""

    DISABLED = "disabled"
    ENABLED = "enabled"


@dataclass
class SignalDefinition:
    """Persisted researcher signal definition."""

    id: int | None
    name: str
    symbols: list[str]
    bar_freq: str
    source_code: str
    status: SignalStatus = SignalStatus.DISABLED
    created_by: str = "system"
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class SignalDiagnostic:
    """Validation or runtime diagnostic surfaced to API/UI callers."""

    level: str
    message: str
    line: int | None = None
    symbol: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "level": self.level,
            "message": self.message,
        }
        if self.line is not None:
            data["line"] = self.line
        if self.symbol:
            data["symbol"] = self.symbol
        if self.timestamp:
            data["timestamp"] = self.timestamp
        return data
