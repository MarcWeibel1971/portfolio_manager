# HFT-Trading-Bot-Stack

Ein ereignisgesteuerter algorithmischer / Hochfrequenzhandels-Stack (HFT) in
Python. Er ist um eine einzige Pipeline herum gebaut –
`Tick → Strategie → Risiko → Ausführung → Portfolio` – sodass **derselbe
Strategiecode unverändert in Backtest, Paper-Trading und (echtem) Live-Handel
läuft**.

> ⚠️ **Standardmäßig sicher.** Die voreingestellte Ausführung ist ein
> *Paper-Broker*, der Fills lokal simuliert – keine Börse, keine Zugangsdaten,
> kein Risiko. Ein **Live-Adapter** ist enthalten (`hft.execution.live`), aber
> mehrfach verriegelt: Er sendet nur echte Orders, wenn `confirm_live=True`
> gesetzt ist, und verbindet sich nur mit dem Mainnet, wenn zusätzlich
> `allow_mainnet=True` gesetzt wird. Handel birgt reale finanzielle Risiken;
> nichts hiervon ist eine Anlageberatung.

## Architektur

```
            ┌───────────────┐   Ticks    ┌───────────────┐
  Feed ───► │ TradingEngine │ ─────────► │   Strategie   │
            │ (Event-Loop)  │ ◄──Order-  │ (Entscheidung)│
            └──────┬────────┘   absicht  └───────────────┘
                   │  Order (risikogeprüft)
                   ▼
            ┌───────────────┐   Fills    ┌───────────────┐
            │    Broker     │ ─────────► │   Portfolio   │
            │ Paper / Live  │            │ (Pos. & G/V)  │
            └───────────────┘            └───────────────┘
                   ▲ Vorhandelsprüfung
            ┌──────┴────────┐
            │  RiskManager  │
            └───────────────┘
```

| Schicht | Modul | Aufgabe |
|---------|-------|---------|
| Kerntypen | `hft.core.types` | `Tick`, `Order`, `Fill`, `Side`, Enums |
| Datenfeeds | `hft.data` | `SimulatedFeed` (Random Walk), `CsvFeed` (Wiedergabe) |
| Strategien | `hft.strategy` | `Strategy`-Basis + `MomentumStrategy`, `MarketMakingStrategy` |
| Risiko | `hft.risk` | `RiskManager` + `RiskLimits` (Vorhandelsprüfungen) |
| Ausführung | `hft.execution` | `Broker`-Interface, `PaperBroker`, `LiveBroker` (ccxt) |
| Portfolio | `hft.portfolio` | Positions-, Kassenbestands- und G/V-Buchhaltung |
| Engine | `hft.engine` | Der Event-Loop, der alles verbindet |
| Backtest | `hft.backtest` | `Backtester` + Kennzahlen (Rendite, Sharpe, Max-Drawdown) |

## Installation

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # editierbare Installation inkl. Test-Abhängigkeiten
pip install -e ".[live]"     # zusätzlich: ccxt für echte Börsenanbindung
```

Die einzige Laufzeitabhängigkeit ist `PyYAML`. Python 3.10+ wird benötigt.

## Schnellstart

Backtest über die Kommandozeile:

```bash
# Momentum (EMA-Crossover) auf einem reproduzierbaren synthetischen Random Walk
python scripts/run_backtest.py --strategy momentum --ticks 5000 --volatility 0.002

# Market Maker auf derselben Engine
python scripts/run_backtest.py --strategy market_making --ticks 5000

# Eine aufgezeichnete CSV abspielen (Spalten: timestamp,symbol,bid,ask[,last,volume])
python scripts/run_backtest.py --strategy momentum --csv data/sample_ticks.csv
```

Oder aus Python:

```python
from hft import Backtester, MomentumStrategy, RiskLimits, SimulatedFeed

bt = Backtester(
    strategy=MomentumStrategy(symbol="BTCUSD", fast_period=10, slow_period=30),
    starting_cash=100_000,
    risk_limits=RiskLimits(max_position=500, max_drawdown=20_000),
)
result = bt.run(SimulatedFeed(symbol="BTCUSD", n_ticks=5000, volatility=0.002))
print(result.summary())
```

## Eine Strategie schreiben

`Strategy` ableiten und `on_tick` implementieren. Orders werden über den
`StrategyContext` abgegeben – niemals direkt über den Broker, damit die
Risikoprüfungen immer greifen:

```python
from hft.core.types import Side, Tick
from hft.strategy.base import Strategy, StrategyContext

