"""Test 2 (after publication) tests, on made-up data only.

``quaver.after`` is imported as a module: its ``test2`` function and ``Test2`` class would
otherwise be collected by pytest as tests.
"""

import math

import numpy as np
import pytest

from quaver import after, metrics
from quaver.data import French10
from quaver.faber import benchmark_returns, family_returns, version_returns

INDUSTRIES = tuple(f"S{k}" for k in range(10))


def months_from(year: int, n: int) -> tuple[str, ...]:
    return tuple(f"{year + k // 12}-{k % 12 + 1:02d}" for k in range(n))


def made_up(n: int = 60, seed: int = 3, start: int = 1999) -> French10:
    returns = np.random.default_rng(seed).uniform(-0.08, 0.10, size=(n, len(INDUSTRIES)))
    return French10(months=months_from(start, n), industries=INDUSTRIES, returns=returns)


# --- Newey-West ---------------------------------------------------------------------------------

# x = [1, 3, 2, 6]: mean 3, deviations [-2, 0, -1, 3], T = 4.
# gamma_0 = (4 + 0 + 1 + 9) / 4 = 3.5
# gamma_1 = (0*-2 + -1*0 + 3*-1) / 4 = -0.75
# gamma_2 = (-1*-2 + 3*0) / 4 = 0.5
HAND = np.array([1.0, 3.0, 2.0, 6.0])


@pytest.mark.parametrize(
    ("lags", "long_run"),
    [
        (0, 3.5),  # the plain standard error, variance divided by T
        (1, 3.5 + 2 * (1 / 2) * -0.75),  # = 2.75
        (2, 3.5 + 2 * ((2 / 3) * -0.75 + (1 / 3) * 0.5)),  # = 17/6
    ],
)
def test_newey_west_by_hand(lags: int, long_run: float) -> None:
    assert after.newey_west_se(HAND, lags) == pytest.approx(math.sqrt(long_run / 4), rel=1e-12)


def test_newey_west_lag_zero_is_the_plain_standard_error() -> None:
    x = np.random.default_rng(5).normal(size=50)
    plain = np.std(x, ddof=0) / math.sqrt(x.size)
    assert after.newey_west_se(x, 0) == pytest.approx(plain, rel=1e-12)


def test_newey_west_values_by_hand() -> None:
    assert after.newey_west_se(HAND, 1) == pytest.approx(math.sqrt(0.6875))
    assert after.newey_west_se(HAND, 2) == pytest.approx(math.sqrt(17 / 24))


