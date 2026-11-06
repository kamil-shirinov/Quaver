"""Test 3 (luck), as prereg/0001-faber-2010.md section 6 defines it.

A random family has the real family's 15 versions, in the same order (lookbacks outer, holding
counts inner), so version v holds FAMILY_HOLDINGS[v % 3] sectors. Each month each version
holds that many sectors picked uniformly at random without replacement, at equal weight; the
family's return is the average of its 15 versions. Its statistic is Test 2's: the annualised
mean excess return over the benchmark.

Draws are reproducible and prefix-stable: each call starts its own generator from ``seed``,
and families are drawn in chunks of 100 in order, so the first 100 families do not depend on k.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from quaver.after import family_statistic
from quaver.data import French10
from quaver.faber import FAMILY_HOLDINGS, FAMILY_LOOKBACKS, FloatArray, benchmark_returns
from quaver.metrics import MONTHS_PER_YEAR

# Section 6: "Draw 10,000 random families with numpy.random.default_rng(20261106)."
K = 10_000
SEED = 20261106
CHUNK = 100
# Section 6: "beats luck" if p < 0.05, otherwise "not distinguishable from luck".
ALPHA = 0.05
BEATS, NOT_DISTINGUISHABLE = "beats luck", "not distinguishable from luck"
# The holding count of each of the 15 versions, in the real family's order.
HOLDINGS: npt.NDArray[np.intp] = np.array(
    [n for _ in FAMILY_LOOKBACKS for n in FAMILY_HOLDINGS], dtype=np.intp
)


@dataclass(frozen=True)
class Test3:
    """The real statistic, every random family's, p and the verdict for one sample."""

    first: str
    last: str
    months: int
    real: float
    randoms: FloatArray
    p: float
    verdict: str

    def percentile(self, q: float) -> float:
        return float(np.percentile(self.randoms, q))

    def to_json(self) -> dict[str, Any]:
        return {
            "first": self.first,
            "last": self.last,
            "months": self.months,
            "real": self.real,
            "p": self.p,
            "verdict": self.verdict,
            "random_families": len(self.randoms),
            "random_at_least_real": int(np.sum(self.randoms >= self.real)),
            "percentiles": {str(q): self.percentile(q) for q in (5, 50, 95)},
            "randoms": [float(v) for v in self.randoms],
        }


def random_family_stats(
    data: French10, first: str, last: str, k: int = K, seed: int = SEED
) -> FloatArray:
    """Each of ``k`` random families' annualised mean excess return over the benchmark."""
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")
    bench = benchmark_returns(data, first, last)
    start = data.months.index(first)
    returns = data.returns[start : start + bench.size]
    months, sectors = returns.shape
    most = int(HOLDINGS.max())
    rows = np.arange(months)[:, None]
    pick = (HOLDINGS - 1)[None, :, None, None]
    rng = np.random.default_rng(seed)
    out = np.empty(k, dtype=np.float64)
    for begin in range(0, k, CHUNK):
        size = min(CHUNK, k - begin)
        draws = rng.random((size, HOLDINGS.size, months, sectors))
        # Each version holds the sectors with the smallest numbers.
        order = np.argsort(draws, axis=-1, kind="stable")[..., :most]
        held = np.cumsum(returns[rows, order], axis=-1)
        versions = np.take_along_axis(held, pick, axis=-1)[..., 0] / HOLDINGS[None, :, None]
        family = versions.mean(axis=1)
        out[begin : begin + size] = (family - bench).mean(axis=1) * MONTHS_PER_YEAR
    return out


def p_value(real: float, randoms: FloatArray) -> float:
    """Section 6: (1 + the number of random families at least the real one) / (1 + their count)."""
    values = np.asarray(randoms, dtype=np.float64)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("expected a non-empty one-dimensional array of random statistics")
    return (1 + int(np.sum(values >= real))) / (1 + values.size)


def verdict(p: float) -> str:
    return BEATS if p < ALPHA else NOT_DISTINGUISHABLE


def test3(data: French10, first: str, last: str, k: int = K, seed: int = SEED) -> Test3:
    """Section 6's test over holding months ``first`` to ``last``."""
    real = family_statistic(data, first, last)
    randoms = random_family_stats(data, first, last, k, seed)
    p = p_value(real, randoms)
    return Test3(
        first=first,
        last=last,
        months=int(benchmark_returns(data, first, last).size),
        real=real,
        randoms=randoms,
        p=p,
        verdict=verdict(p),
    )
