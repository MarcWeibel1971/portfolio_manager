from hft.core.types import Fill, Order, Side
from hft.portfolio.portfolio import Portfolio
from hft.risk.manager import RiskLimits, RiskManager


def make(limits):
    pf = Portfolio(starting_cash=100_000)
    return pf, RiskManager(limits, pf)


def order(side=Side.BUY, qty=10, symbol="X"):
    return Order(symbol=symbol, side=side, quantity=qty)


def test_approves_within_limits():
    _, rm = make(RiskLimits(max_order_quantity=100))
    assert rm.check(order(qty=10), market_price=100.0)


def test_rejects_oversized_order():
    _, rm = make(RiskLimits(max_order_quantity=5))
    decision = rm.check(order(qty=10))
    assert not decision
    assert "qty" in decision.reason


def test_rejects_notional_breach():
    _, rm = make(RiskLimits(max_notional_per_order=500))
    assert not rm.check(order(qty=10), market_price=100.0)  # 1000 notional


def test_rejects_position_breach():
    pf, rm = make(RiskLimits(max_position=15))
    pf.apply_fill(Fill(order_id=1, symbol="X", side=Side.BUY, quantity=10, price=100.0))
    # +10 existing, +10 more would be 20 > 15
    assert not rm.check(order(qty=10), market_price=100.0)
    # +5 more -> 15, allowed
    assert rm.check(order(qty=5), market_price=100.0)


def test_gross_exposure_limit():
    pf, rm = make(RiskLimits(max_gross_exposure=1_500))
    pf.apply_fill(Fill(order_id=1, symbol="X", side=Side.BUY, quantity=10, price=100.0))
    pf.mark("X", 100.0)
    # existing gross 1000; +10 @100 -> 2000 > 1500
    assert not rm.check(order(qty=10), market_price=100.0)


def test_max_leverage_caps_buying_power():
    # 100k equity, leverage 1.0 -> can't take more than 100k of exposure.
    pf, rm = make(RiskLimits(max_leverage=1.0))
    # 500 units @ 100 = 50k -> within buying power.
    assert rm.check(order(qty=500), market_price=100.0)
    # 1500 units @ 100 = 150k -> exceeds 100k buying power.
    decision = rm.check(order(qty=1500), market_price=100.0)
    assert not decision
    assert "buying power" in decision.reason


def test_max_leverage_allows_borrowing_above_one():
    pf, rm = make(RiskLimits(max_leverage=3.0))
    # 100k equity x3 = 300k allowed; 2500 units @ 100 = 250k -> ok.
    assert rm.check(order(qty=2500), market_price=100.0)
    # 3500 units @ 100 = 350k -> over 300k.
    assert not rm.check(order(qty=3500), market_price=100.0)


def test_max_leverage_uses_live_equity():
    pf, rm = make(RiskLimits(max_leverage=1.0))
    # Drain equity via a realized loss, buying power shrinks accordingly.
    pf.apply_fill(Fill(order_id=1, symbol="Y", side=Side.BUY, quantity=10, price=100.0))
    pf.apply_fill(Fill(order_id=2, symbol="Y", side=Side.SELL, quantity=10, price=50.0))
    # Equity now ~95k (lost 500). 10 units Y closed; check a new symbol order.
    assert pf.equity < 100_000
    # 1000 @ 100 = 100k now exceeds reduced buying power.
    assert not rm.check(order(qty=1000, symbol="X"), market_price=100.0)


def test_drawdown_halts_trading():
    pf, rm = make(RiskLimits(max_drawdown=1_000))
    # Force equity down by 1500 via a marked loss.
    pf.apply_fill(Fill(order_id=1, symbol="X", side=Side.BUY, quantity=100, price=100.0))
    pf.mark("X", 85.0)  # lost 1500
    assert not rm.check(order(qty=1), market_price=85.0)
    assert rm.halted
    # Stays halted even after recovery.
    pf.mark("X", 200.0)
    assert not rm.check(order(qty=1), market_price=200.0)
