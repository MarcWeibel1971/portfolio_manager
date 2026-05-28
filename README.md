# HFT Trading Bot Stack

An event-driven algorithmic / high-frequency trading bot stack in Python. It is
built around a single tick → strategy → risk → execution → portfolio pipeline so
that **the same strategy code runs unchanged in backtest, paper, and (future)
live trading**.

> ⚠️ **Safe by default.** The bundled execution venue is a *paper broker* that
> simulates fills locally. No real exchange is ever contacted and no credentials
> are required. There is intentionally **no live-trading adapter included** —
> wiring one in is an explicit, opt-in step you take yourself (see
> [Going live](#going-live)). Trading carries real financial risk; nothing here
> is financial advice.

## Architecture

```
            ┌──────────────┐   ticks    ┌───────────────┐
  feed ───► │ TradingEngine │ ─────────► │   Strategy    │
            │  (event loop) │ ◄───order  │ (decisions)   │
            └──────┬────────┘   intents  └───────────────┘
                   │  order (risk-checked)
                   ▼
            ┌──────────────┐   fills    ┌───────────────┐
            │   Broker     │ ─────────► │   Portfolio   │
            │ (PaperBroker)│            │ (positions/PnL)│
            └──────────────┘            └───────────────┘
                   ▲ pre-trade checks
            ┌──────┴───────┐
            │ RiskManager  │
            └──────────────┘
```

| Layer | Module | Responsibility |
|-------|--------|----------------|
| Core types | `hft.core.types` | `Tick`, `Order`, `Fill`, `Side`, enums |
| Data feeds | `hft.data` | `SimulatedFeed` (random walk), `CsvFeed` (replay) |
| Strategies | `hft.strategy` | `Strategy` base + `MomentumStrategy`, `MarketMakingStrategy` |
| Risk | `hft.risk` | `RiskManager` + `RiskLimits` pre-trade checks |
| Execution | `hft.execution` | `Broker` interface + `PaperBroker` simulator |
| Portfolio | `hft.portfolio` | Position, cash and P&L bookkeeping |
| Engine | `hft.engine` | The event loop tying it all together |
| Backtest | `hft.backtest` | `Backtester` + metrics (`return`, `Sharpe`, `max drawdown`) |

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # editable install with test deps
```

The only runtime dependency is `PyYAML`. Python 3.10+ is required.

## Quick start

Run a backtest from the CLI:

```bash
# Momentum (EMA crossover) on a reproducible synthetic random walk
python scripts/run_backtest.py --strategy momentum --ticks 5000 --volatility 0.002

# Market maker on the same engine
python scripts/run_backtest.py --strategy market_making --ticks 5000

# Replay a recorded CSV (columns: timestamp,symbol,bid,ask[,last,volume])
python scripts/run_backtest.py --strategy momentum --csv data/sample_ticks.csv
```

Or from Python:

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

## Writing a strategy

Subclass `Strategy` and implement `on_tick`. Submit orders through the
`StrategyContext` — never touch the broker directly, so risk checks always apply:

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

## Risk management

Every order is validated by `RiskManager.check` before it reaches the broker.
Limits are opt-in (`None` disables a check):

```python
RiskLimits(
    max_order_quantity=200,       # units per order
    max_position=500,             # absolute units per symbol
    max_gross_exposure=250_000,   # sum of |position notional|
    max_notional_per_order=100_000,
    max_drawdown=20_000,          # halt all trading after this much equity loss
)
```

The drawdown limit is a hard circuit breaker: once tripped it halts the strategy
for the rest of the session.

## Backtest metrics

`BacktestResult` reports total return, realized/unrealized P&L, commission paid,
max drawdown, and an annualised Sharpe ratio, plus the full equity curve for
plotting. Results are deterministic for a given `SimulatedFeed` seed.

## Configuration

`config/config.example.yaml` documents every tunable knob. Copy it to
`config/config.yaml` (gitignored) for local use. **Never commit API keys** — the
example references them via environment variables.

## Testing

```bash
pytest            # 29 tests covering types, portfolio, risk, broker, backtest
ruff check src    # lint
```

## Going live

Live trading is deliberately **not** included. To add it:

1. Implement the `hft.execution.broker.Broker` interface against your exchange
   (e.g. with `ccxt` for crypto or a brokerage SDK for equities).
2. Translate the venue's fill/ack messages into `Fill` objects and call
   `_emit_fill`.
3. Swap that broker into `TradingEngine` in place of `PaperBroker`.

Because strategies and risk checks are venue-agnostic, no strategy code changes.
**Test extensively on a testnet/paper account first, start with tiny size, and
keep `RiskLimits` tight.**

## Project layout

```
src/hft/
  core/        domain types (Tick, Order, Fill, Side)
  data/        market data feeds (simulated, CSV)
  strategy/    strategy base class + examples
  risk/        pre-trade risk manager
  execution/   broker interface + paper broker
  portfolio/   position & PnL tracking
  backtest/    backtesting harness + metrics
  engine.py    the event loop
scripts/       CLI entry points
tests/         pytest suite
config/        example configuration
```

## License

MIT
