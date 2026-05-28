"""Tests für den Live-Adapter mit einem nachgebildeten Börsen-Client (Fake)."""
import pytest

from hft.core.types import Order, OrderStatus, OrderType, Side, Tick
from hft.execution.live import ExchangeClient, LiveBroker


class FakeExchange:
    """Nachbildung einer Börse zum Testen des Abgleichs ohne Netzwerk."""

    def __init__(self):
        self.orders: dict[str, dict] = {}
        self._next = iter(range(1, 1_000_000))
        self.created: list[dict] = []

    def create_order(self, symbol, side, order_type, quantity, price=None):
        oid = f"E{next(self._next)}"
        self.created.append(
            {"symbol": symbol, "side": side, "type": order_type, "qty": quantity, "price": price}
        )
        if order_type == "market":
            # Market-Order: sofort vollständig ausgeführt.
            state = {
                "id": oid,
                "status": "closed",
                "filled": quantity,
                "average": price or 100.0,
                "fee_cost": (price or 100.0) * quantity * 0.001,
            }
        else:
            # Limit-Order: ruht zunächst offen.
            state = {"id": oid, "status": "open", "filled": 0.0, "average": 0.0, "fee_cost": 0.0}
        self.orders[oid] = state
        return state

    def cancel_order(self, exchange_order_id, symbol):
        self.orders[exchange_order_id]["status"] = "canceled"
        return True

    def fetch_order(self, exchange_order_id, symbol):
        return self.orders[exchange_order_id]

    # Testhilfe: Limit-Order extern (teil-)ausführen.
    def fill(self, exchange_order_id, filled, average, fee_cost=0.0, closed=True):
        o = self.orders[exchange_order_id]
        o["filled"] = filled
        o["average"] = average
        o["fee_cost"] = fee_cost
        o["status"] = "closed" if closed else "open"


def test_fake_satisfies_protocol():
    assert isinstance(FakeExchange(), ExchangeClient)


def test_requires_confirm_live():
    with pytest.raises(RuntimeError):
        LiveBroker(FakeExchange())  # confirm_live fehlt


def test_market_order_fills_immediately():
    ex = FakeExchange()
    broker = LiveBroker(ex, confirm_live=True)
    fills = []
    broker.on_fill(fills.append)

    order = Order("BTC/USDT", Side.BUY, 2, OrderType.MARKET)
    # Preis kommt vom Fake (average=100), Market hat keinen limit_price.
    ex_default_price = 100.0
    broker.submit(order)

    assert order.status is OrderStatus.FILLED
    assert len(fills) == 1
    assert fills[0].quantity == 2
    assert fills[0].price == ex_default_price
    assert fills[0].commission == pytest.approx(100.0 * 2 * 0.001)
    assert ex.created[0]["type"] == "market"


def test_limit_order_rests_then_fills_on_poll():
    ex = FakeExchange()
    broker = LiveBroker(ex, confirm_live=True)
    fills = []
    broker.on_fill(fills.append)

    order = Order("BTC/USDT", Side.BUY, 5, OrderType.LIMIT, limit_price=99.0)
    broker.submit(order)
    assert order.is_active
    assert fills == []

    # Börse führt die Order aus; beim nächsten Tick wird abgeglichen.
    exch_id = broker._exch_ids[order.order_id]
    ex.fill(exch_id, filled=5, average=99.0, fee_cost=0.5)
    broker.on_tick(Tick("BTC/USDT", timestamp=1.0, bid=98.5, ask=99.5))

    assert order.status is OrderStatus.FILLED
    assert len(fills) == 1
    assert fills[0].quantity == 5
    assert fills[0].price == 99.0
    assert fills[0].commission == pytest.approx(0.5)


def test_partial_fills_are_incremental():
    ex = FakeExchange()
    broker = LiveBroker(ex, confirm_live=True)
    fills = []
    broker.on_fill(fills.append)

    order = Order("BTC/USDT", Side.SELL, 10, OrderType.LIMIT, limit_price=101.0)
    broker.submit(order)
    exch_id = broker._exch_ids[order.order_id]

    # Erst 4 von 10, dann der Rest — es dürfen nur die Deltas gemeldet werden.
    ex.fill(exch_id, filled=4, average=101.0, fee_cost=0.4, closed=False)
    broker.on_tick(Tick("BTC/USDT", 1.0, 100.5, 101.5))
    ex.fill(exch_id, filled=10, average=101.0, fee_cost=1.0, closed=True)
    broker.on_tick(Tick("BTC/USDT", 2.0, 100.5, 101.5))

    assert [f.quantity for f in fills] == [4, 6]
    assert sum(f.commission for f in fills) == pytest.approx(1.0)
    assert order.status is OrderStatus.FILLED


def test_cancel_marks_order_cancelled():
    ex = FakeExchange()
    broker = LiveBroker(ex, confirm_live=True)
    order = Order("BTC/USDT", Side.BUY, 5, OrderType.LIMIT, limit_price=50.0)
    broker.submit(order)
    assert broker.cancel(order.order_id) is True
    assert order.status is OrderStatus.CANCELLED
    assert broker.cancel(999) is False  # unbekannte Order


def test_create_failure_rejects_order():
    class Boom(FakeExchange):
        def create_order(self, *a, **k):
            raise RuntimeError("exchange down")

    broker = LiveBroker(Boom(), confirm_live=True)
    order = Order("BTC/USDT", Side.BUY, 1, OrderType.MARKET)
    broker.submit(order)
    assert order.status is OrderStatus.REJECTED
