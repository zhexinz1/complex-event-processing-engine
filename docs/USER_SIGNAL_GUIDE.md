# User-Coded Signal Rules

This v1 feature lets internal researchers save Python `Signal` classes, validate them, backtest them, and enable them for live monitoring.

## Contract

```python
class Signal:
    name = "沪金RSI超卖"
    symbols = ["AU9999.XSGE"]
    bar_freq = "1m"

    def __init__(self, ctx):
        self.ctx = ctx

    def on_bar(self, bar):
        if self.ctx.rsi is not None and self.ctx.rsi < 30:
            return {"side": "BUY", "reason": "rsi_oversold", "price": bar.close}
        return None
```

`ctx` is `LocalContext`, so existing lazy indicators such as `ctx.rsi` and latest bar fields such as `ctx.close` are available. `on_bar` must return either `None` or a dictionary copied into `SignalEvent.payload`. `side` is optional; when present it must be `BUY` or `SELL`.

## Runtime

- Code is executed in-process after AST contract checks.
- Imports and several dynamic Python constructs are blocked.
- Double-underscore attribute access such as `().__class__` is blocked before execution.
- The loader exposes only a small builtin allowlist and `OrderSide`.
- Runtime errors are captured as diagnostics and do not crash the event bus.

## APIs

- `GET /api/signals`
- `POST /api/signals`
- `PUT /api/signals/<id>`
- `POST /api/signals/<id>/status`
- `POST /api/signals/validate`
- `POST /api/backtests/run-user-signal`
- `GET /api/signals/live/recent`
- `GET /api/signals/live/stream`

Live monitoring subscribes to JSON-encoded `BarEvent` payloads on `CEP_REDIS_CHANNEL` (`cep_events` by default). Tick-to-bar aggregation is expected to happen upstream. Payloads must include `symbol`, `freq`, OHLCV fields, `turnover`, and ISO-8601 `bar_time`; `event_id` and `timestamp` are optional.

`POST /api/backtests/run-user-signal` also accepts:

- `write_trade_log: false` to skip writing `backtest/logs/*.json`
- `execution_timing: "next_bar"` to fill on the next bar open and avoid same-bar look-ahead bias
- `execution_timing: "current_bar"` to reproduce the legacy same-bar-close behavior for comparison

## Local Commodity CSV Backtests

When backtesting against local `adjusted_main_contract/*.csv` minute history, use the continuous symbol that matches the CSV filename, for example:

- `AU9999.XSGE`
- `AG9999.XSGE`

The save API can persist the signal first, then the backtest API can reference the saved `signal_id`.

Create a gold signal:

```bash
curl -X POST http://localhost:5000/api/signals \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "沪金RSI超卖",
    "symbols": ["AU9999.XSGE"],
    "bar_freq": "1m",
    "created_by": "research",
    "source_code": "class Signal:\n    name = \"沪金RSI超卖\"\n    symbols = [\"AU9999.XSGE\"]\n    bar_freq = \"1m\"\n\n    def __init__(self, ctx):\n        self.ctx = ctx\n\n    def on_bar(self, bar):\n        if self.ctx.rsi is not None and self.ctx.rsi < 30:\n            return {\"side\": \"BUY\", \"reason\": \"rsi_oversold\", \"price\": bar.close}\n        return None\n"
  }'
```

Backtest the saved gold signal on local `AU9999.XSGE.csv`:

```bash
curl -X POST http://localhost:5000/api/backtests/run-user-signal \
  -H 'Content-Type: application/json' \
  -d '{
    "signal_id": 1,
    "data_source": "adjusted_main_contract",
    "symbols": ["AU9999.XSGE"],
    "start_date": "20250601",
    "end_date": "20250630"
  }'
```

Create a silver signal and backtest it on local `AG9999.XSGE.csv`:

```bash
curl -X POST http://localhost:5000/api/signals \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "沪银双均线翻转",
    "symbols": ["AG9999.XSGE"],
    "bar_freq": "1m",
    "created_by": "research",
    "source_code": "class Signal:\n    name = \"沪银双均线翻转\"\n    symbols = [\"AG9999.XSGE\"]\n    bar_freq = \"1m\"\n\n    def __init__(self, ctx):\n        self.ctx = ctx\n\n    def on_bar(self, bar):\n        if self.ctx.ma5 is None or self.ctx.ma10 is None:\n            return None\n        if self.ctx.ma5 > self.ctx.ma10:\n            return {\"side\": \"BUY\", \"reason\": \"ma5_above_ma10\", \"price\": bar.close}\n        if self.ctx.ma5 < self.ctx.ma10:\n            return {\"side\": \"SELL\", \"reason\": \"ma5_below_ma10\", \"price\": bar.close}\n        return None\n"
  }'
```

```bash
curl -X POST http://localhost:5000/api/backtests/run-user-signal \
  -H 'Content-Type: application/json' \
  -d '{
    "data_source": "adjusted_main_contract",
    "source_code": "class Signal:\n    name = \"沪银双均线翻转\"\n    symbols = [\"AG9999.XSGE\"]\n    bar_freq = \"1m\"\n\n    def __init__(self, ctx):\n        self.ctx = ctx\n\n    def on_bar(self, bar):\n        if self.ctx.ma5 is None or self.ctx.ma10 is None:\n            return None\n        if self.ctx.ma5 > self.ctx.ma10:\n            return {\"side\": \"BUY\", \"reason\": \"ma5_above_ma10\", \"price\": bar.close}\n        if self.ctx.ma5 < self.ctx.ma10:\n            return {\"side\": \"SELL\", \"reason\": \"ma5_below_ma10\", \"price\": bar.close}\n        return None\n",
    "symbols": ["AG9999.XSGE"],
    "start_date": "20250601",
    "end_date": "20250630"
  }'
```
