---
name: quant-research-loop
description: Run disciplined iterative research on algorithmic trading strategies in backtesting or event-driven systems. Use when Codex needs to improve a strategy through repeated hypothesis-build-backtest-diagnose-decide cycles, especially for Python signal classes, rules, triggers, or strategy modules where robustness, drawdown control, and backtest validity matter more than blind optimization.
---

# Quant Research Loop

## Overview

Act as a quantitative research assistant, not a blind optimizer. Improve strategies through small, attributable changes that preserve a clean baseline, produce measurable evidence, and end each iteration with a keep, revise, or discard decision.

Optimize for robustness first, then return. Treat suspiciously strong results as a reason to slow down and inspect assumptions before accepting them.

## Workflow

Follow this loop:

`Idea -> Build -> Backtest -> Diagnose -> Decide -> Repeat`

Start each cycle by reading the nearest relevant docs and surrounding code in the owning module. Favor small changes in the most specific module that owns the behavior.

## Step 1: Form One Hypothesis

Begin each iteration with exactly one concrete idea.

Record:

```text
Hypothesis:
Expected effect:
Expected risk:
Files/modules likely affected:
Metrics to compare:
```

Good hypotheses are narrow and testable:

- Add a volatility filter to avoid noisy regimes.
- Require trend confirmation before mean-reversion entries.
- Add a time-in-trade or signal-decay exit.
- Replace a fixed threshold with a rolling percentile.
- Add liquidity or volume confirmation.
- Require multi-bar confirmation to reduce false positives.

Do not batch unrelated changes into one experiment.

## Step 2: Build the Smallest Useful Change

Implement the minimum change needed to test the hypothesis.

Keep these rules:

- Preserve existing strategy behavior as the baseline.
- Keep parameters explicit and typed.
- Avoid hidden global state.
- Avoid unrelated refactors during research iterations.
- Preserve event-driven boundaries: signals detect and emit; they do not perform downstream actions.
- Update nearby docs or comments when public behavior changes.

Before backtesting, verify that the code runs and that the signal contract still makes sense.

## Step 3: Backtest Against a Stable Baseline

Use the same data source, baseline period, and assumptions when comparing versions unless the point of the iteration is cross-regime validation.

Capture at least:

```text
Strategy version:
Data source:
Symbols:
Date range:
Initial capital:
Transaction cost assumptions:
Slippage assumptions:
Number of trades:
Final equity:
Total return:
Max drawdown:
Sharpe or risk-adjusted metric:
Win rate:
Average win/loss:
Exposure:
Turnover:
```

When possible, compare against:

- The previous strategy version
- Buy-and-hold or passive baseline
- A no-filter or no-change control
- Different date ranges or regimes
- Different symbols if the strategy is meant to generalize

Do not accept a change solely because final equity increased.

## Step 4: Diagnose Before Accepting Results

Inspect the results for validity problems and brittle behavior before making any recommendation.

Check:

```text
Lookahead bias:
Data leakage:
Survivorship bias:
Unrealistic fills:
Missing transaction costs:
Too few trades:
Overly concentrated returns:
Large drawdown increase:
Parameter sensitivity:
Strategy only works in one narrow period:
Signal fires too frequently:
Signal fires too rarely:
Unexpected empty signals:
Unexpected duplicate signals:
Runtime errors or diagnostics:
```

Also inspect representative trades and dead zones:

- Best trade
- Worst trade
- Longest holding period
- Fastest loss
- Cluster of losing trades
- Periods with no signals

If results look unusually good, assume there may be leakage, invalid fills, or regime overfit until proven otherwise.

## Step 5: Decide

End every iteration with one decision:

```text
KEEP:
The idea improves core metrics without introducing unacceptable risk.

REVISE:
The idea shows partial promise but needs a narrower follow-up.

DISCARD:
The idea fails, overfits, increases risk, or adds complexity without enough value.
```

State the reason clearly and name the next idea only if it follows from the evidence.

Example:

```text
Decision: REVISE
Reason: Volatility filter reduced drawdown by 18%, but also cut total return by 35%.
Next idea: Test a softer volatility percentile threshold instead of a hard cutoff.
```

## Priority Order

Optimize in this order:

1. Backtest validity
2. Lower drawdown and tail risk
3. Stability across regimes
4. Reasonable trade count
5. Return improvement
6. Simplicity and maintainability

Prefer a simpler, more robust strategy over a higher-return but fragile one.

## Iteration Log Template

Use this format for every cycle:

```markdown
## Iteration N

### Hypothesis
...

### Change
...

### Backtest Setup
- Data source:
- Symbols:
- Date range:
- Costs/slippage:
- Baseline version:

### Results
| Metric | Baseline | Candidate | Delta |
|---|---:|---:|---:|
| Final equity | | | |
| Total return | | | |
| Max drawdown | | | |
| Sharpe | | | |
| Trades | | | |
| Win rate | | | |

### Diagnostics
- Lookahead/data leakage:
- Trade count:
- Regime dependence:
- Runtime issues:
- Suspicious behavior:

### Decision
KEEP / REVISE / DISCARD

### Next Step
...
```

## End-of-Cycle Output

After each cycle, report:

```text
What changed:
What improved:
What got worse:
Any suspected issues:
Decision:
Recommended next iteration:
```

## Stopping Criteria

Pause the loop and summarize when any of these happen:

- Three consecutive iterations fail to improve the strategy.
- A result looks too good to be realistic.
- The change requires missing data or unsupported assumptions.
- Complexity increases materially without robust gains.
- Diagnostics suggest leakage or invalid fills.
- The next step requires a human decision on objective, market, or risk tolerance.
