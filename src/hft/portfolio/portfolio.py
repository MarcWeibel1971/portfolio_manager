"""Position, cash and P&L bookkeeping.

The portfolio is the single source of truth for "what do we hold and how are we
doing". It is updated from fills and marked-to-market from ticks.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from hft.core.types import Fill


@dataclass
class Position:
    """A single-symbol position tracked with average-cost accounting."""

    symbol: str
    quantity: float = 0.0  # signed: positive = long, negative = short
    avg_price: float = 0.0  # average entry price of the open position
    realized_pnl: float = 0.0
    last_price: float = 0.0  # most recent mark

    def apply_fill(self, fill: Fill) -> None:
        """Update the position from a fill, realizing P&L when reducing/closing."""
        signed_qty = fill.quantity * fill.side.sign
        new_quantity = self.quantity + signed_qty

        if self.quantity == 0 or (self.quantity > 0) == (signed_qty > 0):
            # Opening or increasing the position in the same direction.
            total_cost = self.avg_price * abs(self.quantity) + fill.price * fill.quantity
            self.avg_price = total_cost / abs(new_quantity) if new_quantity != 0 else 0.0
        else:
            # Reducing, closing, or flipping the position.
            closing_qty = min(abs(signed_qty), abs(self.quantity))
            # Realized P&L = (exit - entry) * closed units, signed by original side.
            direction = 1 if self.quantity > 0 else -1
            self.realized_pnl += (fill.price - self.avg_price) * closing_qty * direction
            if (self.quantity > 0) != (new_quantity > 0) and new_quantity != 0:
                # Position flipped: the residual opens at the fill price.
                self.avg_price = fill.price
            elif new_quantity == 0:
                self.avg_price = 0.0
            # else: partial reduction keeps the same avg_price.

        self.quantity = new_quantity
        self.realized_pnl -= fill.commission
        self.last_price = fill.price

    def mark(self, price: float) -> None:
        self.last_price = price

    @property
    def unrealized_pnl(self) -> float:
        if self.quantity == 0:
            return 0.0
        return (self.last_price - self.avg_price) * self.quantity

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price


@dataclass
class Portfolio:
    """Aggregate of cash plus per-symbol positions."""

    starting_cash: float = 100_000.0
    cash: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cash = self.starting_cash

    def position(self, symbol: str) -> Position:
        return self.positions.setdefault(symbol, Position(symbol))

    def apply_fill(self, fill: Fill) -> None:
        """Settle cash and update the relevant position from a fill."""
        # Cash decreases when buying, increases when selling; commission always costs.
        self.cash -= fill.side.sign * fill.notional
        self.cash -= fill.commission
        self.position(fill.symbol).apply_fill(fill)

    def mark(self, symbol: str, price: float) -> None:
        if symbol in self.positions:
            self.positions[symbol].mark(price)

    @property
    def realized_pnl(self) -> float:
        return sum(p.realized_pnl for p in self.positions.values())

    @property
    def unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def positions_value(self) -> float:
        return sum(p.market_value for p in self.positions.values())

    @property
    def equity(self) -> float:
        """Total account value: cash + marked-to-market positions."""
        return self.cash + self.positions_value

    @property
    def total_pnl(self) -> float:
        return self.equity - self.starting_cash

    def net_exposure(self) -> float:
        """Signed sum of position market values (long positive, short negative)."""
        return self.positions_value

    def gross_exposure(self) -> float:
        """Sum of absolute position market values."""
        return sum(abs(p.market_value) for p in self.positions.values())
