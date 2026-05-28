"""Market data feed abstraction.

A feed yields :class:`~hft.core.types.Tick` objects in time order. Concrete
feeds include a synthetic random-walk generator and a CSV historical replay.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from hft.core.types import Tick


class MarketDataFeed(ABC):
    """Iterable source of ticks, ordered by timestamp."""

    @abstractmethod
    def __iter__(self) -> Iterator[Tick]:
        ...
