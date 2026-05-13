"""Built-in preset signals seeded into the user-signal table."""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent
from typing import Protocol

from database.models import UserSignalDefinition, UserSignalStatus


PRESET_SIGNAL_AUTHOR = "preset"


@dataclass(frozen=True)
class PresetSignalDefinition:
    name: str
    symbols: list[str]
    bar_freq: str
    source_code: str


PBX_MA_SIGNAL_SOURCE = dedent(
    '''
    class Signal:
        name = "PBX1 + MA$1 情绪周期"
        symbols = ["600519.SH"]
        bar_freq = "1d"

        def __init__(self, ctx):
            self.ctx = ctx
            self.pbx_period = 4
            self.ma_period = 10
            self.quantity = 100
            self.closes = []
            self.previous_pbx1 = None
            self.previous_ma1 = None
            self.in_position = False

        def on_bar(self, bar):
            self.closes.append(bar.close)
            if len(self.closes) < max(self.pbx_period * 4, self.ma_period):
                return None

            pbx1 = self._pbx1()
            ma1 = self._ma(self.ma_period)
            if self.previous_pbx1 is None or self.previous_ma1 is None:
                self.previous_pbx1 = pbx1
                self.previous_ma1 = ma1
                return None

            lines_up = pbx1 > self.previous_pbx1 and ma1 > self.previous_ma1
            lines_down = pbx1 < self.previous_pbx1 and ma1 < self.previous_ma1
            price_above_both = bar.close > max(pbx1, ma1)
            price_below_both = bar.close < min(pbx1, ma1)

            signal = None
            if not self.in_position and price_above_both and lines_up:
                self.in_position = True
                signal = {
                    "side": "BUY",
                    "quantity": self.quantity,
                    "price": bar.close,
                    "reason": "ice_to_start",
                    "pbx1": pbx1,
                    "ma1": ma1,
                }
            elif self.in_position and price_below_both and lines_down:
                self.in_position = False
                signal = {
                    "side": "SELL",
                    "quantity": self.quantity,
                    "price": bar.close,
                    "reason": "climax_to_ebb",
                    "pbx1": pbx1,
                    "ma1": ma1,
                }

            self.previous_pbx1 = pbx1
            self.previous_ma1 = ma1
            return signal

        def _ma(self, period):
            return sum(self.closes[-period:]) / period

        def _pbx1(self):
            return (
                self._ma(self.pbx_period)
                + self._ma(self.pbx_period * 2)
                + self._ma(self.pbx_period * 4)
            ) / 3
    '''
).strip()


TD_DEMARK_SIGNAL_SOURCE = dedent(
    '''
    class Signal:
        name = "TD DeMark 9+13 参考信号"
        symbols = ["000680.SZ"]
        bar_freq = "1d"

        def __init__(self, ctx):
            self.ctx = ctx
            self.setup_bars = 9
            self.setup_lookback = 4
            self.countdown_bars = 13
            self.countdown_lookback = 2
            self.weak_position_pct = 0.5
            self.full_position_pct = 1.0
            self.closes = []
            self.highs = []
            self.lows = []
            self.buy_setup = 0
            self.sell_setup = 0
            self.active_countdown = 0
            self.countdown = 0
            self.position_pct = 0

        def on_bar(self, bar):
            self.closes.append(bar.close)
            self.highs.append(bar.high)
            self.lows.append(bar.low)
            index = len(self.closes) - 1
            if index < max(self.setup_lookback, self.countdown_lookback):
                return None

            lookback_close = self.closes[index - self.setup_lookback]
            self.buy_setup = self.buy_setup + 1 if bar.close < lookback_close else 0
            self.sell_setup = self.sell_setup + 1 if bar.close > lookback_close else 0
            buy_setup_done = self.buy_setup == self.setup_bars
            sell_setup_done = self.sell_setup == self.setup_bars

            if buy_setup_done:
                self.active_countdown = 1
                self.countdown = 0
                return self._position_signal(bar, "BUY", "weak", "td_buy_setup_9")
            if sell_setup_done:
                self.active_countdown = -1
                self.countdown = 0
                return self._position_signal(bar, "SELL", "weak", "td_sell_setup_9")

            buy_countdown_qualifies = (
                self.active_countdown == 1
                and bar.close <= self.lows[index - self.countdown_lookback]
            )
            sell_countdown_qualifies = (
                self.active_countdown == -1
                and bar.close >= self.highs[index - self.countdown_lookback]
            )
            if buy_countdown_qualifies or sell_countdown_qualifies:
                self.countdown += 1

            if self.active_countdown == 1 and self.countdown == self.countdown_bars:
                self.active_countdown = 0
                self.countdown = 0
                return self._position_signal(bar, "BUY", "strong", "td_buy_9_13")
            if self.active_countdown == -1 and self.countdown == self.countdown_bars:
                self.active_countdown = 0
                self.countdown = 0
                return self._position_signal(bar, "SELL", "strong", "td_sell_9_13")
            return None

        def _position_signal(self, bar, td_side, strength, reason):
            target_pct = self._target_position_pct(td_side, strength)
            if target_pct == self.position_pct:
                return None
            self.position_pct = target_pct
            return {
                "side": "BUY" if td_side == "BUY" else "SELL",
                "target_position_pct": target_pct,
                "price": bar.close,
                "td_side": td_side,
                "strength": strength,
                "setup_bars": self.setup_bars,
                "countdown_bars": self.countdown_bars,
                "reason": reason,
            }

        def _target_position_pct(self, td_side, strength):
            if td_side == "BUY":
                if strength == "strong":
                    return self.full_position_pct
                return max(self.position_pct, self.weak_position_pct)
            if strength == "strong":
                return 0
            return min(self.position_pct, self.weak_position_pct)
    '''
).strip()


