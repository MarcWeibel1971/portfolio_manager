"""Tests für den HTML-Report-Generator."""
from hft.backtest.engine import Backtester
from hft.data.simulated import SimulatedFeed
from hft.report.html import render_report, write_report
from hft.strategy.momentum import MomentumStrategy


def _run():
    strat = MomentumStrategy(symbol="X", fast_period=5, slow_period=15, target_position=20)
    bt = Backtester(strategy=strat)
    result = bt.run(SimulatedFeed(symbol="X", n_ticks=400, volatility=0.002, seed=5))
    return result, bt


def test_render_produces_valid_html():
    result, bt = _run()
    html = render_report(result, strategy_name="Momentum", symbol="X", fills=bt.engine.fills)
    assert html.startswith("<!doctype html>")
    assert "</html>" in html
    assert "<svg" in html  # Kapitalkurve vorhanden
    assert "Backtest-Report" in html
    assert "Gesamtrendite" in html


def test_html_escapes_symbol():
    result, _ = _run()
    html = render_report(result, strategy_name="S", symbol="<script>X</script>")
    assert "<script>X</script>" not in html
    assert "&lt;script&gt;" in html


def test_write_report_to_file(tmp_path):
    result, bt = _run()
    out = tmp_path / "report.html"
    path = write_report(result, str(out), strategy_name="Momentum",
                        symbol="X", fills=bt.engine.fills)
    assert path == str(out)
    text = out.read_text(encoding="utf-8")
    assert "<svg" in text
    assert str(result.n_fills) in text


def test_handles_empty_and_flat_curves(tmp_path):
    # Sehr kurze Kurve -> SVG-Fallback statt Polyline, darf nicht abstürzen.
    from hft.backtest.engine import BacktestResult

    flat = BacktestResult(starting_equity=100.0, ending_equity=100.0)
    flat.equity_curve = [(0.0, 100.0)]  # nur ein Punkt
    html = render_report(flat, strategy_name="Leer")
    assert "Zu wenige Datenpunkte" in html
    assert "Keine Ausführungen" in html
