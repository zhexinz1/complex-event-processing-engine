"""事件队列与分发器。"""

from __future__ import annotations

import heapq
from datetime import datetime
from typing import Iterable

from cep.core.event_bus import EventBus
from cep.core.events import BaseEvent


class EventQueue:
    """主事件队列。"""

    def __init__(self) -> None:
        self._heap: list[tuple[datetime, int, BaseEvent]] = []
        self._ordered: list[BaseEvent] = []
        self._ordered_index = 0
        self._sequence = 0

    def push(self, event: BaseEvent) -> None:
        """按时间顺序压入事件。"""
        self._materialize_ordered_into_heap()
        heapq.heappush(self._heap, (event.timestamp, self._sequence, event))
        self._sequence += 1

    def extend(self, events: Iterable[BaseEvent]) -> None:
        """批量压入事件。"""
        for event in events:
            self.push(event)

    def extend_sorted(self, events: Iterable[BaseEvent]) -> None:
        """批量导入已按时间排序的事件，跳过 heap 开销。"""
        if self._heap:
            self.extend(events)
            return
        self._ordered.extend(events)

    def pop(self) -> BaseEvent:
        """弹出下一个事件。"""
        if self._ordered_index < len(self._ordered):
            event = self._ordered[self._ordered_index]
            self._ordered_index += 1
            if self._ordered_index >= len(self._ordered):
                self._ordered.clear()
                self._ordered_index = 0
            return event
        _, _, event = heapq.heappop(self._heap)
        return event

    def peek(self) -> BaseEvent:
        """查看下一个事件但不弹出。"""
        if self._ordered_index < len(self._ordered):
            return self._ordered[self._ordered_index]
        return self._heap[0][2]

    def empty(self) -> bool:
        """是否为空。"""
        return self._ordered_index >= len(self._ordered) and not self._heap

    def __len__(self) -> int:
        """剩余未消费事件数量。"""
        remaining_ordered = len(self._ordered) - self._ordered_index
        return remaining_ordered + len(self._heap)

    def _materialize_ordered_into_heap(self) -> None:
        """当顺序流和 heap 混用时，将剩余顺序事件转入 heap。"""
        if self._ordered_index >= len(self._ordered):
            self._ordered.clear()
            self._ordered_index = 0
            return
        for event in self._ordered[self._ordered_index:]:
            heapq.heappush(self._heap, (event.timestamp, self._sequence, event))
            self._sequence += 1
        self._ordered.clear()
        self._ordered_index = 0


class Dispatcher:
    """核心事件分发器。"""

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus

    def dispatch_next(self, event_queue: EventQueue) -> BaseEvent:
        """取出一个事件并送入 EventBus。"""
        event = event_queue.pop()
        self.event_bus.publish(event)
        return event
