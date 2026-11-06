# Quaver
Verification for quant finance research. The name is short for quant verification.

Quaver rebuilds the trading strategies described in published quant finance papers and tests whether their results hold up: first on the paper's own data, then on data the authors never saw, then on new data as it arrives. Every pass or fail rule is fixed in advance, and every parameter is traced to a page in the paper. It reports which claims survive, failures included.

Status: M1 done (tag `m1`): Faber (2010), Relative Strength Strategies for Investing.

## Results

M1 tested Faber (2010), who reports that each month holding the best-performing US industry sectors of the past 1 to 12 months beats holding all ten equally. Four tests were fixed in advance and run in this order:

| Test | Verdict | Key number |
| --- | --- | --- |
| 1. Reproduce the paper's figures, 1928 to 2009 | Reproduced | 172 of 180 figures within tolerance (the bar was 162) |
| 3. Could random sector picks do as well? In-sample, 1928 to 2009 | Beats luck | +3.33 percentage points a year over the benchmark; 0 of 10,000 random families matched it (p = 0.0001) |
| 2. Is the gain still above zero after publication? 2010-01 to 2026-09 | Weakened | +3.07 points a year, 92% of the in-sample figure, p = 0.1110 over 201 months |
| 3. Could random sector picks do as well? After publication | Beats luck | +3.07 points a year; 0 of 10,000 random families matched it (p = 0.0001) |

"Weakened" is the pre-registered name for "estimate above zero, p >= 0.05". Here the edge looks about as large as before, but 201 months are too noisy to call it clearly above zero. Costs and tradability are not tested. This is research on historical data, not investment advice.

Full write-up: [docs/reports/m1-faber-2010.md](docs/reports/m1-faber-2010.md).
