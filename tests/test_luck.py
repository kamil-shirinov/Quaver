"""Test 3 (luck) tests, on made-up data only.

``quaver.luck`` is imported as a module: its ``test3`` function and ``Test3`` class would
otherwise be collected by pytest as tests.
"""

import numpy as np
import pytest

from quaver import after, luck
from quaver.data import French10
from quaver.faber import benchmark_returns

INDUSTRIES = tuple(f"S{k}" for k in range(10))
FIRST, LAST = "2000-01", "2002-12"


def months_from(year: int, n: int) -> tuple[str, ...]:
    return tuple(f"{year + k // 12}-{k % 12 + 1:02d}" for k in range(n))


def made_up(returns: np.ndarray) -> French10:
    return French10(months=months_from(1999, len(returns)), industries=INDUSTRIES, returns=returns)


def random_data(seed: int = 4) -> French10:
    return made_up(np.random.default_rng(seed).uniform(-0.08, 0.10, size=(48, 10)))


def test_preregistered_constants() -> None:
    assert (luck.K, luck.SEED, luck.CHUNK, luck.ALPHA) == (10_000, 20261106, 100, 0.05)
    assert luck.HOLDINGS.tolist() == [1, 2, 3] * 5


def test_same_seed_same_output() -> None:
    data = random_data()
    a = luck.random_family_stats(data, FIRST, LAST, k=200)
    b = luck.random_family_stats(data, FIRST, LAST, k=200)
    assert a.shape == (200,)
    assert np.array_equal(a, b)
    other = luck.random_family_stats(data, FIRST, LAST, k=200, seed=1)
    assert not np.array_equal(a, other)


@pytest.mark.parametrize("k", [200, 150])
def test_first_families_do_not_depend_on_k(k: int) -> None:
    data = random_data()
    small = luck.random_family_stats(data, FIRST, LAST, k=100)
    large = luck.random_family_stats(data, FIRST, LAST, k=k)
    assert np.array_equal(small, large[:100])


def test_one_family_by_brute_force() -> None:
    """Re-derive the first two families draw by draw from the stated procedure."""
    data = random_data()
    returns = data.returns[12:]
    bench = benchmark_returns(data, FIRST, LAST)
    draws = np.random.default_rng(luck.SEED).random((100, 15, 36, 10))
    stats = luck.random_family_stats(data, FIRST, LAST, k=100)
    for f in range(2):
        family = np.zeros(36)
        for v, n in enumerate([1, 2, 3] * 5):
            for t in range(36):
                held = np.argsort(draws[f, v, t])[:n]
                family[t] += returns[t, held].mean() / 15
        assert stats[f] == pytest.approx(12 * np.mean(family - bench), rel=1e-12)


def test_random_families_centre_on_zero() -> None:
    stats = luck.random_family_stats(random_data(), FIRST, LAST, k=1000)
    assert abs(stats.mean()) < 3 * stats.std() / np.sqrt(stats.size)


def test_k_must_be_positive() -> None:
    with pytest.raises(ValueError, match="k must be at least 1"):
        luck.random_family_stats(random_data(), FIRST, LAST, k=0)


@pytest.mark.parametrize(
    ("real", "randoms", "expected"),
    [
        (1.0, [0.0, 0.5, 0.9], 1 / 4),
        (0.5, [0.0, 0.5, 0.9], 3 / 4),  # ties count as at least as high
        (-1.0, [0.0, 0.5, 0.9], 4 / 4),
        (0.0, [0.0] * 10_000, 1.0),
        (2.0, [0.0] * 10_000, 1 / 10_001),
    ],
)
def test_p_value(real: float, randoms: list[float], expected: float) -> None:
    assert luck.p_value(real, np.array(randoms)) == pytest.approx(expected)


@pytest.mark.parametrize("randoms", [np.array([]), np.ones((2, 2))])
def test_p_value_refuses_bad_input(randoms: np.ndarray) -> None:
    with pytest.raises(ValueError, match="non-empty one-dimensional"):
        luck.p_value(0.0, randoms)


@pytest.mark.parametrize(
    ("p", "expected"),
    [(0.0001, "beats luck"), (0.0499, "beats luck"), (0.05, "not distinguishable from luck")],
)
def test_verdict(p: float, expected: str) -> None:
    assert luck.verdict(p) == expected


def test_one_sector_always_winning_beats_luck() -> None:
    returns = np.random.default_rng(6).uniform(-0.08, 0.10, size=(48, 10))
    returns[:, 7] = 0.20
    result = luck.test3(made_up(returns), FIRST, LAST, k=200)
    assert result.real == pytest.approx(after.family_statistic(made_up(returns), FIRST, LAST))
    assert result.real > result.randoms.max()
    assert result.p == 1 / 201
    assert result.verdict == "beats luck"


def test_identical_sectors_give_p_one() -> None:
    # Exactly representable returns, so every statistic is exactly zero.
    values = np.array([0.5, -0.25, 0.125, 0.0625] * 12)
    result = luck.test3(made_up(np.repeat(values[:, None], 10, axis=1)), FIRST, LAST, k=200)
    assert result.real == 0.0
    assert np.all(result.randoms == 0.0)
    assert result.p == 1.0
    assert result.verdict == "not distinguishable from luck"


def test_test3_record() -> None:
    result = luck.test3(random_data(), FIRST, LAST, k=100)
    record = result.to_json()
    assert (record["first"], record["last"], record["months"]) == (FIRST, LAST, 36)
    assert record["random_families"] == 100
    assert record["random_at_least_real"] == int(np.sum(result.randoms >= result.real))
    assert record["p"] == (1 + record["random_at_least_real"]) / 101
    assert record["percentiles"] == {
        "5": result.percentile(5),
        "50": result.percentile(50),
        "95": result.percentile(95),
    }
    assert record["randoms"] == result.randoms.tolist()
