## Copper/Silver Ratio -> Oil Strategy Progress

Last updated: 2026-05-02

### Research Goal

Use the copper-to-silver ratio (`CU9999.XSGE / AG9999.XSGE`) as an inter-market predictor for crude oil (`SC9999.XINE`) on local `adjusted_main_contract` minute bars.

The current research workflow backtests user-authored `Signal` classes through the Flask API endpoint:

```text
POST /api/backtests/run-user-signal
```

`strategy_playground/research_cu_ag_sc.py` now sends HTTP POST requests to an existing Flask server, defaulting to `http://localhost:5000`. This lets iterative research reuse the server process and its in-memory adjusted-main-contract CSV cache.

Example:

```bash
uv run python strategy_playground/research_cu_ag_sc.py --base-url http://localhost:5000 --only ratio_breakout_mid_corr_gate
```

The script intentionally keeps only runnable active experiments to preserve future context window: `buy_hold_sc`, `lagged_ratio_three_bar_confirm`, `lagged_ratio_min_hold`, and `ratio_breakout_mid_corr_gate`. Discarded historical strategy bodies were removed from code; their outcomes remain in the table below.

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
| Lagged CU/AG ratio + 120-bar minimum hold | `next_bar` | 1,085,920 | 8.59% | -14.18% | 0.352 | 924 | Keep |
| CU/AG ratio breakout + correlation reversion exit | `next_bar` | 1,051,460 | 5.15% | -6.44% | 0.419 | 16 | Revise |
| Soft CU/AG breakout + correlation reversion exit | `next_bar` | 951,200 | -4.88% | -12.40% | -0.221 | 461 | Discard |
| Soft CU/AG breakout + positive correlation gate | `next_bar` | 998,400 | -0.16% | -9.84% | 0.031 | 268 | Revise |
| Mid CU/AG breakout + positive correlation gate | `next_bar` | 1,036,760 | 3.68% | -9.57% | 0.254 | 206 | Revise |
| Mid breakout + corr entry `0.05` | `next_bar` | 942,880 | -5.71% | -12.43% | -0.384 | 118 | Discard |
| Mid breakout + corr entry `0.10` | `next_bar` | 912,640 | -8.74% | -13.51% | -0.804 | 50 | Discard |
| Mid breakout + corr entry `0.05`, exit below `0.0` | `next_bar` | 888,990 | -11.10% | -18.51% | -0.634 | 114 | Discard |
| Mid breakout + corr entry `0.05`, 240-bar hold | `next_bar` | 929,600 | -7.04% | -16.40% | -0.351 | 114 | Discard |
| Mid breakout + corr entry `0.05`, 480-bar corr window | `next_bar` | 812,610 | -18.74% | -24.53% | -1.115 | 83 | Discard |

### Timing Validation

The 3-bar confirmed ratio signal was rerun with both fill modes:

| Variant | Execution | Final Equity | Return | Max DD | Daily Sharpe | Trades |
|---|---|---:|---:|---:|---:|---:|
| 3-bar confirmed ratio | `current_bar` | 1,048,010 | 4.80% | -13.87% | 0.236 | 1,096 |
| 3-bar confirmed ratio | `next_bar` | 1,063,000 | 6.30% | -13.90% | 0.291 | 1,096 |
| Lagged ratio + 3-bar confirmation | `next_bar` | 1,078,260 | 7.83% | -14.51% | 0.348 | 1,096 |

`next_bar` did not hurt this strategy in the tested window. Lagging the ratio by one SC bar made the predictor timing more conservative and improved return and Sharpe, at the cost of a slightly deeper drawdown.

### Current Read

The 120-bar minimum-hold variant is the best candidate so far, but it is not production-ready:

- It still underperforms buy-and-hold SC on total return.
- It reduces drawdown versus buy-and-hold, but only modestly.
- The 120-bar minimum hold reduced turnover from roughly `562x` to `472x` notional over the test window, but turnover remains very high.
- The best breakout/correlation variant so far is still the 720-bar breakout with a positive-correlation entry gate. Stricter correlation entry, slower exits, longer holds, and longer correlation windows all failed.
- Results still assume zero commission and no slippage.

## Iteration 7

### Hypothesis

Adding a minimum holding period to the lagged 3-bar confirmed CU/AG ratio signal should reduce rapid exit/re-entry churn while preserving the core inter-market timing edge.

Expected effect: fewer trades, lower turnover, and similar or slightly better drawdown if short-lived ratio reversals are mostly noise.

Expected risk: delayed exits can keep losing positions open longer and increase average loss or drawdown.

Files/modules likely affected: `strategy_playground/research_cu_ag_sc.py`, `strategy_playground/progress.md`.

Metrics to compare: final equity, total return, max drawdown, daily Sharpe, trades, win rate, average win/loss, exposure, turnover.

### Change

Added `lagged_ratio_min_hold`, preserving the lagged 240-bar ratio momentum, 0.004 entry threshold, 0.0 exit threshold, and 3-bar confirmation. The only behavioral change is `min_hold_bars = 120`, which blocks exits until the position has been held for at least 120 SC bars.

### Backtest Setup

- Data source: `adjusted_main_contract`
- Symbols: `CU9999.XSGE`, `AG9999.XSGE`, `SC9999.XINE`
- Date range: `20240101` to `20260422`
- Initial capital: `1,000,000`
- Costs/slippage: `0` commission and no slippage
- Baseline version: `lagged_ratio_three_bar_confirm`
- Execution timing: `next_bar`
- API base URL used in this run: `http://127.0.0.1:5001`

### Results