class BuyTheDip(Strategy):
    def __init__(self, symbol: str):
        super().__init__()
        self.symbol = symbol
        self.high = 0.0

    def on_tick(self, tick: Tick, ctx: StrategyContext) -> None:
        if tick.symbol != self.symbol:
            return
        self.high = max(self.high, tick.last)
        if tick.last < self.high * 0.99 and ctx.position(self.symbol) == 0:
            ctx.market_order(self.symbol, Side.BUY, 10)
```

Hooks: `on_start`, `on_tick`, `on_fill`, `on_stop`.

## Risikomanagement

Jede Order wird vor dem Broker durch `RiskManager.check` validiert. Limits sind
optional (`None` deaktiviert eine Prüfung):

```python
RiskLimits(
    max_order_quantity=200,       # Einheiten pro Order
    max_position=500,             # absolute Einheiten je Symbol
    max_gross_exposure=250_000,   # Summe der |Positionsnominale|
    max_notional_per_order=100_000,
    max_drawdown=20_000,          # gesamter Handel stoppt nach diesem Kapitalverlust
)
```

Das Drawdown-Limit ist ein harter Schutzschalter: Einmal ausgelöst, stoppt es
die Strategie für den Rest der Sitzung.

## Backtest-Kennzahlen

`BacktestResult` liefert Gesamtrendite, realisierten/unrealisierten G/V,
gezahlte Gebühren, Max-Drawdown und eine annualisierte Sharpe-Ratio, dazu die
vollständige Kapitalkurve. Ergebnisse sind für einen gegebenen
`SimulatedFeed`-Seed deterministisch.

## Live-Trading

Der Live-Adapter (`hft.execution.live`) implementiert dasselbe `Broker`-
Interface wie der Paper-Broker, sodass **kein** Strategie- oder Risikocode
geändert werden muss. Er nutzt [`ccxt`](https://github.com/ccxt/ccxt) und
unterstützt damit viele Krypto-Börsen (Binance, Kraken, Coinbase …).

```python
from hft import LiveBroker, MomentumStrategy, Portfolio, RiskLimits, RiskManager
from hft.engine import TradingEngine
from hft.execution.live import CcxtExchangeClient

# 1. Börsen-Client – standardmäßig Testnet.
client = CcxtExchangeClient(
    "binance",
    api_key="…",            # besser: aus Umgebungsvariablen lesen
    api_secret="…",
    testnet=True,           # für echtes Geld: testnet=False UND allow_mainnet=True
)

# 2. Live-Broker – verlangt eine bewusste Bestätigung.
broker = LiveBroker(client, confirm_live=True)

# 3. Restlicher Stack identisch zum Backtest.
portfolio = Portfolio(starting_cash=10_000)
risk = RiskManager(RiskLimits(max_position=1, max_notional_per_order=100), portfolio)
engine = TradingEngine(MomentumStrategy("BTC/USDT"), broker, portfolio, risk)
```

**Sicherheitsmechanismen:**

1. `LiveBroker` startet nur mit `confirm_live=True`.
2. `CcxtExchangeClient` verbindet sich nur mit dem Testnet, außer
   `allow_mainnet=True` ist gesetzt.
3. Börsenfehler beim Senden/Stornieren töten die Engine nicht – die Order wird
   abgelehnt bzw. die Stornierung schlägt sauber fehl.

Fills werden bei der Auftragserteilung und danach bei jedem Tick (Polling
offener Orders über `fetch_order`) inkrementell abgeglichen, sodass auch
Teilausführungen korrekt verbucht werden.

> **Erst im Testnet testen, mit kleinstem Volumen starten und `RiskLimits` eng
> halten.** Echte Orders bedeuten echtes Geld.

## Tests

```bash
pytest            # Tests für Typen, Portfolio, Risiko, Broker, Live-Adapter, Backtest
ruff check src    # Linting
```

## Projektstruktur

```
src/hft/
  core/        Domänentypen (Tick, Order, Fill, Side)
  data/        Marktdatenfeeds (simuliert, CSV)
  strategy/    Strategie-Basisklasse + Beispiele
  risk/        Vorhandels-Risikomanager
  execution/   Broker-Interface + Paper- und Live-Broker
  portfolio/   Positions- und G/V-Verfolgung
  backtest/    Backtest-Harness + Kennzahlen
  engine.py    der Event-Loop
scripts/       CLI-Einstiegspunkte
tests/         pytest-Suite
config/        Beispielkonfiguration
```

## Lizenz

MIT
