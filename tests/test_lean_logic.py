"""Tests for lean/faber_etf/logic.py. All prices here are made up; nothing runs on QuantConnect."""

import ast
import importlib
import math
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from quaver.data import French10
from quaver.faber import (
    FAMILY_HOLDINGS,
    FAMILY_LOOKBACKS,
    FloatArray,
    family_returns,
    version_returns,
)

import logic

LEAN_DIR = Path(__file__).resolve().parents[1] / "lean" / "faber_etf"
N_ETFS = len(logic.UNIVERSE)


def months_from(start: str, count: int) -> tuple[str, ...]:
    return tuple(logic.add_months(start, k) for k in range(count))


def random_prices(seed: int, n_months: int, n_etfs: int = N_ETFS) -> FloatArray:
    """Month-end closes from monthly returns between -15% and +15%, starting at 20 to 80."""
    rng = np.random.default_rng(seed)
    start = rng.uniform(20.0, 80.0, size=n_etfs)
    growth = 1.0 + rng.uniform(-0.15, 0.15, size=(n_months - 1, n_etfs))
    return np.vstack([start, start * np.cumprod(growth, axis=0)])


def as_french(prices: FloatArray, start: str = "1999-01") -> French10:
    """The same prices as M1's input: monthly returns, labelled by the month they are earned."""
    returns = prices[1:] / prices[:-1] - 1.0
    names = tuple(f"E{k}" for k in range(prices.shape[1]))
    return French10(months=months_from(start, len(prices))[1:], industries=names, returns=returns)


def rows(prices: FloatArray) -> list[list[float]]:
    return [[float(x) for x in row] for row in prices]


# --- Same answers as the M1 code ------------------------------------------------------------------


def test_constants_match_the_m1_family() -> None:
    assert (logic.LOOKBACKS, logic.HOLDINGS) == (FAMILY_LOOKBACKS, FAMILY_HOLDINGS)
    assert logic.MAX_LOOKBACK == 12
    assert logic.UNIVERSE == ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_selections_and_weights_match_quaver_faber(seed: int) -> None:
    prices = random_prices(seed, n_months=40)
    closes = rows(prices)
    data = as_french(prices)
    for lookback in FAMILY_LOOKBACKS:
        for n in FAMILY_HOLDINGS:
            # Returns row h is earned in price month h + 1 and decided at price row t = h.
            first, last = data.months[lookback], data.months[-1]
            m1 = version_returns(data, lookback, n, first, last)
            for k, h in enumerate(range(lookback, len(data.months))):
                scores = logic.trailing_returns(closes, h, lookback)
                assert logic.select(scores, n) == m1.holdings[k], (lookback, n, h)
                np.testing.assert_allclose(
                    logic.version_weights(closes, h, lookback, n), m1.weights[k], atol=1e-15
                )


@pytest.mark.parametrize("seed", [4, 5])
def test_family_weights_match_quaver_faber(seed: int) -> None:
    prices = random_prices(seed, n_months=36)
    closes = rows(prices)
    data = as_french(prices)
    first, last = data.months[12], data.months[-1]
    m1_weights = [
        version_returns(data, lookback, n, first, last).weights
        for lookback in FAMILY_LOOKBACKS
        for n in FAMILY_HOLDINGS
    ]
    expected_weights = np.mean(m1_weights, axis=0)
    family = np.array([logic.family_weights(closes, h) for h in range(12, len(data.months))])
    np.testing.assert_allclose(family, expected_weights, atol=1e-15)
    np.testing.assert_allclose(family.sum(axis=1), 1.0, atol=1e-12)
    # Holding the family weights for a month earns M1's family return.
    earned = (family * data.returns[12:]).sum(axis=1)
    np.testing.assert_allclose(earned, family_returns(data, first, last), atol=1e-14)


