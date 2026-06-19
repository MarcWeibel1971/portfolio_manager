"""A moving-average crossover momentum strategy.

Goes long when a fast EMA crosses above a slow EMA, short when it crosses below.

Rather than firing a single order on the crossover and assuming it fills, the
strategy **reconciles against its actual position on every tick**: it computes
the target position from the signal and steers the real position toward it. If
an order is rejected (e.g. by a risk limit) the position simply doesn't move, so
the next tick tries again — the strategy can never get permanently stuck in the
wrong position because an order was dropped. ``max_order_size`` optionally caps
each order so large flips are scaled in/out over several ticks instead of one
oversized order that might breach per-order limits.
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
        max_order_size: float | None = None,
        min_trade: float = 1e-9,
        name: str | None = None,
    ) -> None:
        super().__init__(name)
        if fast_period >= slow_period:
            raise ValueError("fast_period must be < slow_period")
        if max_order_size is not None and max_order_size <= 0:
            raise ValueError("max_order_size must be positive when set")
        self.symbol = symbol
        self.target_position = target_position
        self.max_order_size = max_order_size  # cap per order; None = no cap
        self.min_trade = min_trade  # ignore dust-sized adjustments
        self._fast = _EMA(fast_period)
        self._slow = _EMA(slow_period)
        self._warmup = slow_period
        self._seen = 0
        self._last_signal = 0
        # Position observed just before the last order; lets us detect when an
        # order failed to move us (a binding risk limit) and avoid churn.
        self._attempt_position: float | None = None

    def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        if tick.symbol != self.symbol:
            return

        fast = self._fast.update(tick.mid)
        slow = self._slow.update(tick.mid)
        self._seen += 1
        if self._seen < self._warmup:
            return  # let the slow EMA stabilise before trading

        # Reconcile actual position toward the signal's target. Running every tick
        # means a rejected or partial order is retried rather than abandoned.
        signal = 1 if fast > slow else -1
        signal_changed = signal != self._last_signal
        self._last_signal = signal
        if signal_changed:
            self._attempt_position = None  # a fresh direction always gets a try

        pos = ctx.position(self.symbol)
        desired = self.target_position * signal
        delta = desired - pos
        if abs(delta) < self.min_trade:
            return  # already at (or close enough to) target

        aligned = (pos > 0 and signal > 0) or (pos < 0 and signal < 0)
        if aligned and not signal_changed and self._attempt_position is not None:
            # We're already on the correct side and only topping up magnitude. If
            # the previous attempt didn't move the position, a risk limit is
            # binding — pause re-trying until something changes (signal flip or a
            # fill) instead of firing a rejected order every tick.
            if abs(pos - self._attempt_position) < self.min_trade:
                return

        size = abs(delta)
        if self.max_order_size is not None:
            size = min(size, self.max_order_size)  # scale in/out in bounded steps

        side = Side.BUY if delta > 0 else Side.SELL
        self._attempt_position = pos  # remember pre-order position to detect a no-op
        ctx.market_order(self.symbol, side, size)
