"""Broker abstraction.

A broker accepts orders and emits fills. Concrete implementations include the
:class:`~hft.execution.paper.PaperBroker` (simulated) and, in future, live
exchange adapters. Strategies and the engine only depend on this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from hft.core.types import Fill, Order, Tick

FillCallback = Callable[[Fill], None]


class Broker(ABC):
    """Interface every execution venue must implement."""

    def __init__(self) -> None:
        self._fill_callbacks: list[FillCallback] = []

    def on_fill(self, callback: FillCallback) -> None:
        """Register a callback invoked for every fill this broker produces."""
        self._fill_callbacks.append(callback)

    def _emit_fill(self, fill: Fill) -> None:
        for cb in self._fill_callbacks:
            cb(fill)

    @abstractmethod
    def submit(self, order: Order) -> None:
        """Submit an order for execution."""

    @abstractmethod
    def cancel(self, order_id: int) -> bool:
        """Attempt to cancel a resting order. Returns True if cancelled."""

    @abstractmethod
    def on_tick(self, tick: Tick) -> None:
        """Feed market data so the venue can match resting orders."""
