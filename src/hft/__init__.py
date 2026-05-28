"""hft — an event-driven algorithmic / high-frequency trading bot stack.

Top-level convenience imports for the most-used building blocks.
"""
from hft.backtest.engine import Backtester, BacktestResult
from hft.core.types import Fill, Order, OrderType, Side, Tick
from hft.data.simulated import CsvFeed, SimulatedFeed
from hft.engine import TradingEngine
from hft.execution.paper import PaperBroker
from hft.portfolio.portfolio import Portfolio
from hft.risk.manager import RiskLimits, RiskManager
from hft.strategy.base import Strategy
from hft.strategy.market_making import MarketMakingStrategy
from hft.strategy.momentum import MomentumStrategy

__version__ = "0.1.0"

__all__ = [
    "Backtester",
    "BacktestResult",
    "CsvFeed",
    "Fill",
    "MarketMakingStrategy",
    "MomentumStrategy",
    "Order",
    "OrderType",
    "PaperBroker",
    "Portfolio",
    "RiskLimits",
    "RiskManager",
    "Side",
    "SimulatedFeed",
    "Strategy",
    "Tick",
    "TradingEngine",
]
