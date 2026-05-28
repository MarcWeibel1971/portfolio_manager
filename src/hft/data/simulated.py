"""Synthetic and historical market data feeds.

``SimulatedFeed`` produces a reproducible geometric random walk with a
configurable spread — useful for demos, tests, and strategy smoke-checks
without any external dependency. ``CsvFeed`` replays recorded ticks.
"""
from __future__ import annotations

import csv
import math
import random
from collections.abc import Iterator
from pathlib import Path

from hft.core.types import Tick
from hft.data.feed import MarketDataFeed


class SimulatedFeed(MarketDataFeed):
    """Geometric Brownian motion mid-price with a fixed fractional spread."""

    def __init__(
        self,
        symbol: str,
        n_ticks: int = 1_000,
        start_price: float = 100.0,
        volatility: float = 0.0008,  # per-tick stdev of log-returns
        drift: float = 0.0,  # per-tick drift of log-returns
        spread_bps: float = 5.0,  # full bid/ask spread in basis points
        start_time: float = 0.0,
        tick_interval: float = 1.0,  # seconds between ticks
        seed: int | None = 42,
    ) -> None:
        self.symbol = symbol
        self.n_ticks = n_ticks
        self.start_price = start_price
        self.volatility = volatility
        self.drift = drift
        self.spread_bps = spread_bps
        self.start_time = start_time
        self.tick_interval = tick_interval
        self.seed = seed

    def __iter__(self) -> Iterator[Tick]:
        rng = random.Random(self.seed)
        price = self.start_price
        half_spread = self.spread_bps / 2.0 / 10_000.0
        for i in range(self.n_ticks):
            shock = rng.gauss(self.drift, self.volatility)
            price *= math.exp(shock)
            bid = price * (1.0 - half_spread)
            ask = price * (1.0 + half_spread)
            yield Tick(
                symbol=self.symbol,
                timestamp=self.start_time + i * self.tick_interval,
                bid=bid,
                ask=ask,
                last=price,
                volume=rng.uniform(1.0, 10.0),
            )


class CsvFeed(MarketDataFeed):
    """Replay ticks from a CSV with columns: timestamp,symbol,bid,ask[,last,volume]."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def __iter__(self) -> Iterator[Tick]:
        with self.path.open(newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                yield Tick(
                    symbol=row["symbol"],
                    timestamp=float(row["timestamp"]),
                    bid=float(row["bid"]),
                    ask=float(row["ask"]),
                    last=float(row.get("last") or row["bid"]),
                    volume=float(row.get("volume") or 0.0),
                )