CROSS_SECTION_MOMENTUM_SIGNAL_SOURCE = dedent(
    '''
    class Signal:
        name = "横截面动量轮动"
        symbols = ["000001.SZ", "600000.SH", "300750.SZ"]
        bar_freq = "1d"

        closes = {}
        latest_bars = {}
        seen_by_time = {}
        pending_actions = {}
        current_symbol = None
        last_rebalance_time = None

        def __init__(self, ctx):
            self.ctx = ctx
            self.lookback = 5
            self.quantity = 100
            for symbol in self.symbols:
                if symbol not in Signal.closes:
                    Signal.closes[symbol] = []

        def on_bar(self, bar):
            if bar.symbol not in self.symbols:
                return None

            Signal.closes[bar.symbol].append(bar.close)
            Signal.latest_bars[bar.symbol] = bar
            if bar.symbol in Signal.pending_actions:
                action = Signal.pending_actions[bar.symbol]
                del Signal.pending_actions[bar.symbol]
                action["price"] = bar.close
                return action

            bar_time = str(bar.bar_time)
            if bar_time not in Signal.seen_by_time:
                Signal.seen_by_time[bar_time] = {}
            Signal.seen_by_time[bar_time][bar.symbol] = True

            if Signal.last_rebalance_time == bar_time:
                return None
            for symbol in self.symbols:
                if symbol not in Signal.seen_by_time[bar_time]:
                    return None
                if len(Signal.closes[symbol]) <= self.lookback:
                    return None

            winner = self.symbols[0]
            winner_score = self._score(winner)
            for symbol in self.symbols:
                score = self._score(symbol)
                if score > winner_score:
                    winner = symbol
                    winner_score = score

            if winner == Signal.current_symbol:
                Signal.last_rebalance_time = bar_time
                return None

            previous = Signal.current_symbol
            Signal.current_symbol = winner
            Signal.last_rebalance_time = bar_time

            if previous is not None:
                Signal.pending_actions[previous] = {
                    "side": "SELL",
                    "quantity": self.quantity,
                    "price": 0,
                    "score": self._score(previous),
                    "winner": winner,
                    "lookback": self.lookback,
                    "reason": "rotate_out",
                }
            Signal.pending_actions[winner] = {
                "side": "BUY",
                "quantity": self.quantity,
                "price": 0,
                "score": winner_score,
                "winner": winner,
                "lookback": self.lookback,
                "reason": "rotate_in",
            }

            if bar.symbol in Signal.pending_actions:
                action = Signal.pending_actions[bar.symbol]
                del Signal.pending_actions[bar.symbol]
                action["price"] = bar.close
                return action
            return None

        def _score(self, symbol):
            values = Signal.closes[symbol]
            return values[-1] / values[-(self.lookback + 1)] - 1
    '''
).strip()


PRESET_SIGNAL_DEFINITIONS = [
    PresetSignalDefinition(
        name="PBX1 + MA$1 情绪周期",
        symbols=["600519.SH"],
        bar_freq="1d",
        source_code=PBX_MA_SIGNAL_SOURCE,
    ),
    PresetSignalDefinition(
        name="TD DeMark 9+13 参考信号",
        symbols=["000680.SZ"],
        bar_freq="1d",
        source_code=TD_DEMARK_SIGNAL_SOURCE,
    ),
    PresetSignalDefinition(
        name="横截面动量轮动",
        symbols=["000001.SZ", "600000.SH", "300750.SZ"],
        bar_freq="1d",
        source_code=CROSS_SECTION_MOMENTUM_SIGNAL_SOURCE,
    ),
]


class UserSignalStore(Protocol):
    def list_user_signals(
        self, status: UserSignalStatus | None = None
    ) -> list[UserSignalDefinition]: ...

    def create_user_signal(self, signal: UserSignalDefinition) -> int: ...

    def update_user_signal(self, signal_id: int, signal: UserSignalDefinition) -> bool: ...


def seed_preset_user_signals(store: UserSignalStore) -> None:
    """Insert or refresh built-in presets as saved signal definitions."""
    existing_by_name = {
        signal.name: signal
        for signal in store.list_user_signals()
        if signal.created_by == PRESET_SIGNAL_AUTHOR
    }
    for preset in PRESET_SIGNAL_DEFINITIONS:
        existing = existing_by_name.get(preset.name)
        signal = UserSignalDefinition(
            id=existing.id if existing else None,
            name=preset.name,
            symbols=list(preset.symbols),
            bar_freq=preset.bar_freq,
            source_code=preset.source_code,
            status=existing.status if existing else UserSignalStatus.DISABLED,
            created_by=PRESET_SIGNAL_AUTHOR,
            created_at=existing.created_at if existing else None,
            updated_at=existing.updated_at if existing else None,
        )
        if existing and existing.id is not None:
            store.update_user_signal(existing.id, signal)
        else:
            store.create_user_signal(signal)
