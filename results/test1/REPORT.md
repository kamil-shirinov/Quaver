# Test 1 (reproduce): Relative Strength Strategies for Investing (2010)

**Verdict: reproduced.** 172 of 180 strategy claims are within tolerance.

Pre-registered bands: reproduced at least 162, partly reproduced 90 to 161, not reproduced fewer than 90; "inconclusive: data differ" if the data check fails.

Data check, benchmark: **passed**. CAGR: ours 10.24, paper 10.28, difference -0.04 pp (tolerance 0.50); volatility: ours 18.49, paper 18.38, difference +0.11 pp (tolerance 0.50).

## Strategy claims within tolerance, by metric

| Metric | Within | Of | Tolerance |
|---|---|---|---|
| CAGR | 43 | 45 | 0.50 pp |
| volatility | 45 | 45 | 0.50 pp |
| Sharpe ratio | 44 | 45 | 0.030 |
| max drawdown | 40 | 45 | 2.00 pp |

## Differences, ours minus the paper

Rows are lookbacks, columns are Top N. A cell outside tolerance is bold and marked ✗.

### CAGR (tolerance 0.50 pp)

| Lookback | Top1 | Top2 | Top3 | Top4 | Top5 | Top6 | Top7 | Top8 | Top9 |
|---|---|---|---|---|---|---|---|---|---|
| 1 mo | -0.09 | -0.44 | -0.26 | +0.04 | +0.19 | -0.01 | +0.06 | +0.02 | +0.05 |
| 3 mo | -0.20 | -0.43 | +0.18 | -0.05 | -0.12 | +0.04 | -0.03 | -0.04 | +0.01 |
| 6 mo | -0.37 | -0.30 | +0.06 | +0.08 | -0.11 | -0.06 | +0.01 | -0.10 | -0.00 |
| 9 mo | **-0.51 ✗** | -0.45 | -0.04 | +0.02 | +0.14 | +0.10 | -0.04 | -0.03 | -0.07 |
| 12 mo | **-0.88 ✗** | -0.41 | -0.28 | -0.02 | +0.05 | +0.03 | -0.01 | -0.06 | -0.02 |

### volatility (tolerance 0.50 pp)

| Lookback | Top1 | Top2 | Top3 | Top4 | Top5 | Top6 | Top7 | Top8 | Top9 |
|---|---|---|---|---|---|---|---|---|---|
| 1 mo | +0.12 | +0.13 | +0.11 | +0.17 | +0.14 | +0.11 | +0.15 | +0.13 | +0.11 |
| 3 mo | +0.04 | +0.08 | +0.21 | +0.13 | +0.24 | +0.21 | +0.12 | +0.15 | +0.15 |
| 6 mo | +0.08 | -0.17 | -0.03 | +0.14 | +0.05 | +0.16 | +0.10 | +0.11 | +0.12 |
| 9 mo | -0.02 | +0.01 | +0.10 | +0.15 | +0.04 | +0.04 | +0.09 | +0.08 | +0.12 |
| 12 mo | +0.36 | +0.15 | +0.12 | +0.10 | +0.20 | +0.15 | +0.14 | +0.08 | +0.11 |

### Sharpe ratio (tolerance 0.030)

| Lookback | Top1 | Top2 | Top3 | Top4 | Top5 | Top6 | Top7 | Top8 | Top9 |
|---|---|---|---|---|---|---|---|---|---|
| 1 mo | -0.002 | -0.029 | -0.019 | -0.007 | +0.010 | -0.003 | +0.000 | +0.003 | +0.003 |
| 3 mo | -0.013 | -0.021 | +0.003 | -0.002 | -0.011 | -0.001 | -0.006 | -0.008 | -0.002 |
| 6 mo | -0.020 | -0.015 | +0.007 | -0.002 | -0.011 | -0.012 | -0.005 | -0.008 | -0.004 |
| 9 mo | -0.028 | -0.028 | -0.002 | -0.007 | +0.007 | +0.001 | +0.000 | +0.000 | -0.006 |
| 12 mo | **-0.047 ✗** | -0.026 | -0.018 | -0.006 | -0.002 | -0.006 | -0.006 | -0.003 | -0.009 |

