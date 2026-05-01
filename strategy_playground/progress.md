## Copper/Silver Ratio -> Oil Strategy Progress

Last updated: 2026-05-01

### Research Goal

Use the copper-to-silver ratio (`CU9999.XSGE / AG9999.XSGE`) as an inter-market predictor for crude oil (`SC9999.XINE`) on local `adjusted_main_contract` minute bars.

The current research workflow backtests user-authored `Signal` classes through the Flask API endpoint:

```text
POST /api/backtests/run-user-signal
```

`strategy_playground/research_cu_ag_sc.py` now sends HTTP POST requests to an existing Flask server, defaulting to `http://localhost:5000`. This lets iterative research reuse the server process and its in-memory adjusted-main-contract CSV cache.

Example:

```bash
uv run python strategy_playground/research_cu_ag_sc.py --base-url http://localhost:5000 --only lagged_ratio_three_bar_confirm
```

### Backtest Setup

- Data source: `adjusted_main_contract`
- Symbols: `CU9999.XSGE`, `AG9999.XSGE`, `SC9999.XINE`
- Date range: `20240101` to `20260422`
- Initial cash: `1,000,000`
- Position size: `1` SC contract
- Execution timing: `next_bar` unless explicitly comparing fill assumptions
- Costs/slippage: current API run used `0` commission and no slippage

### Iteration Results

| Strategy | Execution | Final Equity | Return | Max DD | Daily Sharpe | Trades | Decision |
|---|---|---:|---:|---:|---:|---:|---|
| Buy-and-hold SC baseline | `next_bar` | 1,146,680 | 14.67% | -16.66% | 0.423 | 1 | Baseline |
| Raw CU/AG ratio momentum | `next_bar` | 964,900 | -3.51% | -22.11% | -0.077 | 1,444 | Discard |
| CU/AG ratio + SC trend filter | `next_bar` | 1,057,640 | 5.76% | -16.44% | 0.334 | 3,658 | Discard |
| CU/AG ratio with 3-bar confirmation | `next_bar` | 1,063,000 | 6.30% | -13.90% | 0.291 | 1,096 | Revise |
| Slow CU/AG ratio regime | `next_bar` | 918,150 | -8.18% | -21.03% | -0.244 | 259 | Discard |
| Lagged CU/AG ratio with 3-bar confirmation | `next_bar` | 1,078,260 | 7.83% | -14.51% | 0.348 | 1,096 | Revise |

### Timing Validation

The 3-bar confirmed ratio signal was rerun with both fill modes:

| Variant | Execution | Final Equity | Return | Max DD | Daily Sharpe | Trades |
|---|---|---:|---:|---:|---:|---:|
| 3-bar confirmed ratio | `current_bar` | 1,048,010 | 4.80% | -13.87% | 0.236 | 1,096 |
| 3-bar confirmed ratio | `next_bar` | 1,063,000 | 6.30% | -13.90% | 0.291 | 1,096 |
| Lagged ratio + 3-bar confirmation | `next_bar` | 1,078,260 | 7.83% | -14.51% | 0.348 | 1,096 |

`next_bar` did not hurt this strategy in the tested window. Lagging the ratio by one SC bar made the predictor timing more conservative and improved return and Sharpe, at the cost of a slightly deeper drawdown.

### Current Read

The lagged 3-bar confirmed version is the best candidate so far, but it is not production-ready:

- It still underperforms buy-and-hold SC on total return.
- It reduces drawdown versus buy-and-hold, but only modestly.
- Turnover remains very high at roughly `562x` notional over the test window.
- Results still assume zero commission and no slippage.

### Next Iteration

Focus on churn reduction before optimizing return:

- Add a minimum holding period or wider exit band.
- Re-run through the Flask API with `execution_timing="next_bar"`.
- Add realistic transaction costs/slippage once the trade count is reasonable.
