"""Eigenständiger HTML-Report für Backtest-Ergebnisse.

Erzeugt eine einzelne, in sich geschlossene HTML-Datei: Kennzahlen, eine als
Inline-SVG gezeichnete Kapitalkurve und eine Trade-Tabelle. Es werden keine
externen Skripte, CDNs oder zusätzliche Python-Abhängigkeiten benötigt — die
Datei lässt sich offline im Browser öffnen.
"""
from __future__ import annotations

import html
from collections.abc import Sequence
from datetime import datetime, timezone

from hft.backtest.engine import BacktestResult
from hft.core.types import Fill

# Layout der Kapitalkurve (SVG-Koordinaten).
_SVG_W = 860
_SVG_H = 340
_PAD = 48
_MAX_POINTS = 600  # Downsampling-Grenze für große Kurven


def _downsample(curve: Sequence[tuple[float, float]], limit: int) -> list[tuple[float, float]]:
    """Reduziert die Kurve auf höchstens ``limit`` Punkte (gleichmäßiges Stride)."""
    n = len(curve)
    if n <= limit:
        return list(curve)
    step = n / limit
    sampled = [curve[int(i * step)] for i in range(limit)]
    if sampled[-1] != curve[-1]:
        sampled.append(curve[-1])  # Endpunkt immer behalten
    return sampled


def _equity_svg(result: BacktestResult) -> str:
    """Zeichnet die Kapitalkurve als Inline-SVG-Polyline mit Startkapital-Linie."""
    curve = _downsample(result.equity_curve, _MAX_POINTS)
    if len(curve) < 2:
        return '<p class="muted">Zu wenige Datenpunkte für eine Kurve.</p>'

    equities = [e for _, e in curve]
    lo, hi = min(equities), max(equities)
    # Etwas Headroom und Schutz gegen flache Kurven (lo == hi).
    if hi - lo < 1e-9:
        hi = lo + max(1.0, abs(lo) * 0.001)
    span = hi - lo
    plot_w = _SVG_W - 2 * _PAD
    plot_h = _SVG_H - 2 * _PAD
    n = len(curve)

    def x(i: int) -> float:
        return _PAD + (i / (n - 1)) * plot_w

    def y(value: float) -> float:
        return _PAD + (1.0 - (value - lo) / span) * plot_h

    points = " ".join(f"{x(i):.1f},{y(e):.1f}" for i, (_, e) in enumerate(curve))

    start = result.starting_equity
    baseline = ""
    if lo <= start <= hi:
        by = y(start)
        baseline = (
            f'<line x1="{_PAD}" y1="{by:.1f}" x2="{_SVG_W - _PAD}" y2="{by:.1f}" '
            f'class="baseline" />'
            f'<text x="{_SVG_W - _PAD}" y="{by - 6:.1f}" text-anchor="end" '
            f'class="axis">Start {start:,.0f}</text>'
        )

    # Farbe nach Gesamtergebnis.
    line_class = "up" if result.ending_equity >= start else "down"

    return f"""<svg viewBox="0 0 {_SVG_W} {_SVG_H}" class="chart" role="img"
     aria-label="Kapitalkurve">
  <rect x="{_PAD}" y="{_PAD}" width="{plot_w}" height="{plot_h}" class="plot" />
  {baseline}
  <polyline points="{points}" class="curve {line_class}" />
  <text x="{_PAD}" y="{_PAD - 12}" class="axis">{hi:,.0f}</text>
  <text x="{_PAD}" y="{_SVG_H - _PAD + 18}" class="axis">{lo:,.0f}</text>
  <text x="{_PAD}" y="{_SVG_H - 10}" class="axis">Beginn</text>
  <text x="{_SVG_W - _PAD}" y="{_SVG_H - 10}" text-anchor="end" class="axis">Ende</text>
</svg>"""


def _metric_cards(result: BacktestResult) -> str:
    ret = result.total_return * 100
    ret_class = "up" if ret >= 0 else "down"
    pnl_class = "up" if result.ending_equity >= result.starting_equity else "down"
    cards = [
        ("Gesamtrendite", f"{ret:+.2f}%", ret_class),
        ("Endkapital", f"{result.ending_equity:,.2f}", pnl_class),
        ("Realisierter G/V", f"{result.realized_pnl:,.2f}", ""),
        ("Unrealisierter G/V", f"{result.unrealized_pnl:,.2f}", ""),
        ("Max. Drawdown", f"{result.max_drawdown * 100:.2f}%", "down" if result.max_drawdown else ""),
        ("Sharpe (annualis.)", f"{result.sharpe():.2f}", ""),
        ("Ausführungen", f"{result.n_fills}", ""),
        ("Gezahlte Gebühren", f"{result.total_commission:,.2f}", ""),
    ]
    items = "\n".join(
        f'<div class="card"><div class="label">{html.escape(label)}</div>'
        f'<div class="value {cls}">{html.escape(value)}</div></div>'
        for label, value, cls in cards
    )
    return f'<div class="cards">{items}</div>'


