# M1 report: does Faber (2010) hold up?

Written for a reader who knows some statistics but has not followed this project. Every number below is copied from a file in `results/` (the source is in brackets after it) or from the pre-registration in `prereg/`. Nothing here is a new analysis, with one labelled exception: the 67% median in section e. "pp" means percentage points; "pp per year" is an annualised average.

## Summary

- **Claim tested:** Faber (2010) says that each month holding the best-performing US industry sectors of the past 1 to 12 months beats holding all ten sectors equally, 1928 to 2009.
- **Test 1, reproduce (1928 to 2009): reproduced.** 172 of 180 of the paper's figures match within the pre-set tolerance (the bar was 162). (results/test1/result.json, strategy_claims)
- **Test 3, in-sample luck: beats luck.** The strategies earned +3.33 pp per year over the benchmark; 0 of 10,000 random sector pickers matched it, p = 0.0001. (results/test3-in/REPORT.md)
- **Test 2, after publication (2010-01 to 2026-09): weakened.** +3.07 pp per year, 92% of the in-sample figure, but p = 0.1110 over 201 months, so not clearly above zero. (results/after/result.json, test2)
- **Test 3, after publication: beats luck.** 0 of 10,000 random sector pickers matched +3.07 pp per year, p = 0.0001. (results/after/REPORT.md)

## a. What was tested

**The paper.** Mebane T. Faber, "Relative Strength Strategies for Investing", SSRN 1585517, First Draft April 2010. The PDF used is identified by SHA-256 `9f06e6051e7eb76b5ddf8b8955f96562303b4308bfd7da400a56835a785fb12e` (specs/faber-2010.yaml, paper.pdf_sha256).

**The strategy, in plain words.** At the end of each month, rank the ten US industry sectors by their return over the past L months, dividends included. During the next month, hold the top N sectors in equal parts. Repeat every month. A sector that drops out of the top N is sold at that month-end rebalance. There are no costs, taxes or slippage, as in the paper. The benchmark is all ten sectors held in equal parts, rebalanced monthly. (prereg/0001-faber-2010.md, section 2; specs/faber-2010.yaml, signal, weighting, rebalance, costs, benchmark)

The paper reports L in {1, 3, 6, 9, 12} months and N in {1, ..., 9}, so there are 45 versions. (prereg/0001-faber-2010.md, section 2)

**The data.** Kenneth French Data Library, "10 Industry Portfolios", monthly, the "Average Value Weighted Returns" table. That is 10 industries, 1203 months, 1926-07 to 2026-09, returns in percent. (data/pins.json)

- File: `10_Industry_Portfolios.csv`, SHA-256 `921e2df7ae95355cf9030aebc8b2033c267f3153fb99a676ff912b3ea65d1ed3`; zip SHA-256 `cee051709825e60cc38f2aff01c2dec52265aa7ea4a1fefa023a2c8114a5166e`; downloaded 2026-11-06. (data/pins.json)
- **END = 2026-09**, the last month in that file. It was fixed by the file before any run. (prereg/0001-faber-2010.md, section 1; data/pins.json, end_month)
- The file is not committed because its copyright terms do not clearly allow redistribution; only the pin is. (data/README.md)
- It is a newer vintage than the paper's, so small differences from the paper's numbers are expected. (prereg/0001-faber-2010.md, section 1)

**The samples.** In-sample: holding months 1928-01 to 2009-12, 984 months, the paper's own period. After publication: 2010-01 to END (2026-09), 201 months. (prereg/0001-faber-2010.md, section 2; results/test3-in/REPORT.md; results/after/REPORT.md)

**How the paper's numbers were obtained.** The strategy spec was AI-drafted and human-verified. The paper's tables are images, so their numbers were read by eye rather than quoted. A second, independent reading was made and compared with the first; the two agreed on all 187 values. (specs/faber-2010.yaml, extraction and the comment above `claims`) Every spec value is marked as stated by the paper, inferred, assumed, or read from a table. (docs/decisions/0001-provenance.md)

