"""A simple inventory-aware market-making strategy.

Quotes a symmetric bid/ask around the mid, skewing quotes against inventory so
the book pulls the position back toward flat. This is a textbook
Avellaneda-Stoikov-lite heuristic, not a production quoter — but it exercises
the full resting-limit-order path of the stack.
"""
from __future__ import annotations

from hft.core.types import Fill, Side, Tick
from hft.strategy.base import Strategy, StrategyContext


class MarketMakingStrategy(Strategy):
    def __init__(
        self,
        symbol: str,
        quote_size: float = 10.0,
        spread_bps: float = 10.0,  # half-spread each side, in bps of mid
        max_inventory: float = 100.0,
        inventory_skew_bps: float = 5.0,  # max quote skew at full inventory
        name: str | None = None,
    ) -> None:
        super().__init__(name)
        self.symbol = symbol
        self.quote_size = quote_size
        self.spread_bps = spread_bps
        self.max_inventory = max_inventory
        self.inventory_skew_bps = inventory_skew_bps
        self._bid_id: int | None = None
        self._ask_id: int | None = None

    def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        if tick.symbol != self.symbol:
            return

        # Cancel stale quotes before re-quoting around the new mid.
        if self._bid_id is not None:
            ctx.cancel(self._bid_id)
        if self._ask_id is not None:
            ctx.cancel(self._ask_id)

        mid = tick.mid
        inventory = ctx.position(self.symbol)
        # Skew in [-1, 1]: long inventory shifts quotes down to encourage selling.
        skew_frac = max(-1.0, min(1.0, inventory / self.max_inventory))
        skew = mid * (self.inventory_skew_bps / 10_000.0) * skew_frac
        half_spread = mid * (self.spread_bps / 10_000.0)

        bid_px = mid - half_spread - skew
        ask_px = mid + half_spread - skew

        # Only quote a side if it keeps us within the inventory band.
        if inventory < self.max_inventory:
            self._bid_id = ctx.limit_order(self.symbol, Side.BUY, self.quote_size, bid_px).order_id
        else:
            self._bid_id = None
        if inventory > -self.max_inventory:
            self._ask_id = ctx.limit_order(
                self.symbol, Side.SELL, self.quote_size, ask_px
            ).order_id
        else:
            self._ask_id = None

    def on_fill(self, fill: Fill, ctx: StrategyContext) -> None:
        # Clear the filled quote id so we don't try to cancel a dead order.
        if fill.side is Side.BUY:
            self._bid_id = None
        else:
            self._ask_id = None