def test_ties_go_to_the_etf_listed_first_in_both() -> None:
    prices = random_prices(6, n_months=20, n_etfs=4)
    prices[:, 2] = prices[:, 1]  # E1 and E2 move together
    prices[:, 3] = prices[:, 0]  # so do E0 and E3
    closes = rows(prices)
    data = as_french(prices)
    for lookback in FAMILY_LOOKBACKS:
        m1 = version_returns(data, lookback, 2, data.months[lookback], data.months[-1])
        for k, h in enumerate(range(lookback, len(data.months))):
            held = logic.select(logic.trailing_returns(closes, h, lookback), 2)
            assert held == m1.holdings[k]
            assert held in ((0, 3), (1, 2))  # the pair tied, the first-listed ETF first
    assert logic.select([0.1, 0.3, 0.3, 0.3], 2) == (1, 2)
    assert logic.select([0.5, 0.5, 0.5], 1) == (0,)
    assert logic.select([-0.0, 0.0], 1) == (0,)


def test_trailing_return_is_the_compounded_monthly_return() -> None:
    closes = [[100.0, 50.0], [110.0, 45.0], [121.0, 54.0], [96.8, 54.0]]
    np.testing.assert_allclose(logic.trailing_returns(closes, 2, 2), [0.21, 0.08])
    np.testing.assert_allclose(logic.trailing_returns(closes, 3, 1), [-0.2, 0.0])
    np.testing.assert_allclose(
        logic.trailing_returns(closes, 3, 3), [1.1 * 1.1 * 0.8 - 1, 0.9 * 1.2 * 1.0 - 1]
    )


# --- No lookahead: perturb every price after month t ---------------------------------------------


def test_perturbing_the_future_never_changes_a_decision() -> None:
    rng = np.random.default_rng(7)
    original = random_prices(8, n_months=48)
    later_changed = False
    for t in range(logic.MAX_LOOKBACK, 47):
        perturbed = original.copy()
        perturbed[t + 1 :] = rng.uniform(5.0, 150.0, size=perturbed[t + 1 :].shape)
        a, b = rows(original), rows(perturbed)
        assert logic.family_weights(b, t) == logic.family_weights(a, t), t
        for lookback in FAMILY_LOOKBACKS:
            for n in FAMILY_HOLDINGS:
                assert logic.version_weights(b, t, lookback, n) == logic.version_weights(
                    a, t, lookback, n
                )
        later_changed |= logic.family_weights(b, t + 1) != logic.family_weights(a, t + 1)
    # The perturbation is strong enough that the test could fail.
    assert later_changed


def daily_bars(seed: int, first_day: str, n_days: int) -> list[tuple[str, float]]:
    """Made-up closes for every calendar day from ``first_day`` (weekends do not matter here)."""
    rng = np.random.default_rng(seed)
    start = np.datetime64(first_day)
    closes = 50.0 * np.cumprod(1.0 + rng.uniform(-0.03, 0.03, size=n_days))
    return [(str(start + np.timedelta64(k, "D")), float(c)) for k, c in enumerate(closes)]


def test_month_end_closes_ignore_bars_after_the_signal_day() -> None:
    bars = daily_bars(9, "1998-12-01", 500)
    rng = np.random.default_rng(10)
    for cut in (30, 31, 89, 365, 498):
        day = bars[cut][0]
        perturbed = bars[: cut + 1] + [(d, float(rng.uniform(1, 999))) for d, _ in bars[cut + 1 :]]
        assert logic.month_end_closes(perturbed, day) == logic.month_end_closes(bars, day)
        assert logic.month_end_closes(bars, day) == logic.month_end_closes(bars[: cut + 1], day)


@settings(max_examples=200, deadline=None)
@given(draw=st.data())
def test_family_weights_depend_only_on_rows_up_to_t(draw: st.DataObject) -> None:
    n_etfs = draw.draw(st.integers(3, 9), label="etfs")
    n_months = draw.draw(st.integers(14, 30), label="months")
    t = draw.draw(st.integers(12, n_months - 2), label="t")
    price = st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False)
    past = draw.draw(arrays(np.float64, (n_months, n_etfs), elements=price), label="past")
    future = draw.draw(arrays(np.float64, (n_months - t - 1, n_etfs), elements=price))
    swapped = np.concatenate([past[: t + 1], future])
    assert logic.family_weights(rows(swapped), t) == logic.family_weights(rows(past), t)