## b. How it was kept honest

**Pre-registration.** Before any result existed, the rules, the tolerances and the verdict thresholds were written down and committed. A SHA-256 lock file pins each file in `prereg/`.

**Run guards.** Every runner refuses to start if the lock fails, if the code, pre-registration, spec or data pin has uncommitted changes, or if the data file does not match its pin. Later runners also refuse unless the previous test's result is committed. (src/quaver/test1.py and src/quaver/runs.py, module docstrings)

| Tag | Commit | What it is | SHA-256 of the file |
|---|---|---|---|
| `prereg-0001` | `214777f` | The pre-registration | `1bef0800e5e10e1ea0daba33f2a1ae0e1dbed0e42b1454c20f1c686b71a69003` |
| `prereg-0001-a01` | `50865fa` | Amendment 01 | `b83a860975de3684350776009cfa64d977755c8030d9fdfb9991de241318f5fb` |
| `prereg-0001-a02` | `9a69c92` | Amendment 02 | `d7a6c0c24199938426d501ea80b9bf5ee0b38ba77cde1960bb9cf75e148e1599` |

(prereg/LOCKS.sha256; commits from results/after/result.json, preregistration_files; tags from `git tag`)

**Amendment 01** (written before any result existed; three clarifications, no rule changed):
1. Calendar-year figures use complete calendar years only. After publication, 2026 runs only to September, so it is reported separately as a partial year.
2. The family's monthly return is the average of the 15 versions' returns in that month.
3. In the drift-weights sensitivity check, every held sector starts at equal weight in the first holding month.

**Amendment 02** (written after Test 1 and Test 3 in-sample had been run, before any after-publication result existed; no statistic had been computed on data after 2009-12):
1. Clarifies amendment 01, point 1: the partial-year exclusion applies to calendar-year figures only. Test 2 and Test 3 after publication use every month from 2010-01 to 2026-09, T = 201.
2. Adds one figure, reported without a verdict: Test 2's statistic for 2010-01 to 2025-12, complete years only.
3. Records that the random family's 15 versions follow the real family's order (by lookback, then holding count).

(prereg/0001-faber-2010-amendment-01.md, amendment-02.md)

**The data pin.** The file was hashed and its pin committed (`b7c6cdb`) before any strategy code or result existed. The loader refuses any file whose hash differs from the pin. (git log; data/README.md)

**The order of the tests, and one commit per verdict.** The pre-registration fixes the order: Test 1; then Test 3 in-sample; then Test 2 and Test 3 after publication in one run. Each verdict is committed before the next test runs. A second run of any test needs `--rerun` with a stated reason, and the earlier result is kept. (prereg/0001-faber-2010.md, section 8; src/quaver/runs.py, module docstring)

| Step | Result commit | Verdict | Run at (UTC) |
|---|---|---|---|
| Test 1, reproduce | `d3e4235` | reproduced | 2026-11-06 15:33 (results/test1/result.json, run_at_utc) |
| Test 3, in-sample | `ab9f861` | beats luck | 2026-11-06 16:33 (results/test3-in/result.json, run_at_utc) |
| Test 2 and Test 3, after publication | `85ab10f` | weakened; beats luck | 2026-11-06 16:53 (results/after/result.json, run_at_utc) |

The commit hashes are from `git log`. Amendment 02 (`9a69c92`) was committed between the second and third rows.

## c. Results

### Test 1: Reproduce (1928-01 to 2009-12)

**Pre-registered rule.** Recompute the paper's 180 strategy claims (45 versions times CAGR, volatility, Sharpe ratio and maximum drawdown) and compare each with its tolerance (absolute difference): CAGR 0.50 pp, volatility 0.50 pp, Sharpe 0.03, max drawdown 2.0 pp. Reproduced: at least 162 (90%) within tolerance. Partly reproduced: 90 to 161. Not reproduced: fewer than 90. A data check comes first: our benchmark CAGR and volatility must both be within tolerance, or the verdict is "inconclusive: data differ". (prereg/0001-faber-2010.md, section 4)

