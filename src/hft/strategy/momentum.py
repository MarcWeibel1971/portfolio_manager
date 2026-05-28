"""A moving-average crossover momentum strategy.

Goes long when a fast EMA crosses above a slow EMA, flat/short when it crosses
below. Trades with market orders, sizing to a fixed target position. Simple,
but it demonstrates stateful indicators and position flipping through the stack.
"""
from __future__ import annotations

from hft.core.types import Side, Tick
from hft.strategy.base import Strategy, StrategyContext


class _EMA:
    """Incremental exponential moving average."""

    def __init__(self, period: int) -> None:
        self.alpha = 2.0 / (period + 1.0)
        self.value: float | None = None

    def update(self, x: float) -> float:
        self.value = x if self.value is None else self.alpha * x + (1 - self.alpha) * self.value
        return self.value


class MomentumStrategy(Strategy):
    def __init__(
        self,
        symbol: str,
        fast_period: int = 10,
        slow_period: int = 30,
        target_position: float = 50.0,
        name: str | None = None,
    ) -> None:
        super().__init__(name)
        if fast_period >= slow_period:
            raise ValueError("fast_period must be < slow_period")
        self.symbol = symbol
        self.target_position = target_position
        self._fast = _EMA(fast_period)
        self._slow = _EMA(slow_period)
        self._warmup = slow_period
        self._seen = 0
        self._last_signal = 0  # -1 short, 0 flat-ish, +1 long

    def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        if tick.symbol != self.symbol:
            return

        fast = self._fast.update(tick.mid)
        slow = self._slow.update(tick.mid)
        self._seen += 1
        if self._seen < self._warmup:
            return  # let the slow EMA stabilise before trading

        signal = 1 if fast > slow else -1
        if signal == self._last_signal:
            return  # no crossover, nothing to do

        self._last_signal = signal
        desired = self.target_position * signal
        delta = desired - ctx.position(self.symbol)
        if abs(delta) < 1e-9:
            return

        side = Side.BUY if delta > 0 else Side.SELL
        ctx.market_order(self.symbol, side, abs(delta))