def _trades_table(fills: Sequence[Fill], limit: int = 50) -> str:
    if not fills:
        return '<p class="muted">Keine Ausführungen in diesem Lauf.</p>'
    shown = fills[-limit:]
    rows = []
    for f in shown:
        side_cls = "up" if f.side.value == "buy" else "down"
        rows.append(
            f"<tr><td>{html.escape(f.symbol)}</td>"
            f'<td class="{side_cls}">{f.side.value.upper()}</td>'
            f"<td>{f.quantity:g}</td><td>{f.price:,.4f}</td>"
            f"<td>{f.commission:,.4f}</td></tr>"
        )
    note = "" if len(fills) <= limit else f'<p class="muted">Letzte {limit} von {len(fills)} Trades.</p>'
    return f"""{note}<table class="trades">
  <thead><tr><th>Symbol</th><th>Seite</th><th>Menge</th><th>Preis</th><th>Gebühr</th></tr></thead>
  <tbody>{''.join(rows)}</tbody>
</table>"""


def render_report(
    result: BacktestResult,
    *,
    strategy_name: str,
    symbol: str = "",
    fills: Sequence[Fill] | None = None,
) -> str:
    """Rendert den vollständigen HTML-Report als String."""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subtitle = html.escape(strategy_name)
    if symbol:
        subtitle += f" · {html.escape(symbol)}"

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Backtest-Report · {subtitle}</title>
<style>
  :root {{ --bg:#0f1419; --panel:#1a2029; --fg:#e6e9ef; --muted:#8b94a3;
           --up:#3fb950; --down:#f85149; --accent:#58a6ff; --grid:#2a3340; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
          font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }}
  header {{ padding:28px 32px; border-bottom:1px solid var(--grid); }}
  h1 {{ margin:0 0 4px; font-size:22px; }}
  .sub {{ color:var(--muted); }}
  main {{ max-width:920px; margin:0 auto; padding:28px 32px 60px; }}
  section {{ margin-bottom:36px; }}
  h2 {{ font-size:15px; text-transform:uppercase; letter-spacing:.06em;
        color:var(--muted); margin:0 0 14px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
            gap:14px; }}
  .card {{ background:var(--panel); border:1px solid var(--grid); border-radius:10px;
           padding:16px 18px; }}
  .card .label {{ color:var(--muted); font-size:13px; }}
  .card .value {{ font-size:24px; font-weight:600; margin-top:6px;
                  font-variant-numeric:tabular-nums; }}
  .up {{ color:var(--up); }}
  .down {{ color:var(--down); }}
  .muted {{ color:var(--muted); }}
  .chart {{ width:100%; height:auto; background:var(--panel);
            border:1px solid var(--grid); border-radius:10px; }}
  .plot {{ fill:none; stroke:var(--grid); }}
  .curve {{ fill:none; stroke:var(--accent); stroke-width:2;
            stroke-linejoin:round; stroke-linecap:round; }}
  .curve.up {{ stroke:var(--up); }}
  .curve.down {{ stroke:var(--down); }}
  .baseline {{ stroke:var(--muted); stroke-dasharray:4 4; stroke-width:1; }}
  .axis {{ fill:var(--muted); font-size:11px; }}
  table.trades {{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }}
  table.trades th, table.trades td {{ text-align:right; padding:8px 12px;
            border-bottom:1px solid var(--grid); }}
  table.trades th:first-child, table.trades td:first-child {{ text-align:left; }}
  table.trades th {{ color:var(--muted); font-weight:500; font-size:13px; }}
  footer {{ color:var(--muted); font-size:12px; padding:0 32px 32px;
            max-width:920px; margin:0 auto; }}
</style>
</head>
<body>
<header>
  <h1>Backtest-Report</h1>
  <div class="sub">{subtitle} · {result.n_ticks:,} Ticks · erstellt {generated}</div>
</header>
<main>
  <section>
    <h2>Kennzahlen</h2>
    {_metric_cards(result)}
  </section>
  <section>
    <h2>Kapitalkurve</h2>
    {_equity_svg(result)}
  </section>
  <section>
    <h2>Trades</h2>
    {_trades_table(fills or [])}
  </section>
</main>
<footer>
  Simulierter Backtest — keine Anlageberatung. Vergangene Ergebnisse sind kein
  Indikator für zukünftige Wertentwicklung.
</footer>
</body>
</html>"""


def write_report(
    result: BacktestResult,
    path: str,
    *,
    strategy_name: str,
    symbol: str = "",
    fills: Sequence[Fill] | None = None,
) -> str:
    """Schreibt den Report nach ``path`` und gibt den Pfad zurück."""
    content = render_report(
        result, strategy_name=strategy_name, symbol=symbol, fills=fills
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path
