# Test 3 (luck), in-sample: Faber (2010), Relative Strength Strategies for Investing

**Verdict: beats luck.** p = 0.0001. Pre-registered: "beats luck" if p < 0.05, otherwise "not distinguishable from luck".

Statistic: the family's annualised mean excess return over the benchmark, 1928-01 to 2009-12 (984 months).

- Real family: +3.33 pp per year
- Random families at least as high: 0 of 10,000
- p = (1 + 0) / 10,001 = 0.0001
- Random families, pp per year: 5th percentile -0.39, median +0.00, 95th percentile +0.39

Random families, pp per year (bins, bar, count):

```text
  -0.87 to   -0.70 | #                                                   24
  -0.70 to   -0.52 | ##                                                 131
  -0.52 to   -0.35 | ##########                                         570
  -0.35 to   -0.17 | #############################                     1635
  -0.17 to   +0.00 | ################################################  2686
  +0.00 to   +0.18 | ################################################  2707
  +0.18 to   +0.35 | ###########################                       1545
  +0.35 to   +0.53 | ##########                                         572
  +0.53 to   +0.70 | ##                                                 113
  +0.70 to   +0.88 | #                                                   16
  +0.88 to   +1.05 | #                                                    1
  +1.05 to   +1.23 |                                                      0
  +1.23 to   +1.40 |                                                      0
  +1.40 to   +1.58 |                                                      0
  +1.58 to   +1.75 |                                                      0
  +1.75 to   +1.93 |                                                      0
  +1.93 to   +2.10 |                                                      0
  +2.10 to   +2.28 |                                                      0
  +2.28 to   +2.45 |                                                      0
  +2.45 to   +2.63 |                                                      0
  +2.63 to   +2.80 |                                                      0
  +2.80 to   +2.98 |                                                      0
  +2.98 to   +3.15 |                                                      0
  +3.15 to   +3.33 |                                                      0  <-- real +3.33
```

## Provenance

- Pre-registration: `214777f5762af8a2a59f5001cd5798a94818c542`
- Amendment 01: `50865fa0380db8be617c03e9f7d6d526b8712405`
- Spec: `4554c9f9d1b23957d90b2788fcbd4114af7a83e9`
- Code: `5a68341987cb8e2eb83d6edc266aa7774ba9ae21`
- Data: `data/raw/10_Industry_Portfolios.csv`, SHA-256 `921e2df7ae95355cf9030aebc8b2033c267f3153fb99a676ff912b3ea65d1ed3` (pin `921e2df7ae95355cf9030aebc8b2033c267f3153fb99a676ff912b3ea65d1ed3`), zip SHA-256 `cee051709825e60cc38f2aff01c2dec52265aa7ea4a1fefa023a2c8114a5166e`, downloaded 2026-11-06
- Random families: k = 10,000, numpy.random.default_rng(20261106), drawn in chunks of 100
- Run at (UTC): 2026-11-06T16:33:17+00:00, runtime 27.4 s
