"""Faber (2010) strategy tests. All data here is made up; the real file is never read."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from quaver.data import French10
from quaver.faber import (
    FAMILY_HOLDINGS,
    FAMILY_LOOKBACKS,
    IN_SAMPLE_FIRST,
    IN_SAMPLE_LAST,
    FloatArray,
    Weights,
    benchmark_returns,
    family_returns,
    history_start,
    select,
    signal,
    version_returns,
)

WEIGHTS: tuple[Weights, ...] = ("reset", "drift")


def months_from(start: str, count: int) -> tuple[str, ...]:
    base = int(start[:4]) * 12 + int(start[5:]) - 1
    return tuple(f"{(base + k) // 12}-{(base + k) % 12 + 1:02d}" for k in range(count))


def make_data(returns: FloatArray | list[list[float]], start: str = "2000-01") -> French10:
    values = np.array(returns, dtype=np.float64)
    names = tuple(f"S{k}" for k in range(values.shape[1]))
    return French10(months=months_from(start, len(values)), industries=names, returns=values)


def random_returns(seed: int, n_months: int, n_sectors: int) -> FloatArray:
    return np.random.default_rng(seed).uniform(-0.15, 0.15, size=(n_months, n_sectors))


# --- Golden example: three sectors A, B, C, eight months, 2-month lookback ---------------------

GOLDEN = np.array(
    [
        #  A      B      C
        [0.10, 0.00, -0.10],  # 2000-01  (row 0)
        [0.00, 0.20, 0.10],  # 2000-02  (row 1)
        [-0.10, 0.10, 0.20],  # 2000-03  (row 2)
        [0.20, -0.10, 0.00],  # 2000-04  (row 3)
        [0.10, 0.10, -0.20],  # 2000-05  (row 4)
        [-0.20, 0.30, 0.10],  # 2000-06  (row 5)
        [0.10, -0.10, 0.10],  # 2000-07  (row 6)
        [0.00, 0.10, -0.10],  # 2000-08  (row 7)
    ]
)
A, B, C = 0, 1, 2

# Signal at the end of row t over rows t-1 and t, with the full ranking it gives.
GOLDEN_SIGNALS = {
    1: ([1.1 * 1.0 - 1, 1.0 * 1.2 - 1, 0.9 * 1.1 - 1], (B, A, C)),  # 0.10, 0.20, -0.01
    2: ([1.0 * 0.9 - 1, 1.2 * 1.1 - 1, 1.1 * 1.2 - 1], (B, C, A)),  # -0.10, 0.32, 0.32: tie B=C
    3: ([0.9 * 1.2 - 1, 1.1 * 0.9 - 1, 1.2 * 1.0 - 1], (C, A, B)),  # 0.08, -0.01, 0.20
    4: ([1.2 * 1.1 - 1, 0.9 * 1.1 - 1, 1.0 * 0.8 - 1], (A, B, C)),  # 0.32, -0.01, -0.20
    5: ([1.1 * 0.8 - 1, 1.1 * 1.3 - 1, 0.8 * 1.1 - 1], (B, A, C)),  # -0.12, 0.43, -0.12: tie A=C
    6: ([0.8 * 1.1 - 1, 1.3 * 0.9 - 1, 1.1 * 1.1 - 1], (C, B, A)),  # -0.12, 0.17, 0.21
}


@pytest.mark.parametrize("t", sorted(GOLDEN_SIGNALS))
def test_golden_signals_and_rankings(t: int) -> None:
    expected, ranking = GOLDEN_SIGNALS[t]
    scores = signal(GOLDEN, t, 2)
    np.testing.assert_allclose(scores, expected, atol=1e-12)
    assert select(scores, 3) == ranking


def test_golden_one_sector() -> None:
    result = version_returns(make_data(GOLDEN), 2, 1, "2000-03", "2000-08")
    assert result.months == ("2000-03", "2000-04", "2000-05", "2000-06", "2000-07", "2000-08")
    # Each month holds the top sector of the previous month's signal.
    assert result.holdings == ((B,), (B,), (C,), (A,), (B,), (C,))
    # Its own return that month: B in 03, B in 04, C in 05, A in 06, B in 07, C in 08.
    np.testing.assert_allclose(result.returns, [0.10, -0.10, -0.20, -0.20, -0.10, -0.10])


def test_golden_two_sectors() -> None:
    result = version_returns(make_data(GOLDEN), 2, 2, "2000-03", "2000-08")
    assert result.holdings == ((B, A), (B, C), (C, A), (A, B), (B, A), (C, B))
    expected = [
        (0.10 + -0.10) / 2,  # 03: B, A
        (-0.10 + 0.00) / 2,  # 04: B, C
        (-0.20 + 0.10) / 2,  # 05: C, A
        (-0.20 + 0.30) / 2,  # 06: A, B
        (-0.10 + 0.10) / 2,  # 07: B, A
        (0.10 + -0.10) / 2,  # 08: C, B
    ]
    np.testing.assert_allclose(result.returns, expected, atol=1e-12)
    np.testing.assert_allclose(result.weights[0], [0.5, 0.5, 0.0])


def test_golden_benchmark() -> None:
    result = benchmark_returns(make_data(GOLDEN), "2000-03", "2000-08")
    expected = [0.20 / 3, 0.10 / 3, 0.0, 0.20 / 3, 0.10 / 3, 0.0]
    np.testing.assert_allclose(result, expected, atol=1e-12)


# --- Ties ----------------------------------------------------------------------------------------


def test_ties_go_to_the_sector_listed_first() -> None:
    assert select(np.array([0.1, 0.3, 0.3, 0.3]), 2) == (1, 2)
    assert select(np.array([0.5, 0.5, 0.5]), 1) == (0,)
    assert select(np.array([-0.0, 0.0]), 1) == (0,)


def test_all_equal_sectors_hold_the_first_listed() -> None:
    data = make_data(np.full((6, 4), 0.01))
    result = version_returns(data, 3, 2, "2000-04", "2000-06")
    assert result.holdings == ((0, 1), (0, 1), (0, 1))


# --- No lookahead, a: perturb every return from month t+1 onward ---------------------------------


@pytest.mark.parametrize("weights", WEIGHTS)
@pytest.mark.parametrize("lookback", FAMILY_LOOKBACKS)
def test_perturbing_the_future_never_changes_earlier_holdings(
    lookback: int, weights: Weights
) -> None:
    rng = np.random.default_rng(lookback)
    original = random_returns(seed=100 + lookback, n_months=60, n_sectors=5)
    data = make_data(original)
    first, last = data.months[lookback], data.months[-1]
    later_holdings_changed = False
    for n in (1, 2, 3):
        base = version_returns(data, lookback, n, first, last, weights)
        for t in range(lookback - 1, 59):
            perturbed = original.copy()
            perturbed[t + 1 :] = rng.uniform(-0.15, 0.15, size=perturbed[t + 1 :].shape)
            other = version_returns(make_data(perturbed), lookback, n, first, last, weights)
            # Holding months up to t+1 have positions k = 0 .. t+1-lookback.
            keep = t + 2 - lookback
            assert other.holdings[:keep] == base.holdings[:keep], (n, t)
            np.testing.assert_array_equal(other.weights[:keep], base.weights[:keep])
            np.testing.assert_array_equal(other.returns[: keep - 1], base.returns[: keep - 1])
            later_holdings_changed |= other.holdings[keep:] != base.holdings[keep:]
    # The perturbation is strong enough that the test could fail.
    assert later_holdings_changed


# --- No lookahead, b: the best sector next month always has the worst past return -----------------


def trap_returns(lookback: int, n_months: int = 48, n_sectors: int = 5) -> FloatArray:
    """Each month, the sector with the worst signal so far gets +30%, beating every other."""
    returns = random_returns(seed=200 + lookback, n_months=n_months, n_sectors=n_sectors)
    returns *= 0.3  # ordinary months stay within +-4.5%
    for m in range(lookback, n_months):
        worst = int(np.argmin(signal(returns[:m], m - 1, lookback)))
        returns[m, worst] = 0.30
    return returns


@pytest.mark.parametrize("weights", WEIGHTS)
@pytest.mark.parametrize("lookback", FAMILY_LOOKBACKS)
def test_never_holds_the_trap_sector_in_its_best_month(lookback: int, weights: Weights) -> None:
    returns = trap_returns(lookback)
    data = make_data(returns)
    for n in range(1, returns.shape[1]):
        result = version_returns(data, lookback, n, data.months[lookback], data.months[-1], weights)
        for k, held in enumerate(result.holdings):
            month_returns = returns[lookback + k]
            best = int(np.argmax(month_returns))
            assert month_returns[best] == 0.30
            assert best not in held, (n, result.months[k])
            # A strategy that peeked at the holding month would have held it.
            assert select(month_returns, 1) == (best,)


# --- No lookahead, c: property-based --------------------------------------------------------------

RETURN = st.floats(min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False)


@settings(max_examples=300, deadline=None)
@given(draw=st.data())
def test_holdings_for_next_month_depend_only_on_rows_up_to_t(draw: st.DataObject) -> None:
    n_sectors = draw.draw(st.integers(2, 6), label="sectors")
    lookback = draw.draw(st.integers(1, 12), label="lookback")
    n_months = draw.draw(st.integers(lookback + 1, lookback + 24), label="months")
    n = draw.draw(st.integers(1, n_sectors), label="n")
    weights = draw.draw(st.sampled_from(WEIGHTS), label="weights")
    t = draw.draw(st.integers(lookback - 1, n_months - 2), label="t")
    past = draw.draw(arrays(np.float64, (n_months, n_sectors), elements=RETURN), label="data")
    future = draw.draw(
        arrays(np.float64, (n_months - t - 1, n_sectors), elements=RETURN), label="future"
    )
    swapped = np.concatenate([past[: t + 1], future])

    a, b = make_data(past), make_data(swapped)
    first, last = a.months[lookback], a.months[-1]
    one = version_returns(a, lookback, n, first, last, weights)
    two = version_returns(b, lookback, n, first, last, weights)
    k = t + 1 - lookback  # position of holding month t+1
    assert one.holdings[: k + 1] == two.holdings[: k + 1]
    np.testing.assert_array_equal(one.weights[: k + 1], two.weights[: k + 1])
    # And month t+1's holdings are exactly the ranking of the signal at t.
    assert one.holdings[k] == select(signal(past[: t + 1], t, lookback), n)


# --- Boundaries ----------------------------------------------------------------------------------


def test_first_holding_month_needs_lookback_months_of_history() -> None:
    data = make_data(random_returns(seed=1, n_months=12, n_sectors=3))  # from 2000-01
    with pytest.raises(ValueError, match=r"2000-03 .* 3-month lookback needs data from 1999-12"):
        version_returns(data, 3, 1, "2000-03", "2000-12")
    assert len(version_returns(data, 3, 1, "2000-04", "2000-12").returns) == 9


def test_in_sample_needs_data_from_1927_01_for_the_12_month_lookback() -> None:
    assert (IN_SAMPLE_FIRST, IN_SAMPLE_LAST) == ("1928-01", "2009-12")
    assert history_start(IN_SAMPLE_FIRST, 12) == "1927-01"
    n_months = (2009 - 1927 + 1) * 12
    enough = make_data(random_returns(seed=2, n_months=n_months, n_sectors=4), start="1927-01")
    result = version_returns(enough, 12, 1, IN_SAMPLE_FIRST, IN_SAMPLE_LAST)
    assert len(result.returns) == (2009 - 1928 + 1) * 12
    assert result.months[0] == "1928-01"
    short = make_data(enough.returns[1:], start="1927-02")
    with pytest.raises(ValueError, match="needs data from 1927-01; the data starts 1927-02"):
        version_returns(short, 12, 1, IN_SAMPLE_FIRST, IN_SAMPLE_LAST)
    with pytest.raises(ValueError, match="needs data from 1927-01"):
        family_returns(short, IN_SAMPLE_FIRST, IN_SAMPLE_LAST)
    assert len(version_returns(short, 9, 1, IN_SAMPLE_FIRST, IN_SAMPLE_LAST).returns) == 984


def test_history_start_crosses_year_boundaries() -> None:
    assert history_start("2000-01", 1) == "1999-12"
    assert history_start("2000-12", 12) == "1999-12"
    assert history_start("2010-01", 13) == "2008-12"


def test_months_must_be_in_the_data_and_in_order() -> None:
    data = make_data(GOLDEN)
    with pytest.raises(ValueError, match="first month 1999-12 is not in the data"):
        version_returns(data, 1, 1, "1999-12", "2000-08")
    with pytest.raises(ValueError, match="last month 2000-09 is not in the data"):
        benchmark_returns(data, "2000-03", "2000-09")
    with pytest.raises(ValueError, match="last month 2000-04 is before first month 2000-05"):
        version_returns(data, 1, 1, "2000-05", "2000-04")


def test_signal_rejects_bad_arguments() -> None:
    with pytest.raises(ValueError, match="at least 1 month"):
        signal(GOLDEN, 3, 0)
    with pytest.raises(ValueError, match="outside the data"):
        signal(GOLDEN, 8, 1)
    with pytest.raises(ValueError, match="outside the data"):
        signal(GOLDEN, -1, 1)
    with pytest.raises(ValueError, match="needs 3 months, only 2 are available"):
        signal(GOLDEN, 1, 3)
    np.testing.assert_allclose(signal(GOLDEN, 0, 1), GOLDEN[0])


def test_select_rejects_bad_arguments() -> None:
    with pytest.raises(ValueError, match="cannot hold 0 of 3"):
        select(np.array([0.1, 0.2, 0.3]), 0)
    with pytest.raises(ValueError, match="cannot hold 4 of 3"):
        select(np.array([0.1, 0.2, 0.3]), 4)
    with pytest.raises(ValueError, match="finite"):
        select(np.array([0.1, np.nan, 0.3]), 1)


def test_unknown_weights_rule_is_refused() -> None:
    with pytest.raises(ValueError, match="'reset' or 'drift'"):
        version_returns(make_data(GOLDEN), 1, 1, "2000-02", "2000-08", "equal")  # type: ignore[arg-type]


# --- Reset vs drift ------------------------------------------------------------------------------

RESET_VS_DRIFT = [
    #  A     B      C
    [0.10, 0.05, 0.00],  # 2000-01: signal A > B > C, so hold A, B in 02
    [0.50, 0.00, -0.10],  # 2000-02: A, B again in 03; drift moves A to 0.75/1.25 = 0.6
    [0.00, -0.50, 1.00],  # 2000-03: C > A > B, so hold C, A in 04; B is sold
    [0.10, 0.00, 0.20],  # 2000-04
]


def test_reset_and_drift_give_the_expected_different_weights() -> None:
    data = make_data(RESET_VS_DRIFT)
    reset = version_returns(data, 1, 2, "2000-02", "2000-04", "reset")
    drift = version_returns(data, 1, 2, "2000-02", "2000-04", "drift")
    assert reset.holdings == drift.holdings == ((A, B), (A, B), (C, A))

    np.testing.assert_allclose(reset.weights, [[0.5, 0.5, 0.0], [0.5, 0.5, 0.0], [0.5, 0.0, 0.5]])
    np.testing.assert_allclose(reset.returns, [0.25, (0.00 - 0.50) / 2, (0.10 + 0.20) / 2])

    # 03: A 0.5 * 1.5 = 0.75, B 0.5 * 1.0 = 0.5, of 1.25 -> A 0.6, B 0.4.
    # 04: A 0.6 * 1.0 = 0.6, B 0.4 * 0.5 = 0.2, of 0.8 -> A 0.75, B 0.25; B's 0.25 goes to C.
    np.testing.assert_allclose(drift.weights, [[0.5, 0.5, 0.0], [0.6, 0.4, 0.0], [0.75, 0.0, 0.25]])
    np.testing.assert_allclose(
        drift.returns, [0.25, 0.6 * 0.00 + 0.4 * -0.50, 0.75 * 0.10 + 0.25 * 0.20]
    )


def test_drift_splits_proceeds_equally_among_new_entrants() -> None:
    data = make_data(
        [
            # A     B     C      D     E
            [0.40, 0.30, 0.20, 0.10, 0.00],  # 2000-01: hold A, B, C in 02
            [0.50, 0.00, -0.50, 0.60, 0.70],  # 2000-02: hold E, D, A in 03
            [0.10, 0.00, 0.00, 0.20, -0.20],  # 2000-03
        ]
    )
    drift = version_returns(data, 1, 3, "2000-02", "2000-03", "drift")
    assert drift.holdings == ((0, 1, 2), (4, 3, 0))
    # After 02: A 1/3 * 1.5 = 0.5, B 1/3, C 1/6, of 1.0. B and C's 0.5 is split over D and E.
    np.testing.assert_allclose(drift.weights[1], [0.5, 0.0, 0.0, 0.25, 0.25])
    np.testing.assert_allclose(drift.returns, [0.0, 0.5 * 0.1 + 0.25 * 0.2 + 0.25 * -0.2])
    reset = version_returns(data, 1, 3, "2000-02", "2000-03", "reset")
    np.testing.assert_allclose(reset.returns[1], (0.1 + 0.2 - 0.2) / 3)


def test_drift_refuses_a_portfolio_that_lost_everything() -> None:
    data = make_data([[0.1, 0.0], [-1.0, 0.5], [0.0, 0.0]])
    with pytest.raises(ValueError, match="lost everything"):
        version_returns(data, 1, 1, "2000-02", "2000-03", "drift")


def test_results_are_read_only() -> None:
    result = version_returns(make_data(GOLDEN), 2, 1, "2000-03", "2000-08")
    with pytest.raises(ValueError, match="read-only"):
        result.returns[0] = 1.0
    with pytest.raises(ValueError, match="read-only"):
        result.weights[0, 0] = 1.0


# --- Family --------------------------------------------------------------------------------------


def test_family_is_the_monthly_average_of_its_15_versions() -> None:
    data = make_data(random_returns(seed=3, n_months=30, n_sectors=10))
    first, last = data.months[12], data.months[-1]
    versions = [
        version_returns(data, lookback, n, first, last).returns
        for lookback in (1, 3, 6, 9, 12)
        for n in (1, 2, 3)
    ]
    assert (FAMILY_LOOKBACKS, FAMILY_HOLDINGS) == ((1, 3, 6, 9, 12), (1, 2, 3))
    family = family_returns(data, first, last)
    assert family.shape == (18,)
    np.testing.assert_allclose(family, np.sum(versions, axis=0) / 15)


def test_family_of_identical_sectors_earns_their_return() -> None:
    data = make_data(np.tile(np.linspace(-0.05, 0.05, 20)[:, None], (1, 4)))
    np.testing.assert_allclose(
        family_returns(data, "2001-01", "2001-08"), np.linspace(-0.05, 0.05, 20)[12:]
    )