| Metric | Baseline | Candidate | Delta |
|---|---:|---:|---:|
| Final equity | 1,078,260 | 1,085,920 | +7,660 |
| Total return | 7.83% | 8.59% | +0.77 pp |
| Max drawdown | -14.51% | -14.18% | +0.32 pp |
| Daily Sharpe | 0.348 | 0.352 | +0.004 |
| Trades | 1,096 | 924 | -172 |
| Closed trades | 548 | 462 | -86 |
| Win rate | 51.64% | 54.76% | +3.12 pp |
| Average win | 4,291 | 4,934 | +643 |
| Average loss | -4,287 | -5,562 | -1,275 |
| Exposure | 34.34% | 39.05% | +4.72 pp |
| Turnover | 562.44x | 471.92x | -90.52x |

### Diagnostics

- Lookahead/data leakage: candidate keeps the existing one-SC-bar lag for CU/AG ratio observations and uses `next_bar` fills.
- Trade count: improved but still high at 924 fills and 462 completed round trips.
- Regime dependence: not separately validated in this iteration; all metrics use the full `20240101` to `20260422` sample.
- Runtime issues: none from the backtest API; diagnostics returned `[]`.
- Suspicious behavior: no empty-signal or duplicate-signal diagnostics. The average loss worsened materially, which is consistent with delayed exits and needs cost/tail-risk validation before production use.

### Decision

KEEP

Reason: the minimum hold reduced churn by 15.7%, reduced turnover by about 16.1%, and improved final equity, drawdown, Sharpe, and win rate without adding complex logic. The worsened average loss keeps this from being a final version.

### Next Step

Validate whether the kept candidate survives realistic execution assumptions:

- Add commission/slippage assumptions or a per-trade cost stress test.
- Re-run through the Flask API with `execution_timing="next_bar"`.
- If costs erase the edge, test a stronger churn filter such as a wider exit band instead of extending the hold period further.

## Breakout/Correlation Sweep

Working idea: CU/AG often reacts faster than crude to PMI, so a lagged CU/AG ratio breakout may lead a long SC move; exit when rolling CU/AG-return to SC-return correlation weakens.

Tested variants:

| Variant | Key parameters | Result | Decision |
|---|---|---|---|
| Strict breakout/reversion | `lookback=1200`, `margin=0.1%`, no entry corr gate | Very low drawdown and turnover, but only 16 fills and too little evidence | Revise |
| Soft breakout/reversion | `lookback=480`, `margin=0`, no entry corr gate | Trade count improved, but return turned negative | Discard |
| Soft breakout + corr gate | `lookback=480`, `margin=0`, `corr>0` at entry | Reduced damage versus soft breakout, but still no edge | Revise |
| Mid breakout + corr gate | `lookback=720`, `margin=0`, `corr>0` at entry | Best breakout version so far: 3.68% return, -9.57% max DD, 206 trades | Revise |

Current read: the breakout/correlation family is useful as a drawdown and turnover control, but the tested entry quality is still too weak. The mid-window variant is the only breakout candidate kept runnable in code.

Next step:

- Pause further breakout/correlation tuning after five consecutive failed follow-ups.
- If revisiting the PMI-lead hypothesis, test a direct ratio acceleration or percentile-thrust feature rather than a higher correlation threshold.

### Follow-Up Sweep: Correlation Quality

Question: can the 720-bar breakout improve if entry correlation is stronger or the correlation-reversion exit is less noisy?

| Variant | Return | Max DD | Sharpe | Trades | Decision |
|---|---:|---:|---:|---:|---|
| Entry corr `0.05` | -5.71% | -12.43% | -0.384 | 118 | Discard |
| Entry corr `0.10` | -8.74% | -13.51% | -0.804 | 50 | Discard |
| Entry corr `0.05`, exit corr `<0.0` | -11.10% | -18.51% | -0.634 | 114 | Discard |
| Entry corr `0.05`, 240-bar min hold | -7.04% | -16.40% | -0.351 | 114 | Discard |
| Entry corr `0.05`, 480-bar corr window | -18.74% | -24.53% | -1.115 | 83 | Discard |

Diagnostics:

- Lookahead/data leakage: all variants used the existing lagged CU/AG ratio update and `next_bar` fills.
- Trade count: all variants had enough fills to evaluate directionally, except the `0.10` threshold became sparse at 50 fills.
- Runtime issues: API diagnostics returned `[]` for all five runs.
- Suspicious behavior: tightening correlation made the system select worse trades. The relation is probably not well represented by contemporaneous rolling correlation.

Decision: DISCARD the stricter-correlation branch.

Online research note:

- S&P Global described copper-user PMI measures as forward-looking for copper demand and prices, including a copper-intensive new-orders/stocks ratio with a reported three-month lead to copper prices.
- Long-run commodity research by Martin Stuermer finds mineral commodity prices are primarily demand-shock driven, which supports the broader PMI/copper demand premise but not necessarily a minute-level rolling-correlation entry rule.

Sources: [S&P Global copper PMI commentary](https://prod.azure.ihsmarkit.com/marketintelligence/en/mi/research-analysis/pmi-data-indicate-headwinds-to-copper-prices.html), [Cambridge Core commodity price drivers](https://www.cambridge.org/core/journals/macroeconomic-dynamics/article/150-years-of-boom-and-bust-what-drives-mineral-commodity-prices/B037B3EE44D3110E6D67BD4572CE774D).

Next step:

- Keep `ratio_breakout_mid_corr_gate` only as a low-turnover control.
- For a new PMI-lead experiment, replace correlation gating with CU/AG ratio acceleration or a rolling percentile thrust, then exit on ratio momentum decay.