@pytest.mark.parametrize(
    ("x", "lags", "message"),
    [
        (np.array([1.0]), 0, "at least two values"),
        (np.ones((2, 2)), 0, "one-dimensional"),
        (HAND, 4, "lags must be from 0 to 3"),
        (HAND, -1, "lags must be from 0 to 3"),
    ],
)
def test_newey_west_refuses_bad_input(x: np.ndarray, lags: int, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        after.newey_west_se(x, lags)


@pytest.mark.parametrize(("months", "lags"), [(201, 4), (100, 4), (984, 6), (21, 2), (1, 1)])
def test_lag_rule(months: int, lags: int) -> None:
    assert after.newey_west_lags(months) == lags


def test_lag_rule_for_201_months_by_hand() -> None:
    assert abs(4 * (201 / 100) ** (2 / 9) - 4.671) < 1e-3
    assert after.newey_west_lags(201) == 4


def test_lag_rule_needs_a_month() -> None:
    with pytest.raises(ValueError, match="at least one month"):
        after.newey_west_lags(0)


# --- p and verdict ------------------------------------------------------------------------------


def test_one_sided_p() -> None:
    assert after.one_sided_p(0.0) == pytest.approx(0.5)
    assert after.one_sided_p(1.6448536269514722) == pytest.approx(0.05, abs=1e-12)
    assert after.one_sided_p(-1.96) == pytest.approx(0.975, abs=1e-4)


@pytest.mark.parametrize(
    ("estimate", "p", "expected"),
    [
        (0.02, 0.049, "survived"),
        (0.02, 0.05, "weakened"),
        (0.0001, 0.49, "weakened"),
        (0.0, 0.5, "gone"),
        (-0.01, 0.8, "gone"),
    ],
)
def test_verdict(estimate: float, p: float, expected: str) -> None:
    assert after.verdict(estimate, p) == expected


# --- Test 2 -------------------------------------------------------------------------------------


def test_test2_by_its_parts() -> None:
    data = made_up()
    first, last = "2000-01", "2003-12"
    result = after.test2(data, first, last)
    excess = family_returns(data, first, last) - benchmark_returns(data, first, last)
    assert result.months == 48
    assert result.lags == after.newey_west_lags(48) == 3
    assert result.estimate == pytest.approx(12 * excess.mean())
    assert result.standard_error == pytest.approx(12 * after.newey_west_se(excess, 3))
    assert result.z == pytest.approx(result.estimate / result.standard_error)
    assert result.p == pytest.approx(after.one_sided_p(result.z))
    assert result.verdict == after.verdict(result.estimate, result.p)
    assert set(result.to_json()) == {
        "first",
        "last",
        "months",
        "lags",
        "estimate",
        "standard_error",
        "z",
        "p",
        "verdict",
    }


def test_test2_survives_when_one_sector_always_wins() -> None:
    data = made_up()
    returns = data.returns.copy()
    returns[:, 4] = 0.15
    winner = French10(months=data.months, industries=INDUSTRIES, returns=returns)
    result = after.test2(winner, "2000-01", "2003-12")
    assert result.estimate > 0
    assert result.verdict == "survived"


def test_test2_gone_when_the_winner_reverses() -> None:
    # Each month one sector earns +10% and the previous month's winner earns -10%.
    n = 60
    returns = np.full((n, 10), 0.01)
    for t in range(n):
        returns[t, t % 10] = 0.10
        returns[t, (t - 1) % 10] = -0.10
    data = French10(months=months_from(1999, n), industries=INDUSTRIES, returns=returns)
    result = after.test2(data, "2000-01", "2003-12")
    assert result.estimate < 0
    assert result.verdict == "gone"


def test_test2_refuses_a_zero_standard_error() -> None:
    # Identical sectors with exactly representable returns: the excess is exactly zero.
    returns = np.repeat(np.array([0.5, -0.25, 0.125, 0.0625, -0.5] * 12)[:, None], 10, axis=1)
    data = French10(months=months_from(1999, 60), industries=INDUSTRIES, returns=returns)
    with pytest.raises(ValueError, match="standard error is zero"):
        after.test2(data, "2000-01", "2003-12")


# --- Calendar years and the details -------------------------------------------------------------


def test_split_years() -> None:
    months = (*months_from(2009, 24)[6:], "2011-01", "2011-02")
    complete, partial = after.split_years(months)
    assert [months[k] for k in complete] == list(months_from(2010, 12))
    assert [months[k] for k in partial] == [*months_from(2009, 12)[6:], "2011-01", "2011-02"]


def test_describe_uses_complete_years_only() -> None:
    data = made_up(n=33, start=2009)  # 2009-01 to 2011-09
    months = data.months[12:]  # 2010-01 to 2011-09
    r = data.returns[12:, 0]
    bench = data.returns[12:].mean(axis=1)
    d = after.describe(r, months, bench)
    assert d["cagr"] == pytest.approx(metrics.cagr(r))
    assert d["volatility"] == pytest.approx(metrics.volatility(r))
    assert d["max_drawdown"] == pytest.approx(metrics.max_drawdown(r))
    assert d["annualised_excess"] == pytest.approx(metrics.annualised_excess(r, bench))
    assert list(d["calendar_years"]) == ["2010"]
    assert d["calendar_years"]["2010"] == pytest.approx(float(np.prod(1 + r[:12]) - 1))
    assert d["complete_years"] == 1
    beat = int(np.prod(1 + r[:12]) > np.prod(1 + bench[:12]))
    assert d["years_beating_benchmark"] == beat
    assert d["share_of_years_beating_benchmark"] == beat
    assert d["partial_years"] == [
        {
            "year": 2011,
            "first": "2011-01",
            "last": "2011-09",
            "months": 9,
            "return": pytest.approx(float(np.prod(1 + r[12:]) - 1)),
        }
    ]


def test_describe_without_a_complete_year() -> None:
    r = np.array([0.01, -0.02, 0.03])
    d = after.describe(r, ("2026-01", "2026-02", "2026-03"), r)
    assert d["calendar_years"] == {}
    assert d["complete_years"] == 0
    assert d["share_of_years_beating_benchmark"] is None
    assert d["partial_years"][0]["months"] == 3


def test_after_publication_details() -> None:
    data = made_up(n=72, start=1999)  # 1999-01 to 2004-12
    details = after.after_publication(data, "2003-01", "2004-09", "2000-01", "2002-12")
    assert details["test2"] == after.test2(data, "2003-01", "2004-09").to_json()
    in_sample = after.family_statistic(data, "2000-01", "2002-12")
    assert details["in_sample"] == {"first": "2000-01", "last": "2002-12", "estimate": in_sample}
    assert details["ratio_after_to_in_sample"] == pytest.approx(
        details["test2"]["estimate"] / in_sample
    )
    assert [(v["lookback"], v["top_n"]) for v in details["versions"]] == [
        (lb, n) for lb in (1, 3, 6, 9, 12) for n in (1, 2, 3)
    ]
    bench = benchmark_returns(data, "2003-01", "2004-09")
    for v in details["versions"]:
        r = version_returns(data, v["lookback"], v["top_n"], "2003-01", "2004-09").returns
        assert v["cagr"] == pytest.approx(metrics.cagr(r))
        assert v["annualised_excess"] == pytest.approx(metrics.annualised_excess(r, bench))
        assert list(v["calendar_years"]) == ["2003"]
        assert v["partial_years"][0]["first"] == "2004-01"
    assert details["benchmark"]["annualised_excess"] == 0.0
    assert details["family"]["annualised_excess"] == pytest.approx(details["test2"]["estimate"])


def test_ratio_is_none_when_the_in_sample_statistic_is_zero() -> None:
    # Identical sectors in-sample (the statistic is exactly zero), varied ones after.
    n = 72
    returns = np.random.default_rng(9).uniform(-0.08, 0.10, size=(n, 10))
    returns[:48] = np.array([0.5, -0.25, 0.125, 0.0625] * 12)[:, None]
    data = French10(months=months_from(1999, n), industries=INDUSTRIES, returns=returns)
    assert after.family_statistic(data, "2000-01", "2002-12") == 0.0
    details = after.after_publication(data, "2003-01", "2004-12", "2000-01", "2002-12")
    assert details["ratio_after_to_in_sample"] is None


# --- Complete years only (amendment 02, point 2) ------------------------------------------------


def without_verdict(result: after.Test2) -> dict[str, object]:
    figure = result.to_json()
    del figure["verdict"]
    return figure


def test_complete_years_figure_drops_a_partial_last_year() -> None:
    data = made_up(n=72, start=1999)  # 1999-01 to 2004-12
    figure = after.complete_years_figure(data, "2003-01", "2004-09")
    assert figure == without_verdict(after.test2(data, "2003-01", "2003-12"))
    assert figure is not None
    assert "verdict" not in figure
    assert (figure["first"], figure["last"], figure["months"]) == ("2003-01", "2003-12", 12)


def test_complete_years_figure_drops_a_partial_first_year() -> None:
    data = made_up(n=72, start=1999)
    figure = after.complete_years_figure(data, "2002-04", "2004-12")
    assert figure == without_verdict(after.test2(data, "2003-01", "2004-12"))


def test_complete_years_figure_of_complete_years_is_test2_without_a_verdict() -> None:
    data = made_up(n=72, start=1999)
    figure = after.complete_years_figure(data, "2002-01", "2004-12")
    assert figure == without_verdict(after.test2(data, "2002-01", "2004-12"))


def test_complete_years_figure_without_a_complete_year() -> None:
    data = made_up(n=72, start=1999)
    assert after.complete_years_figure(data, "2003-02", "2003-11") is None


def test_after_publication_reports_the_complete_years_figure() -> None:
    data = made_up(n=72, start=1999)
    details = after.after_publication(data, "2003-01", "2004-09", "2000-01", "2002-12")
    assert details["complete_years"] == after.complete_years_figure(data, "2003-01", "2004-09")
    assert details["complete_years"]["last"] == "2003-12"
    # The main test still uses every month, the partial year included (amendment 02, point 1).
    assert details["test2"]["last"] == "2004-09"
    assert details["test2"]["months"] == 21
