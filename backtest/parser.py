"""历史数据解析器。"""

from __future__ import annotations

from typing import Any, Iterable

from cep.core.events import BarEvent


class HistoricalDataParser:
    """将原始历史数据统一解析为标准事件。"""

    def parse_bars(
        self,
        raw_bars: Iterable[BarEvent | dict[str, Any]],
        *,
        assume_sorted: bool = False,
    ) -> list[BarEvent]:
        """将历史 bar 数据统一转换为 BarEvent 列表。"""
        parsed: list[BarEvent] = []

        for item in raw_bars:
            if isinstance(item, BarEvent):
                parsed.append(item)
            else:
                parsed.append(BarEvent(**item))

        if not assume_sorted:
            parsed.sort(key=lambda bar: (bar.timestamp, bar.bar_time))
        return parsed
