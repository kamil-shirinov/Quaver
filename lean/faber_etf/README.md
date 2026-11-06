# Faber's family on sector ETFs, in QuantConnect LEAN

A LEAN algorithm that trades the family of 15 Faber (2010) relative-strength versions on the
nine original Select Sector SPDR ETFs, or the equal-weight benchmark, or a smoke test of the
same code on a dummy universe.

| File | What it is |
| --- | --- |
| `main.py` | The algorithm. It runs only inside QuantConnect. |
| `logic.py` | The arithmetic: trailing returns, selection, family weights, order sizes, the log. Plain Python, tested in this repository. |

## What it does

- **Universe:** XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY, fixed and in that order (ties go to the one listed first). Smoke mode uses SPY, TLT, GLD, IWM instead.
- **Data:** QuantConnect daily US equity data, adjusted for splits and dividends.
- **Signal:** after the close of each month's last trading day, each ETF's total return over the last L months, from month-end adjusted closes.
- **Family:** target weights are the average of 15 versions' weights (L in 1, 3, 6, 9, 12; N in 1, 2, 3; each version holds 1/N in its top N).
- **Benchmark:** 1/9 in each ETF, rebalanced the same way.
- **Orders:** market-on-open orders for the next trading day, sells first, filled at the open price with no slippage. Fee: 10 bps of traded value per order.
- **Cash buffer:** targets are sized on 99% of the portfolio value at the signal close, so 1% stays in cash to pay fees and absorb the move to the next open.
- **Money:** starts with $100,000. The first holding month is 2000-01 (2006-01 in smoke mode, because GLD's first month-end close is 2004-11).

The algorithm stops with an error instead of carrying on if an order is invalid, a fill is not at the next trading day's open, a fee is not 10 bps, a month-end close is missing, or the last holding month has no value.

## Parameters

| Name | Values |
| --- | --- |
| `mode` | `smoke`, `family` or `benchmark` |
| `end` | the last holding month, `YYYY-MM`. It must be a complete month in QuantConnect's data. |

The `family` and `benchmark` runs produce results of a test, so run them only after their pre-registration is committed. Run `smoke` first.

## Running it on QuantConnect

1. Sign in at [quantconnect.com](https://www.quantconnect.com). The free plan is enough.
2. Open **Algorithm Lab** and create a new **Python** project, for example "faber-etf".
3. Open the project's `main.py`, delete everything in it, and paste in the whole of `lean/faber_etf/main.py` from this repository.
4. Add a file to the project named exactly `logic.py` and paste in the whole of `lean/faber_etf/logic.py`.
5. In the project panel, under **Parameters**, add two parameters: `mode` (for example `smoke`) and `end` (for example `2026-09`).
6. Click **Backtest** and wait for it to finish. If it stops with a runtime error, copy the error message; no log block is written.
7. In the backtest's results, open the **Logs** tab and download the log, or select all of it and copy it into a text file. Keep the whole file: the parser finds the block between the `QUAVER-LOG v1` line and the `QUAVER-END` line and ignores the rest.

The log block is one line per month, `YYYY-MM value`, the portfolio value at that month's last close, starting with the month before the first holding month (its value is the $100,000 starting cash). Then come the total fees, the number of filled orders and the lowest cash balance after any rebalance. A full run to 2026-09 writes about 7 KB, under the free plan's 10 KB log limit.

## Reading the log

```
uv run python -c "
from pathlib import Path
from quaver.qc import parse_log
run = parse_log(Path('smoke.log').read_text())
print(run.mode, run.months[0], run.months[-1], len(run.returns), run.fees, run.orders, run.min_cash)
"
```

`parse_log` refuses a log with a missing or repeated month, months out of order, or a malformed line inside the block. `run.returns[k]` is month `run.months[k]`'s return, from consecutive month-end values.

In a smoke run, check that `min_cash` is not negative: a negative value means the buffer was too small at some rebalance and the portfolio briefly borrowed.
