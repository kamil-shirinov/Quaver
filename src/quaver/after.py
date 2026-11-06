"""Test 2 (after publication), as prereg/0001-faber-2010.md section 5 and amendment 01 define it.

The family's annualised mean excess return over the benchmark, its Newey-West standard error,
a one-sided normal p-value and the verdict, plus the numbers reported without a verdict.
"""

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from quaver import metrics
from quaver.data import French10
from quaver.faber import (
    FAMILY_HOLDINGS,
    FAMILY_LOOKBACKS,
    FloatArray,
    benchmark_returns,
    family_returns,
    version_returns,
)

# Section 5: "Survived: p < 0.05."
ALPHA = 0.05
SURVIVED, WEAKENED, GONE = "survived", "weakened", "gone"


@dataclass(frozen=True)
class Test2:
    """The Test 2 statistic and verdict for one sample. Rates are decimal fractions per year."""

    first: str
    last: str
    months: int
    lags: int
    estimate: float
    standard_error: float
    z: float
    p: float
    verdict: str

    def to_json(self) -> dict[str, Any]:
        return {
            "first": self.first,
            "last": self.last,
            "months": self.months,
            "lags": self.lags,
            "estimate": self.estimate,
            "standard_error": self.standard_error,
            "z": self.z,
            "p": self.p,
            "verdict": self.verdict,
        }


def newey_west_lags(months: int) -> int:
    """Section 5: "Newey-West standard error with floor(4 x (T/100)^(2/9)) lags"."""
    if months < 1:
        raise ValueError(f"need at least one month, got {months}")
    return math.floor(4.0 * math.pow(months / 100.0, 2.0 / 9.0))


def newey_west_se(x: FloatArray, lags: int) -> float:
    """Newey-West standard error of the mean of ``x``.

    Bartlett weights 1 - l/(lags+1); every autocovariance is divided by T. With ``lags=0`` this
    is the plain standard error with the variance divided by T.
    """
    values = np.asarray(x, dtype=np.float64)
    if values.ndim != 1 or values.size < 2:
        raise ValueError("expected a one-dimensional series of at least two values")
    if not 0 <= lags < values.size:
        raise ValueError(f"lags must be from 0 to {values.size - 1}, got {lags}")
    t = values.size
    d = values - values.mean()
    long_run = float(d @ d) / t
    for lag in range(1, lags + 1):
        weight = 1.0 - lag / (lags + 1)
        long_run += 2.0 * weight * float(d[lag:] @ d[:-lag]) / t
    return math.sqrt(long_run / t)


def one_sided_p(z: float) -> float:
    """P(Z >= z) for a standard normal Z."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def verdict(estimate: float, p: float) -> str:
    """Section 5: survived if p < 0.05; weakened if above zero with p >= 0.05; else gone."""
    if estimate <= 0.0:
        return GONE
    return SURVIVED if p < ALPHA else WEAKENED


def family_excess(data: French10, first: str, last: str) -> FloatArray:
    """The family's monthly return minus the benchmark's, holding months ``first`` to ``last``."""
    return np.asarray(
        family_returns(data, first, last) - benchmark_returns(data, first, last),
        dtype=np.float64,
    )


def family_statistic(data: French10, first: str, last: str) -> float:
    """Section 5's statistic: the family's annualised mean excess return over the benchmark."""
    return metrics.annualised_excess(
        family_returns(data, first, last), benchmark_returns(data, first, last)
    )


def test2(data: French10, first: str, last: str) -> Test2:
    """Section 5's test over holding months ``first`` to ``last``."""
    excess = family_excess(data, first, last)
    lags = newey_west_lags(excess.size)
    estimate = family_statistic(data, first, last)
    se = metrics.MONTHS_PER_YEAR * newey_west_se(excess, lags)
    if se == 0.0:
        raise ValueError("the Newey-West standard error is zero, so the test is undefined")
    z = estimate / se
    p = one_sided_p(z)
    return Test2(
        first=first,
        last=last,
        months=excess.size,
        lags=lags,
        estimate=estimate,
        standard_error=se,
        z=z,
        p=p,
        verdict=verdict(estimate, p),
    )


def split_years(months: tuple[str, ...]) -> tuple[list[int], list[int]]:
    """Row indices in complete calendar years, and in partial years (amendment 01, item 1)."""
    by_year: dict[str, list[int]] = {}
    for k, month in enumerate(months):
        by_year.setdefault(month[:4], []).append(k)
    complete: list[int] = []
    partial: list[int] = []
    for year, rows in by_year.items():
        full = [months[k] for k in rows] == [f"{year}-{m:02d}" for m in range(1, 13)]
        (complete if full else partial).extend(rows)
    return complete, partial


def _partial_years(returns: FloatArray, months: tuple[str, ...]) -> list[dict[str, Any]]:
    _, partial = split_years(months)
    by_year: dict[str, list[int]] = {}
    for k in partial:
        by_year.setdefault(months[k][:4], []).append(k)
    return [
        {
            "year": int(year),
            "first": months[rows[0]],
            "last": months[rows[-1]],
            "months": len(rows),
            "return": float(np.prod(1.0 + returns[rows]) - 1.0),
        }
        for year, rows in by_year.items()
    ]


def _complete_years(returns: FloatArray, months: tuple[str, ...]) -> dict[int, float]:
    complete, _ = split_years(months)
    if not complete:
        return {}
    return metrics.calendar_year_returns(returns[complete], [months[k] for k in complete])


def describe(returns: FloatArray, months: tuple[str, ...], benchmark: FloatArray) -> dict[str, Any]:
    """Section 3's metrics for one series, plus its calendar years (amendment 01, item 1).

    CAGR, volatility, max drawdown and excess use every month. Calendar-year returns and the
    share of years beating the benchmark use complete years only; a partial year is listed
    separately.
    """
    years = _complete_years(returns, months)
    bench_years = _complete_years(benchmark, months)
    beat = sum(1 for year, value in years.items() if value > bench_years[year])
    return {
        "cagr": metrics.cagr(returns),
        "volatility": metrics.volatility(returns),
        "max_drawdown": metrics.max_drawdown(returns),
        "annualised_excess": metrics.annualised_excess(returns, benchmark),
        "calendar_years": {str(year): value for year, value in years.items()},
        "complete_years": len(years),
        "years_beating_benchmark": beat,
        "share_of_years_beating_benchmark": beat / len(years) if years else None,
        "partial_years": _partial_years(returns, months),
    }


def after_publication(
    data: French10, first: str, last: str, in_first: str, in_last: str
) -> dict[str, Any]:
    """Everything section 5 reports: the test, the in-sample statistic, the ratio, the versions."""
    after = test2(data, first, last)
    in_sample = family_statistic(data, in_first, in_last)
    bench = benchmark_returns(data, first, last)
    start = data.months.index(first)
    months: tuple[str, ...] = data.months[start : start + bench.size]
    versions = []
    for lookback in FAMILY_LOOKBACKS:
        for n in FAMILY_HOLDINGS:
            version = version_returns(data, lookback, n, first, last)
            versions.append(
                {"lookback": lookback, "top_n": n, **describe(version.returns, months, bench)}
            )
    return {
        "test2": after.to_json(),
        "in_sample": {"first": in_first, "last": in_last, "estimate": in_sample},
        "ratio_after_to_in_sample": after.estimate / in_sample if in_sample != 0.0 else None,
        "family": describe(family_returns(data, first, last), months, bench),
        "benchmark": describe(bench, months, bench),
        "versions": versions,
    }