# --- Month-end closes from daily bars -------------------------------------------------------------


def test_month_end_closes_take_each_months_last_bar() -> None:
    bars = [
        ("1998-12-22", 10.0),
        ("1998-12-31", 11.0),
        ("1999-01-04", 12.0),
        ("1999-01-29", 13.0),
        ("1999-02-01", 14.0),
        ("1999-02-02", 15.0),
    ]
    assert logic.month_end_closes(bars, "1999-01-29") == {"1998-12": 11.0, "1999-01": 13.0}
    assert logic.month_end_closes(bars, "1999-02-02") == {
        "1998-12": 11.0,
        "1999-01": 13.0,
        "1999-02": 15.0,
    }


def test_month_end_closes_refuse_bad_bars() -> None:
    good = [("2000-01-31", 10.0), ("2000-02-29", 11.0)]
    with pytest.raises(ValueError, match="'2000-02-30x' is not a day"):
        logic.month_end_closes(good, "2000-02-30x")
    with pytest.raises(ValueError, match="'2000-1-31' is not a day"):
        logic.month_end_closes([("2000-1-31", 10.0)], "2000-01-31")
    with pytest.raises(ValueError, match="not in time order: 2000-01-31 follows 2000-01-31"):
        logic.month_end_closes([good[0], good[0]], "2000-01-31")
    with pytest.raises(ValueError, match=r"close on 2000-01-31 is 0.0"):
        logic.month_end_closes([("2000-01-31", 0.0)], "2000-01-31")
    with pytest.raises(ValueError, match="close on 2000-01-31 is nan"):
        logic.month_end_closes([("2000-01-31", math.nan)], "2000-01-31")
    with pytest.raises(ValueError, match="no close on 2000-03-01; the last bar is 2000-02-29"):
        logic.month_end_closes(good, "2000-03-01")
    with pytest.raises(ValueError, match="no close on 2000-01-31; the last bar is missing"):
        logic.month_end_closes([], "2000-01-31")


def test_close_matrix_needs_thirteen_month_ends() -> None:
    months = months_from("1998-12", 13)  # 1998-12 .. 1999-12
    a = {m: 10.0 + k for k, m in enumerate(months)}
    b = {m: 20.0 + k for k, m in enumerate(months)} | {"2000-01": 99.0}
    matrix = logic.close_matrix([a, b], ("A", "B"), "1999-12")
    assert len(matrix) == 13
    assert matrix[0] == [10.0, 20.0]
    assert matrix[-1] == [22.0, 32.0]  # 2000-01 is after the signal month and is not read
    del a["1998-12"]
    with pytest.raises(ValueError, match=r"A has no month-end close for 1998-12; .* from 1998-12"):
        logic.close_matrix([a, b], ("A", "B"), "1999-12")
    with pytest.raises(ValueError, match="2 close series for 1 tickers"):
        logic.close_matrix([a, b], ("A",), "1999-12")


# --- Arguments -----------------------------------------------------------------------------------


def test_months() -> None:
    assert logic.add_months("2000-01", -1) == "1999-12"
    assert logic.add_months("1999-12", 13) == "2001-01"
    assert logic.add_months("2000-01", -13) == "1998-12"
    assert logic.parse_month("2026-09") == "2026-09"
    for bad in ("2026-9", "2026-13", "2026-00", "26-09", "2026-09-01"):
        with pytest.raises(ValueError, match="is not a month written YYYY-MM"):
            logic.parse_month(bad)


