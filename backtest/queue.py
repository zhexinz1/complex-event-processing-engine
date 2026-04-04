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
        self._sequence = 0

    def push(self, event: BaseEvent) -> None:
        """按时间顺序压入事件。"""
        heapq.heappush(self._heap, (event.timestamp, self._sequence, event))
        self._sequence += 1

    def extend(self, events: Iterable[BaseEvent]) -> None:
        """批量压入事件。"""
        for event in events:
            self.push(event)

    def pop(self) -> BaseEvent:
        """弹出下一个事件。"""
        _, _, event = heapq.heappop(self._heap)
        return event

    def empty(self) -> bool:
        """是否为空。"""
        return not self._heap


class Dispatcher:
    """核心事件分发器。"""

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus

    def dispatch_next(self, event_queue: EventQueue) -> BaseEvent:
        """取出一个事件并送入 EventBus。"""
        event = event_queue.pop()
        self.event_bus.publish(event)
        return event
