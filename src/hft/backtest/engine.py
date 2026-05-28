"""Backtesting harness: run a strategy over historical/simulated data and score it.

Wraps :class:`~hft.engine.TradingEngine`, recording an equity curve as it goes
and computing summary performance metrics at the end.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from hft.core.types import Tick
from hft.data.feed import MarketDataFeed
from hft.engine import TradingEngine
from hft.execution.paper import PaperBroker
from hft.portfolio.portfolio import Portfolio
from hft.risk.manager import RiskLimits, RiskManager
from hft.strategy.base import Strategy


@dataclass
class BacktestResult:
    starting_equity: float
    ending_equity: float
    equity_curve: list[tuple[float, float]] = field(default_factory=list)  # (ts, equity)
    n_ticks: int = 0
    n_fills: int = 0
    n_rejected: int = 0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_commission: float = 0.0

    @property
    def total_return(self) -> float:
        if self.starting_equity == 0:
            return 0.0
        return (self.ending_equity - self.starting_equity) / self.starting_equity

    @property
    def max_drawdown(self) -> float:
        """Largest peak-to-trough decline of the equity curve, as a fraction."""
        peak = -math.inf
        max_dd = 0.0
        for _, equity in self.equity_curve:
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak)
        return max_dd

    def sharpe(self, periods_per_year: float = 252 * 6.5 * 3600) -> float:
        """Annualised Sharpe of per-tick equity returns (rf = 0).

        ``periods_per_year`` defaults to roughly the number of 1-second ticks in
        a year of US equity trading hours; override it to match your bar size.
        """
        curve = [e for _, e in self.equity_curve]
        if len(curve) < 3:
            return 0.0
        returns = [
            (curve[i] - curve[i - 1]) / curve[i - 1]
            for i in range(1, len(curve))
            if curve[i - 1] != 0
        ]
        if not returns:
            return 0.0
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / len(returns)
        std = math.sqrt(var)
        if std == 0:
            return 0.0
        return (mean / std) * math.sqrt(periods_per_year)

    def summary(self) -> str:
        lines = [
            "Backtest summary",
            "================",
            f"  Ticks processed : {self.n_ticks}",
            f"  Fills           : {self.n_fills}",
            f"  Rejected orders : {self.n_rejected}",
            f"  Starting equity : {self.starting_equity:,.2f}",
            f"  Ending equity   : {self.ending_equity:,.2f}",
            f"  Total return    : {self.total_return * 100:.2f}%",
            f"  Realized PnL    : {self.realized_pnl:,.2f}",
            f"  Unrealized PnL  : {self.unrealized_pnl:,.2f}",
            f"  Commission paid : {self.total_commission:,.2f}",
            f"  Max drawdown    : {self.max_drawdown * 100:.2f}%",
            f"  Sharpe (annual) : {self.sharpe():.2f}",
        ]
        return "\n".join(lines)


class Backtester:
    """Convenience wrapper that assembles a paper-trading engine and scores a run."""

    def __init__(
        self,
        strategy: Strategy,
        starting_cash: float = 100_000.0,
        risk_limits: RiskLimits | None = None,
        commission_rate: float = 0.0005,
        slippage_bps: float = 1.0,
    ) -> None:
        self.strategy = strategy
        self.portfolio = Portfolio(starting_cash=starting_cash)
        self.broker = PaperBroker(commission_rate=commission_rate, slippage_bps=slippage_bps)
        self.risk = RiskManager(risk_limits or RiskLimits(), self.portfolio)
        self.engine = TradingEngine(strategy, self.broker, self.portfolio, self.risk)

    def run(self, feed: MarketDataFeed | Iterable[Tick]) -> BacktestResult:
        starting_equity = self.portfolio.equity
        result = BacktestResult(
            starting_equity=starting_equity,
            ending_equity=starting_equity,
        )

        self.strategy.on_start(self.engine.ctx)
        for tick in feed:
            self.engine.process_tick(tick)
            result.n_ticks += 1
            result.equity_curve.append((tick.timestamp, self.portfolio.equity))
        self.strategy.on_stop(self.engine.ctx)

        result.ending_equity = self.portfolio.equity
        result.n_fills = len(self.engine.fills)
        result.n_rejected = self.engine.rejected_orders
        result.realized_pnl = self.portfolio.realized_pnl
        result.unrealized_pnl = self.portfolio.unrealized_pnl
        result.total_commission = sum(f.commission for f in self.engine.fills)
        return result
