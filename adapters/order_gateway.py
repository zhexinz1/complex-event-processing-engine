"""
Minimal order gateway primitives used by integration examples.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Order:
    order_id: str
    symbol: str
    status: str


class MockOrderGateway:
    """In-memory order gateway for examples and local demos."""

    def __init__(self) -> None:
        self._callback: Callable[[Order], None] | None = None
        self._connected = False

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def set_order_callback(self, callback: Callable[[Order], None]) -> None:
        self._callback = callback

    def submit_order(self, symbol: str, quantity: float, side: str) -> Order:
        order = Order(
            order_id=f"MOCK-{symbol}-{abs(hash((symbol, quantity, side))) % 100000}",
            symbol=symbol,
            status="SUBMITTED" if self._connected else "REJECTED",
        )
        if self._callback is not None:
            self._callback(order)
        return order