def test_run_settings() -> None:
    family = logic.run_settings("family", "2026-09")
    assert (family.tickers, family.first, family.base, family.end) == (
        logic.UNIVERSE,
        "2000-01",
        "1999-12",
        "2026-09",
    )
    assert family.follows_family
    benchmark = logic.run_settings("benchmark", "2000-01")
    assert benchmark.tickers == logic.UNIVERSE and not benchmark.follows_family
    smoke = logic.run_settings("smoke", "2006-03")
    assert (smoke.tickers, smoke.first, smoke.base) == (logic.SMOKE_UNIVERSE, "2006-01", "2005-12")
    assert smoke.follows_family
    with pytest.raises(ValueError, match="mode must be one of family, benchmark, smoke, got None"):
        logic.run_settings(None, "2026-09")
    with pytest.raises(ValueError, match="got 'Family'"):
        logic.run_settings("Family", "2026-09")
    with pytest.raises(ValueError, match=r"parameter end .* is missing"):
        logic.run_settings("family", None)
    with pytest.raises(ValueError, match="is not a month"):
        logic.run_settings("family", "")
    with pytest.raises(ValueError, match="end 1999-12 is before the first holding month 2000-01"):
        logic.run_settings("family", "1999-12")
    with pytest.raises(ValueError, match="end 2005-12 is before the first holding month 2006-01"):
        logic.run_settings("smoke", "2005-12")


def test_the_smoke_universe_has_twelve_months_of_closes_before_its_first_month() -> None:
    # GLD, the youngest, has its first month-end close at 2004-11 (listed 2004-11-18).
    assert logic.add_months(logic.SMOKE_FIRST_HOLDING_MONTH, -logic.MAX_LOOKBACK - 1) == "2004-12"
    assert logic.add_months(logic.FIRST_HOLDING_MONTH, -logic.MAX_LOOKBACK - 1) == "1998-12"


def test_trailing_returns_and_select_refuse_bad_arguments() -> None:
    closes = [[1.0, 2.0], [1.1, 2.2]]
    with pytest.raises(ValueError, match="at least 1 month"):
        logic.trailing_returns(closes, 1, 0)
    with pytest.raises(ValueError, match="outside the closes"):
        logic.trailing_returns(closes, 2, 1)
    with pytest.raises(ValueError, match="outside the closes"):
        logic.trailing_returns(closes, -1, 1)
    with pytest.raises(ValueError, match="needs 3 month-end closes, only 2 are available"):
        logic.trailing_returns(closes, 1, 2)
    with pytest.raises(ValueError, match="cannot hold 0 of 2"):
        logic.select([0.1, 0.2], 0)
    with pytest.raises(ValueError, match="cannot hold 3 of 2"):
        logic.select([0.1, 0.2], 3)
    with pytest.raises(ValueError, match="finite"):
        logic.select([0.1, math.nan], 1)


def test_benchmark_weights() -> None:
    assert logic.benchmark_weights(9) == [1 / 9] * 9
    assert math.isclose(sum(logic.benchmark_weights(9)), 1.0)
    with pytest.raises(ValueError, match="at least one ETF"):
        logic.benchmark_weights(0)


# --- Orders and fees -----------------------------------------------------------------------------


def test_order_quantities_round_targets_down_and_keep_the_buffer() -> None:
    # Budget 0.99 * 100,000 = 99,000: A 0.5 -> 49,500 / 30 = 1650; B 0.5 -> 49,500 / 70 = 707.1.
    assert logic.order_quantities([0.5, 0.5, 0.0], 100_000.0, [30.0, 70.0, 10.0], [0, 0, 0]) == [
        1650,
        707,
        0,
    ]
    # From holdings: sell all of C, trim A, add to B.
    assert logic.order_quantities(
        [0.5, 0.5, 0.0], 100_000.0, [30.0, 70.0, 10.0], [1700, 600, 50]
    ) == [-50, 107, -50]
    assert logic.order_quantities([1.0], 1000.0, [10.0], [0], buffer=0.0) == [100]
    spent = 1650 * 30.0 + 707 * 70.0
    assert spent <= 0.99 * 100_000.0


def test_order_quantities_refuse_bad_arguments() -> None:
    ok = ([0.5, 0.5], 1000.0, [10.0, 10.0], [0, 0])
    with pytest.raises(ValueError, match="2 weights, 1 prices, 2 holdings"):
        logic.order_quantities(ok[0], ok[1], [10.0], ok[3])
    for buffer in (-0.01, 1.0):
        with pytest.raises(ValueError, match="buffer must be in"):
            logic.order_quantities(*ok, buffer=buffer)
    for value in (0.0, math.inf):
        with pytest.raises(ValueError, match="not a positive number"):
            logic.order_quantities(ok[0], value, ok[2], ok[3])
    for weights in ([0.6, 0.6], [-0.1, 0.5], [math.nan, 0.5]):
        with pytest.raises(ValueError, match="non-negative and sum to at most 1"):
            logic.order_quantities(weights, ok[1], ok[2], ok[3])
    with pytest.raises(ValueError, match="prices must be positive"):
        logic.order_quantities(ok[0], ok[1], [10.0, 0.0], ok[3])