### max drawdown (tolerance 2.00 pp)

| Lookback | Top1 | Top2 | Top3 | Top4 | Top5 | Top6 | Top7 | Top8 | Top9 |
|---|---|---|---|---|---|---|---|---|---|
| 1 mo | -1.19 | **-3.27 ✗** | -1.23 | -1.16 | -0.73 | -0.89 | -1.11 | -1.05 | -0.27 |
| 3 mo | **-3.48 ✗** | +0.19 | +1.45 | +0.15 | -1.22 | -0.11 | +0.01 | -0.36 | -0.37 |
| 6 mo | **+2.50 ✗** | -0.43 | +0.66 | **-2.59 ✗** | -0.21 | -0.54 | +0.04 | -0.37 | -0.15 |
| 9 mo | +1.62 | -0.04 | +0.05 | +1.06 | +0.80 | +0.71 | +0.07 | -0.10 | -0.12 |
| 12 mo | **-3.85 ✗** | -1.02 | +1.01 | -0.41 | +0.02 | -1.02 | -1.01 | -0.01 | -0.10 |

## Benchmark claims

| Claim | Metric | Paper | Ours | Difference | Tolerance | Within |
|---|---|---|---|---|---|---|
| C181 | CAGR | 10.28 | 10.24 | -0.04 | 0.50 | yes |
| C182 | volatility | 18.38 | 18.49 | +0.11 | 0.50 | yes |
| C183 | Sharpe ratio | 0.350 | 0.348 | -0.002 | 0.030 | yes |
| C184 | max drawdown | -81.67 | -81.91 | -0.24 | 2.00 | yes |
| C185 | best year | 53.38 | 53.51 | +0.13 | 1.00 | yes |
| C186 | worst year | -38.21 | -38.53 | -0.32 | 1.00 | yes |

Not tested, as pre-registered: C187 (turnover).

## Sensitivity checks

Reported only; they never change the verdict. Strategy claims within tolerance when the weights drift between rebalances (each held sector starts at equal weight in the first holding month), and when volatility, and so the Sharpe ratio, uses ddof = 0.

| Check | Within | Of | CAGR | volatility | Sharpe ratio | max drawdown |
|---|---|---|---|---|---|---|
| Drift weights | 166 | 180 | 41 | 45 | 41 | 39 |
| Volatility ddof = 0 | 172 | 180 | 43 | 45 | 44 | 40 |

## Share of calendar years beating the benchmark

Calendar years 1928 to 2009 (82 years) in which the version's return was above the benchmark's. No verdict.

| Lookback | Top1 | Top2 | Top3 | Top4 | Top5 | Top6 | Top7 | Top8 | Top9 |
|---|---|---|---|---|---|---|---|---|---|
| 1 mo | 57% | 66% | 68% | 73% | 74% | 72% | 76% | 84% | 74% |
| 3 mo | 61% | 70% | 71% | 72% | 73% | 71% | 62% | 62% | 62% |
| 6 mo | 60% | 65% | 67% | 71% | 68% | 66% | 70% | 62% | 62% |
| 9 mo | 60% | 66% | 65% | 63% | 63% | 63% | 62% | 67% | 65% |
| 12 mo | 65% | 67% | 70% | 67% | 71% | 68% | 66% | 73% | 60% |

## Provenance

- Pre-registration: `214777f5762af8a2a59f5001cd5798a94818c542`
- Amendment 01: `50865fa0380db8be617c03e9f7d6d526b8712405`
- Spec: `4554c9f9d1b23957d90b2788fcbd4114af7a83e9`
- Code: `a884216963e93b640d182a7719fca00dabc8124c`
- Data: `data/raw/10_Industry_Portfolios.csv`, SHA-256 `921e2df7ae95355cf9030aebc8b2033c267f3153fb99a676ff912b3ea65d1ed3` (pin `921e2df7ae95355cf9030aebc8b2033c267f3153fb99a676ff912b3ea65d1ed3`), zip SHA-256 `cee051709825e60cc38f2aff01c2dec52265aa7ea4a1fefa023a2c8114a5166e`, downloaded 2026-11-06
- Run at (UTC): 2026-11-06T15:33:23+00:00
