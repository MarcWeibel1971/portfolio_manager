from hft.backtest.engine import Backtester
from hft.data.simulated import SimulatedFeed
from hft.risk.manager import RiskLimits
from hft.strategy.market_making import MarketMakingStrategy
from hft.strategy.momentum import MomentumStrategy


def test_momentum_backtest_runs_and_trades():
    strat = MomentumStrategy(symbol="X", fast_period=5, slow_period=15, target_position=20)
    bt = Backtester(strategy=strat, starting_cash=100_000,
                    risk_limits=RiskLimits(max_position=100))
    feed = SimulatedFeed(symbol="X", n_ticks=1000, volatility=0.002, seed=7)
    result = bt.run(feed)

    assert result.n_ticks == 1000
    assert result.n_fills > 0  # crossovers should have generated trades
    assert len(result.equity_curve) == 1000
    # Equity is internally consistent: cash + positions value.
    assert abs(result.ending_equity - bt.portfolio.equity) < 1e-6
    assert isinstance(result.summary(), str)


def test_market_making_backtest_runs():
    strat = MarketMakingStrategy(symbol="X", quote_size=5, spread_bps=20, max_inventory=50)
    bt = Backtester(strategy=strat, starting_cash=100_000,
                    risk_limits=RiskLimits(max_position=200))
    feed = SimulatedFeed(symbol="X", n_ticks=800, volatility=0.001, seed=3)
    result = bt.run(feed)
    assert result.n_ticks == 800
    assert result.n_fills > 0  # quotes should get hit on a random walk


def test_reproducible_with_seed():
    def run():
        strat = MomentumStrategy(symbol="X", fast_period=5, slow_period=15)
        bt = Backtester(strategy=strat)
        return bt.run(SimulatedFeed(symbol="X", n_ticks=500, seed=99)).ending_equity

    assert run() == run()


def test_metrics_bounds():
    strat = MomentumStrategy(symbol="X", fast_period=5, slow_period=15)
    bt = Backtester(strategy=strat)
    result = bt.run(SimulatedFeed(symbol="X", n_ticks=500, seed=1))
    assert 0.0 <= result.max_drawdown <= 1.0
    assert result.total_commission >= 0.0
