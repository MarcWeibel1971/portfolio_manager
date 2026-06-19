#!/usr/bin/env python3
"""Backtest über die Kommandozeile ausführen.

Beispiele
---------
    # Momentum-Strategie auf einem synthetischen Random Walk
    python scripts/run_backtest.py --strategy momentum --ticks 5000

    # Market Maker auf einem aufgezeichneten CSV-Feed
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
    raise SystemExit(f"Unbekannte Strategie: {name!r} (möglich: momentum, market_making)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest für den HFT-Stack ausführen.")
    parser.add_argument(
        "--strategy", default="momentum", choices=["momentum", "market_making"],
        help="zu testende Strategie",
    )
    parser.add_argument("--symbol", default="DEMO", help="Handelssymbol")
    parser.add_argument("--ticks", type=int, default=2000, help="Anzahl synthetischer Ticks")
    parser.add_argument("--seed", type=int, default=42, help="Seed des synthetischen Feeds")
    parser.add_argument("--volatility", type=float, default=0.0008, help="Volatilität pro Tick")
    parser.add_argument("--cash", type=float, default=100_000.0, help="Startkapital")
    parser.add_argument("--csv", type=str, default=None, help="stattdessen diese CSV abspielen")
    parser.add_argument("--max-position", type=float, default=500.0, help="max. Positionsgröße")
    parser.add_argument(
        "--report", type=str, default=None,
        help="HTML-Report in diese Datei schreiben (z. B. report.html)",
    )
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
    print(f"Strategie: {strategy.name}\n")
    print(result.summary())

    if args.report:
        from hft.report.html import write_report

        write_report(
            result,
            args.report,
            strategy_name=strategy.name,
            symbol=args.symbol,
            fills=bt.engine.fills,
        )
        print(f"\nHTML-Report geschrieben: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
