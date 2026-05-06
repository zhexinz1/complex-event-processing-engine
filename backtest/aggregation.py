"""多周期 K 线聚合。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from cep.core.event_bus import EventBus
from cep.core.events import BarEvent

logger = logging.getLogger(__name__)


def _get_bucket(dt: datetime, freq: str) -> datetime:
    """计算给定时间在特定频率下的时间桶（左边界）。"""
    freq = freq.lower()
    if freq.endswith("m"):
        minutes = int(freq[:-1])
        if minutes >= 60:
            hours = minutes // 60
            bucket_hour = (dt.hour // hours) * hours
            return dt.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)
        else:
            bucket_minute = (dt.minute // minutes) * minutes
            return dt.replace(minute=bucket_minute, second=0, microsecond=0)
    elif freq.endswith("h"):
        hours = int(freq[:-1])
        bucket_hour = (dt.hour // hours) * hours
        return dt.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)
    elif freq.endswith("d"):
        # 对于日线级别，通常以 0 点作为边界
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"Unsupported frequency format: {freq}")


class MultiTimeframeBarAggregator:
    """
    多周期 K 线聚合器 (Time-Bucketing)。

    采用实盘标准的时间边界对齐算法：
    将高频小周期 K 线的时间戳映射到大周期的目标边界（Bucket），
    当新到达的 K 线所跨越的边界大于当前维护的边界时，即封闭并产出聚合的大周期 K 线。
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
        
        # 记录每个 (symbol, target_freq) 当前正在聚合的 K 线属性
        self._current_buckets: dict[tuple[str, str], datetime] = {}
        self._buffers: dict[tuple[str, str], list[BarEvent]] = {}

        if self.target_freqs:
            self.event_bus.subscribe(BarEvent, self.on_bar)

    def on_bar(self, event: BarEvent) -> None:
        """接收小周期 Bar 并根据时间边界产出聚合 Bar。"""
        if event.freq != self.base_freq:
            return

        for target_freq in self.target_freqs:
            if target_freq == self.base_freq:
                continue

            bucket = _get_bucket(event.bar_time, target_freq)
            key = (event.symbol, target_freq)

            current_bucket = self._current_buckets.get(key)
            
            if current_bucket is None:
                # 初始状态
                self._current_buckets[key] = bucket
                self._buffers[key] = [event]
            elif bucket > current_bucket:
                # 跨越了边界，封闭上一根 K 线并发布
                self._emit_aggregated_bar(key, target_freq)
                
                # 开启新周期
                self._current_buckets[key] = bucket
                self._buffers[key] = [event]
            else:
                # 在同一边界内，累加
                self._buffers[key].append(event)

    def flush(self) -> None:
        """强制清空所有缓冲池并发布最后未完结的 K 线。"""
        keys = list(self._buffers.keys())
        for key in keys:
            target_freq = key[1]
            self._emit_aggregated_bar(key, target_freq)
            self._current_buckets.pop(key, None)
            
    def _emit_aggregated_bar(self, key: tuple[str, str], target_freq: str) -> None:
        buffer = self._buffers.get(key)
        if not buffer:
            return
            
        symbol = key[0]
        bucket_time = self._current_buckets[key]
        
        aggregated = BarEvent(
            symbol=symbol,
            freq=target_freq,
            open=buffer[0].open,
            high=max(bar.high for bar in buffer),
            low=min(bar.low for bar in buffer),
            close=buffer[-1].close,
            volume=sum(bar.volume for bar in buffer),
            turnover=sum(bar.turnover for bar in buffer),
            bar_time=bucket_time,
            timestamp=buffer[-1].timestamp,
        )
        self._buffers[key] = []
        self.event_bus.publish(aggregated)
