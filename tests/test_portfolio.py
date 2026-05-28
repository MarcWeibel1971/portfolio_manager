import pytest

from hft.core.types import Fill, Side
from hft.portfolio.portfolio import Portfolio


def fill(symbol, side, qty, price, commission=0.0):
    return Fill(order_id=1, symbol=symbol, side=side, quantity=qty, price=price,
                commission=commission)


def test_long_then_close_realizes_pnl():
    pf = Portfolio(starting_cash=10_000)
    pf.apply_fill(fill("X", Side.BUY, 10, 100.0))
    assert pf.cash == pytest.approx(9_000.0)
    pos = pf.position("X")
    assert pos.quantity == 10
    assert pos.avg_price == pytest.approx(100.0)

    pf.apply_fill(fill("X", Side.SELL, 10, 110.0))
    assert pf.position("X").quantity == 0
    assert pf.realized_pnl == pytest.approx(100.0)  # (110-100)*10
    assert pf.cash == pytest.approx(10_100.0)


def test_short_then_cover_realizes_pnl():
    pf = Portfolio(starting_cash=10_000)
    pf.apply_fill(fill("X", Side.SELL, 5, 100.0))
    assert pf.position("X").quantity == -5
    pf.apply_fill(fill("X", Side.BUY, 5, 90.0))
    # Short sold at 100, covered at 90 -> +10 * 5 = 50
    assert pf.realized_pnl == pytest.approx(50.0)


def test_average_cost_on_scaling_in():
    pf = Portfolio()
    pf.apply_fill(fill("X", Side.BUY, 10, 100.0))
    pf.apply_fill(fill("X", Side.BUY, 10, 120.0))
    assert pf.position("X").avg_price == pytest.approx(110.0)
    assert pf.position("X").quantity == 20


def test_position_flip_resets_avg_price():
    pf = Portfolio()
    pf.apply_fill(fill("X", Side.BUY, 10, 100.0))
    # Sell 15: closes 10 long (realizes (130-100)*10=300), opens 5 short at 130
    pf.apply_fill(fill("X", Side.SELL, 15, 130.0))
    pos = pf.position("X")
    assert pos.quantity == -5
    assert pos.avg_price == pytest.approx(130.0)
    assert pos.realized_pnl == pytest.approx(300.0)


def test_unrealized_pnl_and_equity_mark():
    pf = Portfolio(starting_cash=10_000)
    pf.apply_fill(fill("X", Side.BUY, 10, 100.0))
    pf.mark("X", 105.0)
    assert pf.unrealized_pnl == pytest.approx(50.0)
    # cash 9000 + 10 units * 105 = 10050
    assert pf.equity == pytest.approx(10_050.0)
    assert pf.total_pnl == pytest.approx(50.0)


def test_commission_reduces_cash_and_pnl():
    pf = Portfolio(starting_cash=10_000)
    pf.apply_fill(fill("X", Side.BUY, 10, 100.0, commission=5.0))
    assert pf.cash == pytest.approx(8_995.0)
    assert pf.position("X").realized_pnl == pytest.approx(-5.0)


def test_gross_vs_net_exposure():
    pf = Portfolio()
    pf.apply_fill(fill("A", Side.BUY, 10, 100.0))
    pf.apply_fill(fill("B", Side.SELL, 10, 100.0))
    pf.mark("A", 100.0)
    pf.mark("B", 100.0)
    assert pf.net_exposure() == pytest.approx(0.0)
    assert pf.gross_exposure() == pytest.approx(2_000.0)
