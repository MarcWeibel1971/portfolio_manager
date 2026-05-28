import pytest

from hft.core.types import Order, OrderStatus, OrderType, Side, Tick


def test_side_sign_and_opposite():
    assert Side.BUY.sign == 1
    assert Side.SELL.sign == -1
    assert Side.BUY.opposite is Side.SELL
    assert Side.SELL.opposite is Side.BUY


def test_tick_mid_and_spread():
    tick = Tick(symbol="X", timestamp=0.0, bid=99.0, ask=101.0)
    assert tick.mid == 100.0
    assert tick.spread == 2.0


def test_order_validation():
    with pytest.raises(ValueError):
        Order(symbol="X", side=Side.BUY, quantity=0)
    with pytest.raises(ValueError):
        Order(symbol="X", side=Side.BUY, quantity=1, order_type=OrderType.LIMIT)


def test_order_ids_are_unique():
    a = Order(symbol="X", side=Side.BUY, quantity=1)
    b = Order(symbol="X", side=Side.BUY, quantity=1)
    assert a.order_id != b.order_id


def test_partial_then_full_fill_updates_vwap_and_status():
    order = Order(symbol="X", side=Side.BUY, quantity=10)
    order.apply_fill(4, 100.0)
    assert order.status is OrderStatus.PARTIALLY_FILLED
    assert order.filled_quantity == 4
    order.apply_fill(6, 110.0)
    assert order.status is OrderStatus.FILLED
    assert order.remaining_quantity == pytest.approx(0.0)
    # VWAP = (4*100 + 6*110) / 10 = 106
    assert order.avg_fill_price == pytest.approx(106.0)


def test_overfill_rejected():
    order = Order(symbol="X", side=Side.BUY, quantity=5)
    with pytest.raises(ValueError):
        order.apply_fill(6, 100.0)
