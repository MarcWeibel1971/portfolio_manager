from hft.core.types import Order, OrderStatus, OrderType, Side, Tick
from hft.execution.paper import PaperBroker


def tick(symbol="X", bid=99.0, ask=101.0, ts=0.0):
    return Tick(symbol=symbol, timestamp=ts, bid=bid, ask=ask, last=(bid + ask) / 2)


def collect_fills(broker):
    fills = []
    broker.on_fill(fills.append)
    return fills


def test_market_buy_lifts_ask_with_slippage():
    broker = PaperBroker(commission_rate=0.0, slippage_bps=10.0)
    fills = collect_fills(broker)
    broker.on_tick(tick(ask=100.0, bid=99.0))
    broker.submit(Order("X", Side.BUY, 5, OrderType.MARKET))
    assert len(fills) == 1
    # 100 * (1 + 10bps) = 100.1
    assert abs(fills[0].price - 100.1) < 1e-6
    assert fills[0].quantity == 5


def test_market_order_without_data_is_rejected():
    broker = PaperBroker()
    order = Order("X", Side.BUY, 5, OrderType.MARKET)
    broker.submit(order)
    assert order.status is OrderStatus.REJECTED


def test_limit_buy_rests_until_marketable():
    broker = PaperBroker(commission_rate=0.0)
    fills = collect_fills(broker)
    broker.on_tick(tick(bid=99.0, ask=101.0))
    order = Order("X", Side.BUY, 5, OrderType.LIMIT, limit_price=100.0)
    broker.submit(order)
    assert order.is_active
    assert len(fills) == 0
    # Ask drops to 100 -> limit becomes marketable.
    broker.on_tick(tick(bid=98.0, ask=100.0))
    assert order.status is OrderStatus.FILLED
    assert fills[0].price == 100.0


def test_limit_sell_fills_when_bid_rises():
    broker = PaperBroker(commission_rate=0.0)
    fills = collect_fills(broker)
    broker.on_tick(tick(bid=99.0, ask=101.0))
    order = Order("X", Side.SELL, 5, OrderType.LIMIT, limit_price=100.0)
    broker.submit(order)
    assert len(fills) == 0
    broker.on_tick(tick(bid=100.0, ask=102.0))
    assert order.status is OrderStatus.FILLED


def test_cancel_resting_order():
    broker = PaperBroker()
    broker.on_tick(tick())
    order = Order("X", Side.BUY, 5, OrderType.LIMIT, limit_price=50.0)
    broker.submit(order)
    assert broker.cancel(order.order_id) is True
    assert order.status is OrderStatus.CANCELLED
    assert broker.cancel(order.order_id) is False  # already gone


def test_commission_charged_on_notional():
    broker = PaperBroker(commission_rate=0.001, slippage_bps=0.0)
    fills = collect_fills(broker)
    broker.on_tick(tick(ask=100.0, bid=100.0))
    broker.submit(Order("X", Side.BUY, 10, OrderType.MARKET))
    assert abs(fills[0].commission - (10 * 100.0 * 0.001)) < 1e-9
