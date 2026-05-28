#!/usr/bin/env python3
"""Run a backtest from the command line.

Examples
--------
    # Momentum strategy on a synthetic random walk
    python scripts/run_backtest.py --strategy momentum --ticks 5000

    # Market maker on a recorded CSV feed
    python scripts/run_backtest.py --strategy market_making --csv data/sample_ticks.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running straight from a source checkout without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hft.backtest.engine import Backtester  # noqa: E402
from hft.data.simulated import CsvFeed, SimulatedFeed  # noqa: E402
from hft.risk.manager import RiskLimits  # noqa: E402
from hft.strategy.market_making import MarketMakingStrategy  # noqa: E402
from hft.strategy.momentum import MomentumStrategy  # noqa: E402


def build_strategy(name: str, symbol: str):
    if name == "momentum":
        return MomentumStrategy(symbol=symbol, fast_period=10, slow_period=30)
    if name == "market_making":
        return MarketMakingStrategy(symbol=symbol, quote_size=10, spread_bps=10)
    raise SystemExit(f"Unknown strategy: {name!r} (choose: momentum, market_making)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an HFT-stack backtest.")
    parser.add_argument(
        "--strategy", default="momentum", choices=["momentum", "market_making"]
    )
    parser.add_argument("--symbol", default="DEMO")
    parser.add_argument("--ticks", type=int, default=2000, help="synthetic tick count")
    parser.add_argument("--seed", type=int, default=42, help="synthetic feed seed")
    parser.add_argument("--volatility", type=float, default=0.0008)
    parser.add_argument("--cash", type=float, default=100_000.0)
    parser.add_argument("--csv", type=str, default=None, help="replay this CSV instead")
    parser.add_argument("--max-position", type=float, default=500.0)
    args = parser.parse_args(argv)

    strategy = build_strategy(args.strategy, args.symbol)
    feed = (
        CsvFeed(args.csv)
        if args.csv
        else SimulatedFeed(
            symbol=args.symbol,
            n_ticks=args.ticks,
            volatility=args.volatility,
            seed=args.seed,
        )
    )

    bt = Backtester(
        strategy=strategy,
        starting_cash=args.cash,
        risk_limits=RiskLimits(max_position=args.max_position),
    )
    result = bt.run(feed)
    print(f"Strategy: {strategy.name}\n")
    print(result.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
