"""多周期 K 线聚合。"""

from __future__ import annotations

from typing import Optional

from cep.core.event_bus import EventBus
from cep.core.events import BarEvent


def _parse_minute_freq(freq: str) -> int:
    """将 '1m' / '5m' / '15m' 解析为分钟数。"""
    if not freq.endswith("m"):
        raise ValueError(f"Only minute frequencies are supported for aggregation: {freq}")

    minutes = int(freq[:-1])
    if minutes <= 0:
        raise ValueError(f"Frequency must be positive: {freq}")
    return minutes


class MultiTimeframeBarAggregator:
    """
    多周期 K 线聚合器。

    目前支持分钟级 Bar 从小周期聚合为大周期，例如：
      1m -> 5m / 15m
    """

    def __init__(
        self,
        event_bus: EventBus,
        base_freq: str = "1m",
        target_freqs: Optional[list[str]] = None,
    ) -> None:
        self.event_bus = event_bus
        self.base_freq = base_freq
        self.target_freqs = target_freqs or []
        self._buffers: dict[tuple[str, str], list[BarEvent]] = {}

        self._base_minutes = _parse_minute_freq(base_freq)
        self._factors = {
            target_freq: _parse_minute_freq(target_freq) // self._base_minutes
            for target_freq in self.target_freqs
        }
        self.event_bus.subscribe(BarEvent, self.on_bar)

    def on_bar(self, event: BarEvent) -> None:
        """接收小周期 Bar 并在达到窗口长度时产出聚合 Bar。"""
        if event.freq != self.base_freq:
            return

        for target_freq, factor in self._factors.items():
            if factor <= 1:
                continue

            key = (event.symbol, target_freq)
            buffer = self._buffers.setdefault(key, [])
            buffer.append(event)

            if len(buffer) < factor:
                continue

            aggregated = BarEvent(
                symbol=event.symbol,
                freq=target_freq,
                open=buffer[0].open,
                high=max(bar.high for bar in buffer),
                low=min(bar.low for bar in buffer),
                close=buffer[-1].close,
                volume=sum(bar.volume for bar in buffer),
                turnover=sum(bar.turnover for bar in buffer),
                bar_time=buffer[0].bar_time,
                timestamp=buffer[-1].timestamp,
            )
            self._buffers[key] = []
            self.event_bus.publish(aggregated)
