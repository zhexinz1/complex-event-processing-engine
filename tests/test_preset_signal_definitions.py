from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.models import UserSignalDefinition, UserSignalStatus
from signals.preset_signal_definitions import (
    PRESET_SIGNAL_AUTHOR,
    PRESET_SIGNAL_DEFINITIONS,
    seed_preset_user_signals,
)
from signals.runtime import SignalContractValidator, load_signal_class


def test_preset_signal_sources_satisfy_user_signal_contract() -> None:
    validator = SignalContractValidator()

    for preset in PRESET_SIGNAL_DEFINITIONS:
        is_valid, diagnostics = validator.validate(preset.source_code)

        assert is_valid, preset.name
        assert diagnostics == []
        signal_class, runtime_diagnostics = load_signal_class(preset.source_code)
        assert signal_class.name == preset.name
        assert signal_class.symbols == preset.symbols
        assert signal_class.bar_freq == preset.bar_freq
        assert runtime_diagnostics == []


def test_seed_preset_user_signals_creates_missing_rows() -> None:
    class FakeStore:
        def __init__(self) -> None:
            self.signals: list[UserSignalDefinition] = []

        def list_user_signals(self, status: UserSignalStatus | None = None):
            assert status is None
            return self.signals

        def create_user_signal(self, signal: UserSignalDefinition) -> int:
            signal.id = len(self.signals) + 1
            self.signals.append(signal)
            return signal.id

        def update_user_signal(
            self, signal_id: int, signal: UserSignalDefinition
        ) -> bool:
            raise AssertionError("missing rows should be created, not updated")

    store = FakeStore()

    seed_preset_user_signals(store)

    assert [signal.name for signal in store.signals] == [
        preset.name for preset in PRESET_SIGNAL_DEFINITIONS
    ]
    assert all(signal.created_by == PRESET_SIGNAL_AUTHOR for signal in store.signals)
    assert all(signal.status == UserSignalStatus.DISABLED for signal in store.signals)


def test_seed_preset_user_signals_refreshes_existing_rows_and_preserves_status() -> None:
    existing = UserSignalDefinition(
        id=9,
        name=PRESET_SIGNAL_DEFINITIONS[0].name,
        symbols=["OLD"],
        bar_freq="1m",
        source_code="old",
        status=UserSignalStatus.ENABLED,
        created_by=PRESET_SIGNAL_AUTHOR,
    )

    class FakeStore:
        def __init__(self) -> None:
            self.signals = [existing]
            self.updated: list[UserSignalDefinition] = []

        def list_user_signals(self, status: UserSignalStatus | None = None):
            assert status is None
            return self.signals

        def create_user_signal(self, signal: UserSignalDefinition) -> int:
            signal.id = len(self.signals) + 1
            self.signals.append(signal)
            return signal.id

        def update_user_signal(
            self, signal_id: int, signal: UserSignalDefinition
        ) -> bool:
            assert signal_id == existing.id
            self.updated.append(signal)
            return True

    store = FakeStore()

    seed_preset_user_signals(store)

    assert store.updated
    refreshed = store.updated[0]
    assert refreshed.id == existing.id
    assert refreshed.symbols == PRESET_SIGNAL_DEFINITIONS[0].symbols
    assert refreshed.source_code == PRESET_SIGNAL_DEFINITIONS[0].source_code
    assert refreshed.status == UserSignalStatus.ENABLED
