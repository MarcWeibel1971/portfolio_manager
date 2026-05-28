"""Strategy base class and the context strategies use to act.

A strategy is a pure decision-maker: it observes ticks and fills and emits order
intents through the :class:`StrategyContext`. It never talks to a broker
directly, so the engine can interpose risk checks and the same strategy code
runs identically in backtest and live.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from hft.core.types import Fill, Order, OrderType, Side, Tick
from hft.portfolio.portfolio import Portfolio


class StrategyContext:
    """The handle a strategy uses to submit/cancel orders and read state."""

    def __init__(
        self,
        portfolio: Portfolio,
        submit: Callable[[Order], None],
        cancel: Callable[[int], bool],
    ) -> None:
        self.portfolio = portfolio
        self._submit = submit
        self._cancel = cancel

    def market_order(self, symbol: str, side: Side, quantity: float) -> Order:
        order = Order(symbol=symbol, side=side, quantity=quantity, order_type=OrderType.MARKET)
        self._submit(order)
        return order

    def limit_order(
        self, symbol: str, side: Side, quantity: float, limit_price: float
    ) -> Order:
        order = Order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
        )
        self._submit(order)
        return order

    def cancel(self, order_id: int) -> bool:
        return self._cancel(order_id)

    def position(self, symbol: str) -> float:
        return self.portfolio.position(symbol).quantity


class Strategy(ABC):
    """Subclass and implement :meth:`on_tick`; override the rest as needed."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name or self.__class__.__name__

    def on_start(self, ctx: StrategyContext) -> None:
        """Called once before any ticks. Optional setup hook."""

    @abstractmethod
    def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        """Called for every market data tick. Place the strategy logic here."""

    def on_fill(self, fill: Fill, ctx: StrategyContext) -> None:
        """Called when one of this strategy's orders is (partially) filled."""

    def on_stop(self, ctx: StrategyContext) -> None:
        """Called once after the last tick. Optional teardown hook."""