**Outcome: reproduced, 172 of 180.** (results/test1/result.json, strategy_claims)

- Data check, benchmark: passed. CAGR ours 10.24 against the paper's 10.28 (difference -0.04 pp); volatility ours 18.49 against 18.38 (+0.11 pp). (results/test1/REPORT.md)

| Metric | Within tolerance | Of |
|---|---|---|
| CAGR | 43 | 45 |
| Volatility | 45 | 45 |
| Sharpe ratio | 44 | 45 |
| Max drawdown | 40 | 45 |

(results/test1/result.json, strategy_claims.by_metric)

All six tested benchmark claims were within tolerance. (results/test1/REPORT.md, Benchmark claims)

**The eight misses, and the five largest.** Differences are ours minus the paper's. The five below are ordered by how far each is outside its own tolerance, largest first. (results/test1/REPORT.md, difference tables)

| Claim | Version | Metric | Paper | Difference | Tolerance |
|---|---|---|---|---|---|
| C148 | 12-month, Top 1 | max drawdown | -76.91 | -3.85 pp | 2.00 pp |
| C145 | 12-month, Top 1 | CAGR | 16.05 | -0.88 pp | 0.50 pp |
| C40 | 3-month, Top 1 | max drawdown | -64.50 | -3.48 pp | 2.00 pp |
| C8 | 1-month, Top 2 | max drawdown | -74.21 | -3.27 pp | 2.00 pp |
| C147 | 12-month, Top 1 | Sharpe ratio | 0.56 | -0.047 | 0.030 |

(paper values: results/test1/result.json, claims). The other three misses are C88 (6-month, Top 4, max drawdown, -2.59 pp), C76 (6-month, Top 1, max drawdown, +2.50 pp) and C109 (9-month, Top 1, CAGR, -0.51 pp).

**Likely causes.** These are inferences from the pattern of misses; no test was run to confirm them.
- *One-sector Top 1 versions.* Six of the eight misses, and four of the five largest, are Top 1 versions. Holding a single sector each month makes the result depend on a few months' returns for that one sector.
- *Drawdowns.* Five of the eight misses are maximum drawdown, a figure set by a single worst stretch and so sensitive to small differences in a few months.
- *Data revisions.* Our file is a later vintage than the paper's, and French revises the series as CRSP restates history. A small restatement in a few sector-months can move a one-sector drawdown by a few points while leaving most averages almost unchanged. This fits the pattern but is not shown here.

**Sensitivity checks (no effect on the verdict).** With weights left to drift between rebalances, 166 of 180 claims are within tolerance; with volatility (and so the Sharpe ratio) computed with ddof = 0, 172 of 180. (results/test1/result.json, sensitivity)

### Test 3, in-sample: could random picks have done as well? (1928-01 to 2009-12)

**Pre-registered rule.** A random family: for each of the 15 versions with N in {1, 2, 3} across the five lookbacks, each month pick N sectors uniformly at random without replacement, at equal weight, then average the 15. Draw 10,000 random families with `numpy.random.default_rng(20261106)`. The statistic is the family's annualised mean excess return over the benchmark. p = (1 + the number of random families at least as high as the real one) / 10,001. "Beats luck" if p < 0.05. (prereg/0001-faber-2010.md, sections 5 and 6)

**Outcome: beats luck.** (results/test3-in/REPORT.md)

| | In-sample, 1928-01 to 2009-12 (984 months) |
|---|---|
| Real family | +3.33 pp per year |
| Random families at least as high | 0 of 10,000 |
| p | 0.0001 |
| Random families, 5th / 50th / 95th percentile | -0.39 / +0.00 / +0.39 pp per year |

With 10,000 random families, 0.0001 is the smallest p the formula can give. The real result sits far outside the random range, whose histogram ends in a single family in the +0.88 to +1.05 bin. (results/test3-in/REPORT.md, histogram)

### Test 2: After publication (2010-01 to 2026-09), run once

