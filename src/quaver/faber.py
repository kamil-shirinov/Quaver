"""Faber (2010) US sector relative strength, as prereg/0001-faber-2010.md section 2 defines it.

Every holding decision for month t+1 is made from ``returns[: t + 1]``, a slice that ends at
month t, so no position can see its own holding month or anything later.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

from quaver.data import French10

FloatArray = npt.NDArray[np.float64]
Weights = Literal["reset", "drift"]

# Pre-registration, section 2: "In-sample: holding months 1928-01 to 2009-12."
IN_SAMPLE_FIRST = "1928-01"
IN_SAMPLE_LAST = "2009-12"
# Pre-registration, section 5: "the 15 versions with N in {1, 2, 3}, across all five lookbacks."
FAMILY_LOOKBACKS = (1, 3, 6, 9, 12)
FAMILY_HOLDINGS = (1, 2, 3)
# Pre-registration, section 2: "each lookback L in {1, 3, 6, 9, 12} months and each holding count
# N in {1, ..., 9}: 45 versions."
LOOKBACKS = (1, 3, 6, 9, 12)
HOLDINGS = (1, 2, 3, 4, 5, 6, 7, 8, 9)


@dataclass(frozen=True, eq=False)
class VersionReturns:
    """One version's holding months, monthly returns, chosen sectors and start-of-month weights.

    ``holdings[k]`` lists the sectors held in ``months[k]``, best-ranked first.
    ``weights[k]`` gives every sector's weight at the start of ``months[k]``.
    """

    months: tuple[str, ...]
    returns: FloatArray
    holdings: tuple[tuple[int, ...], ...]
    weights: FloatArray


def signal(returns: FloatArray, t: int, lookback: int) -> FloatArray:
    """Each sector's compounded return over months t-lookback+1 to t (row indices, inclusive).

    Pre-registration, section 2: "Signal at the end of month t: each sector's compounded
    return over months t-L+1 to t."
    """
    if lookback < 1:
        raise ValueError(f"lookback must be at least 1 month, got {lookback}")
    if not 0 <= t < len(returns):
        raise ValueError(f"month index {t} is outside the data (0 to {len(returns) - 1})")
    start = t - lookback + 1
    if start < 0:
        raise ValueError(
            f"a {lookback}-month signal at month index {t} needs {lookback} months, "
            f"only {t + 1} are available"
        )
    window = returns[start : t + 1]
    return np.asarray(np.prod(1.0 + window, axis=0) - 1.0, dtype=np.float64)


def select(scores: FloatArray, n: int) -> tuple[int, ...]:
    """Indices of the n highest scores, best first. Ties go to the sector listed first.

    Pre-registration, section 2: "hold the N highest-ranked sectors ... Ties go to the sector
    listed first in the file."
    """
    if not 1 <= n <= len(scores):
        raise ValueError(f"cannot hold {n} of {len(scores)} sectors")
    if not np.all(np.isfinite(scores)):
        raise ValueError("scores must be finite")
    # A stable sort keeps equal scores in file order.
    order = np.argsort(-scores, kind="stable")
    return tuple(int(i) for i in order[:n])


def history_start(first: str, lookback: int) -> str:
    """The earliest month of data a version needs to hold positions from ``first``."""
    index = int(first[:4]) * 12 + int(first[5:]) - 1 - lookback
    return f"{index // 12}-{index % 12 + 1:02d}"


def _span(data: French10, first: str, last: str) -> tuple[int, int]:
    indices = []
    for label, month in (("first", first), ("last", last)):
        if month not in data.months:
            raise ValueError(
                f"{label} month {month} is not in the data ({data.months[0]} to {data.months[-1]})"
            )
        indices.append(data.months.index(month))
    i, j = indices
    if j < i:
        raise ValueError(f"last month {last} is before first month {first}")
    return i, j


def _drift(
    previous: FloatArray,
    month_returns: FloatArray,
    previous_held: tuple[int, ...],
    held: tuple[int, ...],
) -> FloatArray:
    """Held sectors keep their drifted weights; dropped sectors' proceeds go equally to entrants."""
    grown = previous * (1.0 + month_returns)
    total = float(grown.sum())
    if total <= 0.0:
        raise ValueError("the portfolio lost everything, so drifted weights are undefined")
    drifted = grown / total
    kept = [s for s in held if s in previous_held]
    entrants = [s for s in held if s not in previous_held]
    dropped = [s for s in previous_held if s not in held]
    weights = np.zeros_like(drifted)
    weights[kept] = drifted[kept]
    if entrants:
        weights[entrants] = drifted[dropped].sum() / len(entrants)
    return weights


def version_returns(
    data: French10,
    lookback: int,
    n: int,
    first: str,
    last: str,
    weights: Weights = "reset",
) -> VersionReturns:
    """One version's monthly returns for holding months ``first`` to ``last`` ("YYYY-MM").

    Pre-registration, section 2: "During month t+1, hold the N highest-ranked sectors at equal
    weight, reset to equal weight every month."
    ``weights="drift"`` is the section 7 sensitivity check: "Weights left to drift between
    rebalances instead of being reset to equal." Held sectors keep their drifted weights, and a
    sector that drops out is sold with the proceeds split equally among the new entrants. The
    first holding month starts at equal weight.
    """
    if weights not in ("reset", "drift"):
        raise ValueError(f"weights must be 'reset' or 'drift', got {weights!r}")
    i, j = _span(data, first, last)
    if i < lookback:
        raise ValueError(
            f"holding month {first} with a {lookback}-month lookback needs data from "
            f"{history_start(first, lookback)}; the data starts {data.months[0]}"
        )
    n_sectors = data.returns.shape[1]
    out = np.empty(j - i + 1, dtype=np.float64)
    all_weights = np.zeros((j - i + 1, n_sectors), dtype=np.float64)
    holdings: list[tuple[int, ...]] = []
    for k, h in enumerate(range(i, j + 1)):
        # Only rows before the holding month h are passed in.
        held = select(signal(data.returns[:h], h - 1, lookback), n)
        if weights == "drift" and k > 0:
            w = _drift(all_weights[k - 1], data.returns[h - 1], holdings[-1], held)
        else:
            w = np.zeros(n_sectors, dtype=np.float64)
            w[list(held)] = 1.0 / n
        all_weights[k] = w
        out[k] = float(w @ data.returns[h])
        holdings.append(held)
    out.setflags(write=False)
    all_weights.setflags(write=False)
    return VersionReturns(
        months=data.months[i : j + 1],
        returns=out,
        holdings=tuple(holdings),
        weights=all_weights,
    )


def benchmark_returns(data: French10, first: str, last: str) -> FloatArray:
    """The equal-weighted average of all sectors each month.

    Pre-registration, section 2: "Benchmark: the equal-weighted average of all ten sectors,
    rebalanced monthly."
    """
    i, j = _span(data, first, last)
    return np.asarray(data.returns[i : j + 1].mean(axis=1), dtype=np.float64)


def family_returns(data: French10, first: str, last: str) -> FloatArray:
    """Each month, the equal-weighted average of the 15 family versions' returns.

    Pre-registration, section 5: "The family: the equal-weighted average of the 15 versions
    with N in {1, 2, 3}, across all five lookbacks."
    """
    versions = [
        version_returns(data, lookback, n, first, last).returns
        for lookback in FAMILY_LOOKBACKS
        for n in FAMILY_HOLDINGS
    ]
    return np.asarray(np.mean(versions, axis=0), dtype=np.float64)
