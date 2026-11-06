"""Metric tests against hand-computed values. All data here is made up."""

import math

import pytest

from quaver.metrics import (
    PAPER_RISK_FREE,
    annualised_excess,
    best_year,
    cagr,
    calendar_year_returns,
    max_drawdown,
    sharpe_paper,
    volatility,
    worst_year,
)


def year(y: int) -> list[str]:
    return [f"{y}-{m:02d}" for m in range(1, 13)]


def test_cagr() -> None:
    # 1.1 * 1.1 = 1.21 over 24 months: 1.21 ** (12 / 24) - 1 = 0.10.
    assert cagr([0.10, 0.10] + [0.0] * 22) == pytest.approx(0.10)
    # 1.21 over 6 months: 1.21 ** 2 - 1 = 0.4641.
    assert cagr([0.21, 0.0, 0.0, 0.0, 0.0, 0.0]) == pytest.approx(0.4641)
    # Exactly twelve months: the compounded return itself, 1.1 * 0.9 - 1 = -0.01.
    assert cagr([0.10, -0.10] + [0.0] * 10) == pytest.approx(-0.01)


def test_volatility_sample_and_population() -> None:
    # Mean 0.02, deviations +-0.01. ddof=1: variance 0.0002/1; ddof=0: 0.0002/2.
    assert volatility([0.01, 0.03]) == pytest.approx(math.sqrt(0.0002) * math.sqrt(12))
    assert volatility([0.01, 0.03], ddof=0) == pytest.approx(0.01 * math.sqrt(12))
    # Mean 0.03, deviations -0.02, 0, +0.02: ddof=1 variance 0.0008/2 = 0.0004.
    assert volatility([0.01, 0.03, 0.05]) == pytest.approx(0.02 * math.sqrt(12))


def test_volatility_needs_more_months_than_ddof() -> None:
    with pytest.raises(ValueError, match="ddof=1 needs more than 1 month"):
        volatility([0.01])
    assert volatility([0.01], ddof=0) == 0.0


def test_sharpe_paper() -> None:
    returns = [0.10, 0.10] + [0.0] * 22
    # CAGR 0.10. Mean 0.2/24 = 1/120; sample variance (0.02 - 24 / 120**2) / 23.
    vol = math.sqrt((0.02 - 24 / 120**2) / 23) * math.sqrt(12)
    assert vol == pytest.approx(0.0978020, abs=1e-7)
    assert PAPER_RISK_FREE == 0.0381
    assert sharpe_paper(returns) == pytest.approx((0.10 - 0.0381) / vol)
    assert sharpe_paper(returns) == pytest.approx(0.63291, abs=1e-5)
    vol0 = math.sqrt((0.02 - 24 / 120**2) / 24) * math.sqrt(12)
    assert sharpe_paper(returns, ddof=0) == pytest.approx((0.10 - 0.0381) / vol0)


def test_sharpe_with_zero_volatility_is_refused() -> None:
    with pytest.raises(ValueError, match="volatility is zero"):
        sharpe_paper([0.01, 0.01, 0.01])


def test_max_drawdown_counts_a_fall_from_the_very_start() -> None:
    # Values 0.5, 1.0, 0.8, 1.0 from a start of 1: the worst fall is 1 -> 0.5.
    # Without the starting value the answer would be 1.0 -> 0.8, only -0.2.
    assert max_drawdown([-0.5, 1.0, -0.2, 0.25]) == pytest.approx(-0.5)


def test_max_drawdown_from_a_later_peak() -> None:
    # Values 1.5, 0.9, 0.99: 0.9 / 1.5 - 1 = -0.4.
    assert max_drawdown([0.5, -0.4, 0.1]) == pytest.approx(-0.4)


def test_max_drawdown_without_a_fall_is_zero() -> None:
    assert max_drawdown([0.01, 0.02, 0.0]) == 0.0


def test_calendar_years_compound_and_best_and_worst_year() -> None:
    months = year(2000) + year(2001)
    # 2000: 1.1 * 1.1 = 1.21 -> 0.21 (summing would give 0.20).
    # 2001: 0.9 * 0.8 = 0.72 -> -0.28 (summing would give -0.30).
    returns = [0.10, 0.0, 0.0, 0.10] + [0.0] * 8 + [-0.10] + [0.0] * 10 + [-0.20]
    by_year = calendar_year_returns(returns, months)
    assert list(by_year) == [2000, 2001]
    assert by_year[2000] == pytest.approx(0.21)
    assert by_year[2001] == pytest.approx(-0.28)
    assert best_year(returns, months) == pytest.approx(0.21)
    assert worst_year(returns, months) == pytest.approx(-0.28)


def test_partial_calendar_year_is_refused() -> None:
    months = year(2025) + [f"2026-{m:02d}" for m in range(1, 10)]
    with pytest.raises(ValueError, match="2026 is not a complete calendar year"):
        calendar_year_returns([0.0] * 21, months)
    with pytest.raises(ValueError, match="2025 is not a complete calendar year"):
        best_year([0.0] * 12, [*year(2025)[1:], "2026-01"])


def test_calendar_years_need_one_month_per_return() -> None:
    with pytest.raises(ValueError, match="12 returns but 11 months"):
        calendar_year_returns([0.0] * 12, year(2000)[:11])


def test_annualised_excess() -> None:
    # Differences 0.01, 0.00, 0.02: mean 0.01, times 12 = 0.12.
    assert annualised_excess([0.02, 0.01, 0.03], [0.01, 0.01, 0.01]) == pytest.approx(0.12)


def test_annualised_excess_needs_matching_lengths() -> None:
    with pytest.raises(ValueError, match="3 returns but 2 benchmark returns"):
        annualised_excess([0.02, 0.01, 0.03], [0.01, 0.01])


@pytest.mark.parametrize("bad", [[], [[0.01, 0.02]]])
def test_metrics_need_a_flat_non_empty_series(bad: list[float]) -> None:
    with pytest.raises(ValueError, match="non-empty one-dimensional"):
        cagr(bad)