**Pre-registered rule.** The same family statistic (15 versions, N in {1, 2, 3}) over 2010-01 to END. Estimator: Newey-West standard error with floor(4 x (T/100)^(2/9)) lags, one-sided test that the mean is above zero, p from the normal distribution. "Survived" if p < 0.05. "Weakened" if the estimate is above zero and p >= 0.05. "Gone" if the estimate is zero or below. (prereg/0001-faber-2010.md, section 5)

**Outcome: weakened.** (results/after/result.json, test2; results/after/REPORT.md)

| | Value |
|---|---|
| Months | 201 (2010-01 to 2026-09) |
| Estimate | +3.07 pp per year |
| Newey-West standard error | 2.51 pp (4 lags) |
| z | 1.221 |
| One-sided p | 0.1110 |
| In-sample estimate (1928-01 to 2009-12) | +3.33 pp per year |
| After publication / in-sample | 0.92 |
| Complete years only, 2010-01 to 2025-12 (192 months), no verdict | +3.94 pp per year, standard error 2.53 pp, z = 1.557, p = 0.0597 |

(results/after/result.json: test2, in_sample, ratio_after_to_in_sample, complete_years)

**For context.** McLean and Pontiff (2016) found that published stock-return predictors earned returns 58% lower after publication on average, a ratio of 0.42. Our ratio is 0.92. (results/after/REPORT.md; prereg/0001-faber-2010.md, section 5)

**What "weakened" means here.** It is the pre-registered name for "the estimate is above zero and p >= 0.05". It does not mean the edge shrank. Here the estimate is 92% of the in-sample figure, so the edge looks about as large as before. But 201 months are too noisy to call it clearly above zero: the standard error (2.51 pp) is almost as large as the estimate (3.07 pp). The label records only that the pre-set bar for "survived" was not met. The complete-years figure, which drops the nine months of 2026, gives p = 0.0597, just above the 0.05 line; it carries no verdict, because amendment 02 made it a reported figure only.

### Why Test 3 and Test 2 differ after publication

