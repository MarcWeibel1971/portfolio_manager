#!/usr/bin/env python3
"""Historische Marktdaten herunterladen und im CSV-Format des Stacks speichern.

Nutzt `ccxt`, um OHLCV-Kerzen einer Krypto-Börse zu laden, und wandelt den
Schlusskurs (close) in synthetische Bid/Ask-Ticks mit konfigurierbarem Spread um
(ccxt liefert keine Bid/Ask-Historie). Die Ausgabe passt direkt zu CsvFeed bzw.
``scripts/run_backtest.py --csv``.

Beispiel
--------
    pip install ".[live]"
    python scripts/fetch_data.py --exchange binance --symbol BTC/USDT \
        --timeframe 1m --limit 2000 --out data/btc_1m.csv

Hinweis: Kein API-Key nötig — öffentliche Marktdaten sind frei abrufbar.
"""
from __future__ import annotations

import argparse
import csv
import sys


def fetch_ohlcv(exchange_id: str, symbol: str, timeframe: str, limit: int, since: int | None):
    try:
        import ccxt  # type: ignore
    except ImportError:
        sys.exit("ccxt fehlt. Installieren mit: pip install ccxt   (oder: pip install \".[live]\")")

    try:
        exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
    except AttributeError:
        sys.exit(f"Unbekannte Börse: {exchange_id!r}")

    if not exchange.has.get("fetchOHLCV"):
        sys.exit(f"{exchange_id} unterstützt kein fetchOHLCV.")

    return exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)


def write_csv(rows, symbol: str, spread_bps: float, out_path: str) -> int:
    half_spread = spread_bps / 2.0 / 10_000.0
    written = 0
    with open(out_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "symbol", "bid", "ask", "last", "volume"])
        for ts_ms, _open, _high, _low, close, volume in rows:
            ts = ts_ms / 1000.0  # ccxt liefert Millisekunden
            bid = close * (1.0 - half_spread)
            ask = close * (1.0 + half_spread)
            writer.writerow([ts, symbol, round(bid, 8), round(ask, 8), close, volume])
            written += 1
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Historische OHLCV-Daten als Tick-CSV speichern.")
    parser.add_argument("--exchange", default="binance", help="ccxt-Börsen-ID (binance, kraken, …)")
    parser.add_argument("--symbol", default="BTC/USDT", help="Handelspaar")
    parser.add_argument("--timeframe", default="1m", help="Kerzen-Intervall (1m,5m,1h,1d …)")
    parser.add_argument("--limit", type=int, default=1000, help="Anzahl Kerzen")
    parser.add_argument("--since", type=int, default=None, help="Startzeit in ms (Epoch)")
    parser.add_argument("--spread-bps", type=float, default=2.0, help="synthetischer Spread in bps")
    parser.add_argument("--out", default="data/historical.csv", help="Ziel-CSV")
    args = parser.parse_args(argv)

    rows = fetch_ohlcv(args.exchange, args.symbol, args.timeframe, args.limit, args.since)
    n = write_csv(rows, args.symbol, args.spread_bps, args.out)
    print(f"{n} Kerzen von {args.exchange} ({args.symbol}, {args.timeframe}) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