def test_sells_are_submitted_before_buys() -> None:
    assert logic.submission_order([5, -3, 0, 2, -1]) == [1, 4, 0, 3]
    assert logic.submission_order([0, 0]) == []


def test_fee_is_ten_bps_of_traded_value() -> None:
    assert logic.FEE_RATE == 0.001
    assert math.isclose(logic.fee(10_000.0), 10.0)
    assert math.isclose(logic.fee(-2_500.0), 2.5)


# --- Log -----------------------------------------------------------------------------------------


def full_run_log(end: str = "2026-09") -> tuple[logic.RunSettings, list[str], list[str]]:
    run = logic.run_settings("family", end)
    n = (int(end[:4]) - 1999) * 12 + int(end[5:]) - 12 + 1
    months = list(months_from(run.base, n))
    values = [9_999_999.99 - k for k in range(n)]  # the widest plausible values
    return run, months, logic.format_log(run, months, values, 12_345.67, 9_999, -1.5)


def test_log_has_one_message_per_year_and_fits_the_limit() -> None:
    _, months, messages = full_run_log()
    assert months[0] == "1999-12" and months[-1] == "2026-09" and len(months) == 322
    assert messages[0] == (
        "QUAVER-LOG v1 mode=family end=2026-09 universe=XLB,XLE,XLF,XLI,XLK,XLP,XLU,XLV,XLY"
    )
    assert messages[1] == "1999-12 9999999.99"
    assert messages[2].splitlines()[0] == "2000-01 9999998.99"
    assert len(messages[2].splitlines()) == 12
    assert len(messages[-2].splitlines()) == 9  # 2026-01 .. 2026-09
    assert messages[-1] == "fees 12345.67\norders 9999\nmin_cash -1.50\nQUAVER-END"
    assert len(messages) == 1 + 28 + 1
    size = sum(len(m) + 1 + logic.LOG_PREFIX_BYTES for m in messages)
    assert size <= logic.LOG_LIMIT_BYTES < 10_000


def test_log_refuses_gaps_and_oversize() -> None:
    run = logic.run_settings("family", "2000-02")
    with pytest.raises(ValueError, match="3 months but 2 values"):
        logic.format_log(run, ["1999-12", "2000-01", "2000-02"], [1.0, 2.0], 0.0, 0, 0.0)
    with pytest.raises(ValueError, match="from 1999-12 to 2000-02 without a gap, got 1999-12 to"):
        logic.format_log(run, ["1999-12", "2000-02"], [1.0, 2.0], 0.0, 0, 0.0)
    with pytest.raises(ValueError, match=r"from 1999-12 to 2000-02 .* got 1999-12 to 2000-01"):
        logic.format_log(run, ["1999-12", "2000-01"], [1.0, 2.0], 0.0, 0, 0.0)
    with pytest.raises(ValueError, match="got none to none"):
        logic.format_log(run, [], [], 0.0, 0, 0.0)
    with pytest.raises(ValueError, match=r"the log would be about .* bytes, over 8000"):
        full_run_log("2036-12")


# --- main.py -------------------------------------------------------------------------------------


def test_main_cannot_be_imported_outside_quantconnect() -> None:
    with pytest.raises(ModuleNotFoundError, match="AlgorithmImports"):
        importlib.import_module("main")


@pytest.mark.parametrize("name", ["logic.py", "main.py"])
def test_lean_files_parse_as_python_3_11(name: str) -> None:
    source = (LEAN_DIR / name).read_text(encoding="utf-8")
    ast.parse(source, filename=name, feature_version=(3, 11))
