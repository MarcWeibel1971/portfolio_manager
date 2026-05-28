"""The trading engine: the event loop that ties the stack together.

Per tick the engine:
  1. marks the portfolio to the new price,
  2. lets the broker match resting orders (emitting fills),
  3. invokes the strategy, routing every order intent through the risk manager.

Fills flow back through a single handler that updates the portfolio and notifies
the strategy. The same engine drives both live and simulated feeds — only the
``feed`` and ``broker`` differ.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable

from hft.core.types import Fill, Order, Tick
from hft.data.feed import MarketDataFeed
from hft.execution.broker import Broker
from hft.portfolio.portfolio import Portfolio
from hft.risk.manager import RiskManager
from hft.strategy.base import Strategy, StrategyContext

logger = logging.getLogger("hft.engine")


class TradingEngine:
    def __init__(
        self,
        strategy: Strategy,
        broker: Broker,
        portfolio: Portfolio,
        risk: RiskManager,
    ) -> None:
        self.strategy = strategy
        self.broker = broker
        self.portfolio = portfolio
        self.risk = risk

        self.rejected_orders = 0
        self.submitted_orders = 0
        self.fills: list[Fill] = []
        self._last_price: dict[str, float] = {}

        self.ctx = StrategyContext(
            portfolio=portfolio,
            submit=self._submit,
            cancel=broker.cancel,
        )
        broker.on_fill(self._handle_fill)

    # -- order routing ------------------------------------------------------
    def _submit(self, order: Order) -> None:
        market_price = self._last_price.get(order.symbol)
        decision = self.risk.check(order, market_price)
        if not decision:
            self.rejected_orders += 1
            logger.debug("Order %s rejected: %s", order.order_id, decision.reason)
            return
        self.submitted_orders += 1
        self.broker.submit(order)

    def _handle_fill(self, fill: Fill) -> None:
        self.fills.append(fill)
        self.portfolio.apply_fill(fill)
        self.strategy.on_fill(fill, self.ctx)

    # -- main loop ----------------------------------------------------------
    def process_tick(self, tick: Tick) -> None:
        self._last_price[tick.symbol] = tick.mid
        self.portfolio.mark(tick.symbol, tick.mid)
        self.broker.on_tick(tick)  # may emit fills for resting orders
        self.strategy.on_tick(tick, self.ctx)

    def run(self, feed: MarketDataFeed | Iterable[Tick]) -> None:
        """Drive the engine over a feed from start to finish."""
        self.strategy.on_start(self.ctx)
        for tick in feed:
            self.process_tick(tick)
        self.strategy.on_stop(self.ctx)
