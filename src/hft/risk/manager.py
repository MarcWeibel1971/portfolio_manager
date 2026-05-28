"""Pre-trade risk checks.

The risk manager sits between strategies and the broker. Every order must pass
``check`` before it is sent. Limits are intentionally simple and explicit so
they are easy to audit — risk code you cannot read is risk code you cannot trust.
"""
from __future__ import annotations

from dataclasses import dataclass

from hft.core.types import Order, OrderType
from hft.portfolio.portfolio import Portfolio


@dataclass
class RiskLimits:
    """Configurable pre-trade limits. ``None`` disables an individual check."""

    max_order_quantity: float | None = None  # max units per single order
    max_position: float | None = None  # max absolute units held per symbol
    max_gross_exposure: float | None = None  # max sum of |position notional|
    max_notional_per_order: float | None = None  # max value of a single order
    max_drawdown: float | None = None  # halt trading below starting_cash - this


@dataclass
class RiskDecision:
    approved: bool
    reason: str = ""

    def __bool__(self) -> bool:  # allow `if decision:`
        return self.approved


class RiskManager:
    """Stateless-per-call validator that reads live state from the portfolio."""

    def __init__(self, limits: RiskLimits, portfolio: Portfolio) -> None:
        self.limits = limits
        self.portfolio = portfolio
        self.halted = False

    def _reference_price(self, order: Order, market_price: float | None) -> float | None:
        """Best available price for notional estimation."""
        if order.order_type is OrderType.LIMIT and order.limit_price is not None:
            return order.limit_price
        if market_price is not None:
            return market_price
        pos = self.portfolio.positions.get(order.symbol)
        return pos.last_price if pos and pos.last_price > 0 else None

    def check(self, order: Order, market_price: float | None = None) -> RiskDecision:
        """Return a :class:`RiskDecision`; ``market_price`` aids notional checks."""
        lim = self.limits

        if self.halted:
            return RiskDecision(False, "trading halted by drawdown limit")

        # Drawdown circuit breaker — evaluated against current equity.
        if lim.max_drawdown is not None:
            drawdown = self.portfolio.starting_cash - self.portfolio.equity
            if drawdown >= lim.max_drawdown:
                self.halted = True
                return RiskDecision(
                    False, f"max drawdown breached ({drawdown:.2f} >= {lim.max_drawdown})"
                )

        if lim.max_order_quantity is not None and order.quantity > lim.max_order_quantity:
            return RiskDecision(
                False,
                f"order qty {order.quantity} > max {lim.max_order_quantity}",
            )

        price = self._reference_price(order, market_price)

        if lim.max_notional_per_order is not None and price is not None:
            notional = order.quantity * price
            if notional > lim.max_notional_per_order:
                return RiskDecision(
                    False,
                    f"order notional {notional:.2f} > max {lim.max_notional_per_order}",
                )

        # Projected position after this order fills fully.
        current_qty = self.portfolio.position(order.symbol).quantity
        projected_qty = current_qty + order.quantity * order.side.sign

        if lim.max_position is not None and abs(projected_qty) > lim.max_position:
            return RiskDecision(
                False,
                f"projected position {projected_qty} exceeds max {lim.max_position}",
            )

        if lim.max_gross_exposure is not None and price is not None:
            # Replace this symbol's contribution with the projected one.
            others = self.portfolio.gross_exposure() - abs(
                self.portfolio.position(order.symbol).market_value
            )
            projected_gross = others + abs(projected_qty) * price
            if projected_gross > lim.max_gross_exposure:
                return RiskDecision(
                    False,
                    f"projected gross exposure {projected_gross:.2f} > "
                    f"max {lim.max_gross_exposure}",
                )

        return RiskDecision(True)
