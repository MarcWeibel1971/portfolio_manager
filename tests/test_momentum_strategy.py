"""Unit tests for MomentumStrategy, including the rejection-recovery regression."""
import pytest

from hft.core.types import Side, Tick
from hft.strategy.momentum import MomentumStrategy


class StubContext:
    """Minimal StrategyContext stand-in with controllable acceptance.

    When ``accept`` is False, orders are recorded but the position never moves —
    exactly what happens when the risk manager rejects an order.
    """

    def __init__(self, accept: bool = True, start_position: float = 0.0):
        self.accept = accept
        self._pos = start_position
        self.orders: list[tuple[Side, float]] = []

    def market_order(self, symbol, side, quantity):
        self.orders.append((side, quantity))
        if self.accept:
            self._pos += quantity * side.sign
        return object()

    def position(self, symbol):
        return self._pos


class CappedContext:
    """Accepts orders but clamps the position magnitude to ``cap``.

    Models a binding buying-power limit: top-up orders beyond the cap are
    accepted yet leave the position unchanged (a no-op fill).
    """

    def __init__(self, cap: float):
        self.cap = cap
        self._pos = 0.0
        self.orders: list[tuple[Side, float]] = []

    def market_order(self, symbol, side, quantity):
        self.orders.append((side, quantity))
        target = self._pos + quantity * side.sign
        if abs(target) > self.cap:
            target = self.cap * (1 if target > 0 else -1)
        self._pos = target
        return object()

    def position(self, symbol):
        return self._pos


def _uptrend(strat, ctx, n=12, start=100.0):
    """Feed a steadily rising series so the signal is firmly long."""
    for i in range(n):
        strat.on_tick(Tick(strat.symbol, float(i), start + i - 0.02, start + i + 0.02), ctx)


def _downtrend(strat, ctx, n=12, start=200.0):
    """Feed a steadily falling series so the signal is firmly short."""
    for i in range(n):
        strat.on_tick(Tick(strat.symbol, float(i), start - i - 0.02, start - i + 0.02), ctx)


def test_validates_periods_and_size():
    with pytest.raises(ValueError):
        MomentumStrategy("X", fast_period=10, slow_period=5)
    with pytest.raises(ValueError):
        MomentumStrategy("X", max_order_size=0)


def test_trades_toward_target_on_uptrend():
    strat = MomentumStrategy("X", fast_period=2, slow_period=4, target_position=30)
    ctx = StubContext(accept=True)
    _uptrend(strat, ctx)
    # Should have gone long and parked at the target, not beyond it.
    assert ctx.position("X") == pytest.approx(30)
    assert all(side is Side.BUY for side, _ in ctx.orders)


def test_retries_after_rejection_instead_of_getting_stuck():
    # Regression: previously a single crossover order was sent and the signal
    # state updated regardless, so a rejected order left the position stuck.
    strat = MomentumStrategy("X", fast_period=2, slow_period=4, target_position=30)
    ctx = StubContext(accept=False)  # every order is rejected -> position stays 0
    _uptrend(strat, ctx, n=12)
    # The position never moved (all rejected) ...
    assert ctx.position("X") == 0
    # ... but the strategy kept trying on subsequent ticks rather than giving up.
    assert len(ctx.orders) >= 3
    assert all(side is Side.BUY for side, _ in ctx.orders)


def test_max_order_size_chunks_large_positions():
    strat = MomentumStrategy("X", fast_period=2, slow_period=4,
                             target_position=100, max_order_size=10)
    ctx = StubContext(accept=True)
    _uptrend(strat, ctx, n=20)
    # No single order exceeds the cap ...
    assert all(qty <= 10 + 1e-9 for _, qty in ctx.orders)
    # ... and over enough ticks the position still reaches the target.
    assert ctx.position("X") == pytest.approx(100)


def test_wrong_side_keeps_retrying_even_when_rejected():
    # The dangerous case: signal says short but we're stuck long. Must keep
    # trying to correct the direction on every tick until it goes through.
    strat = MomentumStrategy("X", fast_period=2, slow_period=4, target_position=30)
    ctx = StubContext(accept=False, start_position=30)  # all flips rejected
    _downtrend(strat, ctx, n=12)
    assert ctx.position("X") == 30  # never moved (all rejected)
    assert len(ctx.orders) >= 3  # but kept trying to flip short
    assert all(side is Side.SELL for side, _ in ctx.orders)


def test_stall_guard_stops_churning_on_blocked_topups():
    # Correct side but a binding limit caps magnitude below target: the strategy
    # should stop re-firing rejected top-up orders rather than one per tick.
    strat = MomentumStrategy("X", fast_period=2, slow_period=4, target_position=30)
    ctx = CappedContext(cap=5)  # can only ever hold 5 units
    _uptrend(strat, ctx, n=20)
    assert ctx.position("X") == pytest.approx(5)  # capped on the correct side
    assert len(ctx.orders) <= 3  # did not churn ~20 rejected top-ups
    assert all(side is Side.BUY for side, _ in ctx.orders)


def test_no_order_when_already_at_target():
    strat = MomentumStrategy("X", fast_period=2, slow_period=4, target_position=30)
    ctx = StubContext(accept=True, start_position=30)
    _uptrend(strat, ctx)
    # Already long at target on an uptrend -> no further orders.
    assert ctx.orders == []
