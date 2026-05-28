"""Paper-trading broker: simulated fills against live ticks.

Fill model (deliberately simple but not naive):
  * MARKET orders fill immediately at the opposite side of the book plus a
    configurable slippage, charged commission on notional.
  * LIMIT orders rest until a tick crosses their price, then fill at the limit.

This is the default execution venue — it never touches a real exchange, so the
whole stack is safe to run end-to-end without credentials or risk of real loss.
"""
from __future__ import annotations

from hft.core.types import (
    Fill,
    Order,
    OrderStatus,
    OrderType,
    Side,
)
from hft.execution.broker import Broker


class PaperBroker(Broker):
    def __init__(
        self,
        commission_rate: float = 0.0005,  # 5 bps per trade
        slippage_bps: float = 1.0,  # market-order slippage in basis points
    ) -> None:
        super().__init__()
        self.commission_rate = commission_rate
        self.slippage_bps = slippage_bps
        self._resting: dict[int, Order] = {}
        self._last_tick: dict[str, "Tick"] = {}  # noqa: F821 (fwd ref for typing only)

    # -- order entry --------------------------------------------------------
    def submit(self, order: Order) -> None:
        last = self._last_tick.get(order.symbol)
        if order.order_type is OrderType.MARKET:
            if last is None:
                order.status = OrderStatus.REJECTED
                return
            self._fill_market(order, last)
        else:
            # Resting limit order — may fill immediately if marketable.
            self._resting[order.order_id] = order
            if last is not None:
                self._try_fill_limit(order, last)

    def cancel(self, order_id: int) -> bool:
        order = self._resting.pop(order_id, None)
        if order is None:
            return False
        if order.is_active:
            order.status = OrderStatus.CANCELLED
            return True
        return False

    # -- market data --------------------------------------------------------
    def on_tick(self, tick) -> None:  # type: ignore[no-untyped-def]
        self._last_tick[tick.symbol] = tick
        # Walk a copy because fills mutate the resting book.
        for order in list(self._resting.values()):
            if order.symbol == tick.symbol and order.is_active:
                self._try_fill_limit(order, tick)

    # -- fill mechanics -----------------------------------------------------
    def _fill_market(self, order, tick) -> None:  # type: ignore[no-untyped-def]
        # Cross the spread: buys lift the ask, sells hit the bid.
        base = tick.ask if order.side is Side.BUY else tick.bid
        slip = base * (self.slippage_bps / 10_000.0) * order.side.sign
        price = base + slip
        self._execute(order, order.remaining_quantity, price)

    def _try_fill_limit(self, order, tick) -> None:  # type: ignore[no-untyped-def]
        # A buy limit fills when the ask drops to or below it; a sell limit
        # fills when the bid rises to or above it.
        marketable = (
            order.side is Side.BUY and tick.ask <= order.limit_price
        ) or (order.side is Side.SELL and tick.bid >= order.limit_price)
        if marketable:
            self._execute(order, order.remaining_quantity, order.limit_price)

    def _execute(self, order, quantity, price) -> None:  # type: ignore[no-untyped-def]
        commission = abs(quantity * price) * self.commission_rate
        order.apply_fill(quantity, price)
        if order.status is OrderStatus.FILLED:
            self._resting.pop(order.order_id, None)
        self._emit_fill(
            Fill(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=quantity,
                price=price,
                timestamp=getattr(self._last_tick.get(order.symbol), "timestamp", 0.0),
                commission=commission,
            )
        )

    @property
    def open_orders(self) -> list[Order]:
        return [o for o in self._resting.values() if o.is_active]
