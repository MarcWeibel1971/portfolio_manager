"""Core domain types shared across the trading stack.

These are deliberately small, immutable-where-sensible dataclasses so they are
cheap to create on a hot path and easy to reason about in tests.
"""
from __future__ import annotations

import enum
import itertools
import time
from dataclasses import dataclass, field


class Side(enum.Enum):
    """Direction of an order or trade."""

    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        """+1 for BUY, -1 for SELL. Handy for signed position maths."""
        return 1 if self is Side.BUY else -1

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


class OrderType(enum.Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(enum.Enum):
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# Monotonic order-id generator. Process-local, which is all a single engine needs.
_order_id_counter = itertools.count(1)


def next_order_id() -> int:
    return next(_order_id_counter)


@dataclass(frozen=True)
class Tick:
    """A single top-of-book / trade observation for one symbol."""

    symbol: str
    timestamp: float  # epoch seconds (float for sub-second resolution)
    bid: float
    ask: float
    last: float = 0.0
    volume: float = 0.0

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass
class Order:
    """An order request and its evolving fill state."""

    symbol: str
    side: Side
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    order_id: int = field(default_factory=next_order_id)
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(f"Order quantity must be positive, got {self.quantity}")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT orders require a limit_price")

    @property
    def remaining_quantity(self) -> float:
        return self.quantity - self.filled_quantity

    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)

    def apply_fill(self, quantity: float, price: float) -> None:
        """Record a (partial) fill, updating the volume-weighted average price."""
        if quantity <= 0:
            raise ValueError("Fill quantity must be positive")
        if quantity > self.remaining_quantity + 1e-9:
            raise ValueError(
                f"Fill {quantity} exceeds remaining {self.remaining_quantity}"
            )
        new_filled = self.filled_quantity + quantity
        self.avg_fill_price = (
            self.avg_fill_price * self.filled_quantity + price * quantity
        ) / new_filled
        self.filled_quantity = new_filled
        self.status = (
            OrderStatus.FILLED
            if self.remaining_quantity <= 1e-9
            else OrderStatus.PARTIALLY_FILLED
        )


@dataclass(frozen=True)
class Fill:
    """A confirmed execution against an order."""

    order_id: int
    symbol: str
    side: Side
    quantity: float
    price: float
    timestamp: float = field(default_factory=time.time)
    commission: float = 0.0

    @property
    def notional(self) -> float:
        return self.quantity * self.price