Test 3 asks: could random sector picks have done as well in the same period? Here they could not (0 of 10,000 at least as high; random families' 5th to 95th percentile -1.05 to +1.07 pp per year, against the real +3.07). (results/after/REPORT.md)

Test 2 asks a different question: given how much the family's monthly excess return jumps around, is its average clearly above zero? With a standard error of 2.51 pp, +3.07 pp is not.

Both can be true at once. Test 3 says the real result is not what random picking produces. Test 2 says that, on 201 months, the average cannot be pinned down well enough to rule out zero.

## d. Choices made during the build that the pre-registration did not spell out

None of these changed a rule, a tolerance or a verdict threshold. They are listed so a reader can check them.

**From the Test 1 runner** (`a884216`, "Add Test 1 runner"):
1. *A difference exactly equal to the tolerance counts as within*, with a 1e-9 allowance for floating-point error only. (src/quaver/test1.py, `is_within`, `FLOAT_SLACK`)
2. *The ddof = 0 sensitivity check also recomputes the Sharpe ratio*, since Sharpe divides by volatility. (src/quaver/test1.py, `metric_value`; results/test1/REPORT.md, Sensitivity checks)
3. *Beating the benchmark in a calendar year means a strictly higher calendar-year return.* (src/quaver/test1.py, `_beat_shares`)
4. *A rerun keeps the old REPORT.md as REPORT-n.md*, next to result-n.json. (src/quaver/test1.py, `run_test1`)

**From the strategy code** (`f2a8646`, "Add Faber strategy, metrics and no-lookahead tests"), already written into amendment 01:
5. The family is the average of the 15 versions' monthly returns. (amendment 01, point 2)
6. Under drift weights, every held sector starts at equal weight. (amendment 01, point 3)
7. Incomplete calendar years are refused rather than guessed at. (src/quaver/metrics.py, `calendar_year_returns`; amendment 01, point 1)

**From Test 2 and Test 3** (`5a68341`, "Add Test 2 and Test 3 runners"; `ff6e31a`, "Report all 45 versions after publication"):
8. *Chunks of 100.* Random families are drawn from one generator in chunks of 100, in order, so the first 100 families do not depend on the total number drawn (`5a68341`; src/quaver/luck.py, `CHUNK`).
9. *Version order.* A random family's 15 versions follow the real family's order, lookbacks outer and holding counts inner (`5a68341`; amendment 02, point 3).
10. *The per-version table covers all 45 versions.* The pre-registration asks for "every version's after-publication numbers"; the first runner reported only the 15 family versions, and `ff6e31a` extended it to all 45, with the family members marked. (results/after/REPORT.md, "Every version after publication")

**Reporting changes before the after-publication run.** After Test 1 and Test 3 in-sample were committed, and before the after-publication run, three commits changed what is reported, not what is computed: `9a69c92` (amendment 02), `22905b1` ("Report complete-years figure; record all pre-registration hashes") and `ff6e31a` (above). Because `22905b1` came after Test 1 and Test 3 in-sample, those two result files list only the pre-registration and amendment 01 in their provenance; the lock file and the after-publication result list all three. (git log; Provenance sections of the three REPORT.md files)

## e. What M1 does not show

- **Costs and tradability.** All results exclude taxes, commissions and slippage, as the paper does. Whether anyone could have traded these portfolios at these prices is not tested. Costs, tradability, forward and live tests each need their own pre-registration. (specs/faber-2010.yaml, costs; prereg/0001-faber-2010.md, section 8)
- **The paper's combined strategy and its headline.** The paper's best-known result is that its relative-strength portfolios beat buy-and-hold in "approximately 70% of all years". That appears to summarise Exhibit 4.6, a combined 1-3-6-9-12 strategy (an average of five trailing returns) that the spec cannot express as a single lookback, so it was left out of every test and has no verdict. (prereg/0001-faber-2010.md, section 4; specs/faber-2010.yaml, header comments) The closest descriptive figure here is a median of 67% of calendar years 1928 to 2009 beating the benchmark across our 45 single-lookback versions. That median is computed for this report as the median of the 45 shares in results/test1/result.json (beat_benchmark.versions), which is 0.6707; no results file prints it. It is descriptive only and tests nothing. After publication, the family beat the benchmark in 9 of 16 complete years (56%). (results/after/result.json, family)
- **A random-pick test is a limited test.** "Beats luck" shows the result is not what random sector picking would give. It does not show that momentum is the reason.
- **One paper, one data source, one run.** The after-publication period has 201 months and ends in the same month as the data. A different data vintage, sector definition or ending month could move the estimate.
- **Not investment advice.** This is research on historical data. Nothing here is a recommendation to buy or sell anything.

## f. How to reproduce

```
uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
uv run quaver data-check        # verifies data/raw/10_Industry_Portfolios.csv against data/pins.json
uv run quaver run-test1         # Test 1; writes results/test1/
uv run quaver run-test3-in      # Test 3, in-sample; writes results/test3-in/
uv run quaver run-after         # Test 2 and Test 3, after publication; writes results/after/
```

(src/quaver/cli.py)

- **The data pin.** Put the file with SHA-256 `921e2df7ae95355cf9030aebc8b2033c267f3153fb99a676ff912b3ea65d1ed3` at `data/raw/10_Industry_Portfolios.csv`. The loader refuses any other file. (data/pins.json)
- **Results already exist in this repository.** Each runner runs once. To run again in a scratch clone, pass `--rerun "<reason>"`; the earlier result is kept. (src/quaver/cli.py)
- **A newer French download will differ slightly.** French revises the file as CRSP data is restated and new months are added, so its hash changes and the pin will not match. A fresh download is a different vintage and needs a new pin and, for any pre-registered test, a dated amendment. (data/README.md)
- **Seeds.** The random generator is `numpy.random.default_rng(20261106)`, 10,000 families. (results/after/REPORT.md, Provenance)
