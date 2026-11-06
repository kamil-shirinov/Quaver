"""Performance metrics, exactly as prereg/0001-faber-2010.md section 3 defines them.

Returns are monthly decimal fractions (0.01 is 1%). Every result is a decimal fraction too.
"""

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
MONTHS_PER_YEAR = 12
PAPER_RISK_FREE = 0.0381


def _monthly(returns: Sequence[float] | FloatArray) -> FloatArray:
    values = np.asarray(returns, dtype=np.float64)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("expected a non-empty one-dimensional series of monthly returns")
    return values


def cagr(returns: Sequence[float] | FloatArray) -> float:
    """Compound annual growth rate.

    Pre-registration, section 3: "CAGR: (product of (1 + r))^(12/T) - 1, for T months."
    """
    r = _monthly(returns)
    return float(np.prod(1.0 + r) ** (MONTHS_PER_YEAR / r.size) - 1.0)


def volatility(returns: Sequence[float] | FloatArray, ddof: int = 1) -> float:
    """Annualised standard deviation of monthly returns.

    Pre-registration, section 3: "Volatility: sample standard deviation (ddof = 1) of monthly
    returns, times sqrt(12)." Section 7: "Volatility with ddof = 0."
    """
    r = _monthly(returns)
    if r.size <= ddof:
        raise ValueError(f"volatility with ddof={ddof} needs more than {ddof} months")
    return float(np.std(r, ddof=ddof) * np.sqrt(MONTHS_PER_YEAR))


def sharpe_paper(returns: Sequence[float] | FloatArray, ddof: int = 1) -> float:
    """The paper's Sharpe ratio.

    Pre-registration, section 3: "Sharpe, the paper's formula, used only to compare with the
    paper: (CAGR - 3.81%) / volatility."
    """
    vol = volatility(returns, ddof)
    if vol == 0.0:
        raise ValueError("volatility is zero, so the Sharpe ratio is undefined")
    return (cagr(returns) - PAPER_RISK_FREE) / vol


def max_drawdown(returns: Sequence[float] | FloatArray) -> float:
    """The largest fall from a running peak, as a negative fraction (0.0 if there is none).

    Pre-registration, section 3: "Max drawdown: the largest fall from a running peak of
    month-end values, starting from 1."
    """
    r = _monthly(returns)
    values = np.concatenate(([1.0], np.cumprod(1.0 + r)))
    peaks = np.maximum.accumulate(values)
    return float(np.min(values / peaks - 1.0))


def calendar_year_returns(
    returns: Sequence[float] | FloatArray, months: Sequence[str]
) -> dict[int, float]:
    """Each calendar year's compounded return, keyed by year.

    Pre-registration, section 3: "Best and worst year: calendar-year compounded returns."
    The pre-registration does not define a partial year, so any year without all twelve
    months, January to December, is refused.
    """
    r = _monthly(returns)
    if len(months) != r.size:
        raise ValueError(f"{r.size} returns but {len(months)} months")
    by_year: dict[int, list[tuple[str, float]]] = {}
    for month, value in zip(months, r, strict=True):
        by_year.setdefault(int(month[:4]), []).append((month, float(value)))
    result: dict[int, float] = {}
    for year, entries in by_year.items():
        if [month for month, _ in entries] != [f"{year}-{m:02d}" for m in range(1, 13)]:
            raise ValueError(f"{year} is not a complete calendar year, January to December")
        result[year] = float(np.prod([1.0 + value for _, value in entries]) - 1.0)
    return result


def best_year(returns: Sequence[float] | FloatArray, months: Sequence[str]) -> float:
    """The highest calendar-year compounded return (section 3: "Best and worst year")."""
    return max(calendar_year_returns(returns, months).values())


def worst_year(returns: Sequence[float] | FloatArray, months: Sequence[str]) -> float:
    """The lowest calendar-year compounded return (section 3: "Best and worst year")."""
    return min(calendar_year_returns(returns, months).values())


def annualised_excess(
    returns: Sequence[float] | FloatArray, benchmark: Sequence[float] | FloatArray
) -> float:
    """Mean monthly excess return over the benchmark, times 12.

    Pre-registration, section 3: "Excess return: the monthly return minus the benchmark's in
    the same month. Annualised as the mean times 12."
    """
    r, b = _monthly(returns), _monthly(benchmark)
    if r.size != b.size:
        raise ValueError(f"{r.size} returns but {b.size} benchmark returns")
    return float(np.mean(r - b) * MONTHS_PER_YEAR)
