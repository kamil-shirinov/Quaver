"""Tests for the QuantConnect log parser. Every log here is made up."""

import numpy as np
import pytest

from quaver.qc import LogError, parse_log

import logic

GOOD = """\
2026-11-06 12:00:01 Launching analysis for 1a2b3c with LEAN Engine v2.5.0.0
2000-03-07 00:00:00 QUAVER-LOG v1 mode=smoke end=2000-03 universe=SPY,TLT,GLD,IWM
2000-03-07 00:00:00 1999-12 100000.00
2000-03-07 00:00:00 2000-01 101000.00
2000-02 98980.00

2000-03 103929.00
2000-03-07 00:00:00 fees 123.45
orders 12
min_cash 987.65
QUAVER-END
2000-03-07 00:00:00 Algorithm Id:(1a2b3c) completed in 1.23 seconds
"""


def replace(old: str, new: str) -> str:
    assert old in GOOD
    return GOOD.replace(old, new)


def test_parses_values_returns_and_summary() -> None:
    run = parse_log(GOOD)
    assert (run.mode, run.end, run.universe) == ("smoke", "2000-03", ("SPY", "TLT", "GLD", "IWM"))
    assert run.months == ("2000-01", "2000-02", "2000-03")
    np.testing.assert_array_equal(run.values, [100000.0, 101000.0, 98980.0, 103929.0])
    np.testing.assert_allclose(run.returns, [0.01, -0.02, 0.05], atol=1e-12)
    assert (run.fees, run.orders, run.min_cash) == (123.45, 12, 987.65)
    with pytest.raises(ValueError, match="read-only"):
        run.returns[0] = 0.0


def test_reads_what_the_algorithm_writes() -> None:
    settings = logic.run_settings("benchmark", "2001-02")
    months = [logic.add_months("1999-12", k) for k in range(15)]
    values = [100_000.0 * 1.01**k for k in range(15)]
    messages = logic.format_log(settings, months, values, 45.678, 120, -3.0)
    text = "\n".join(f"2001-03-07 00:00:00 {m}" for m in messages)
    run = parse_log(text)
    assert (run.mode, run.end, run.universe) == ("benchmark", "2001-02", logic.UNIVERSE)
    assert run.months == tuple(months[1:])
    np.testing.assert_allclose(run.returns, 0.01, atol=1e-6)
    assert (run.fees, run.orders, run.min_cash) == (45.68, 120, -3.0)


def test_a_gap_is_refused() -> None:
    with pytest.raises(LogError, match=r"line 6: gap: 2000-02 is missing"):
        parse_log(replace("2000-02 98980.00\n", ""))


def test_months_out_of_order_are_refused() -> None:
    with pytest.raises(LogError, match=r"line 5: 2000-01 is out of order after 2000-01"):
        parse_log(replace("2000-02 98980.00", "2000-01 98980.00"))


@pytest.mark.parametrize(
    "bad",
    [
        "2000-02 98980",  # no cents
        "2000-02 98,980.00",
        "2000-13 98980.00",  # no such month
        "2000-02  98980.00",
        "2000-02 -98980.00",
        "fees 1.5",
        "orders -1",
        "QUAVER-ENDED",
    ],
)
def test_a_malformed_line_is_refused(bad: str) -> None:
    with pytest.raises(LogError, match=r"line 5: malformed line"):
        parse_log(replace("2000-02 98980.00", bad))


def test_the_header_must_appear_once_and_be_well_formed() -> None:
    with pytest.raises(LogError, match="expected one 'QUAVER-LOG v1' line, found 0"):
        parse_log("nothing here\n")
    with pytest.raises(LogError, match="found 2"):
        parse_log(GOOD + GOOD)
    for header in (
        "QUAVER-LOG v1 mode=live end=2000-03 universe=SPY,TLT,GLD,IWM",
        "QUAVER-LOG v1 mode=smoke end=2000-3 universe=SPY,TLT,GLD,IWM",
        "QUAVER-LOG v1 mode=smoke end=2000-03 universe=",
        "QUAVER-LOG v1 mode=smoke end=2000-03",
    ):
        with pytest.raises(LogError, match="line 2: malformed header"):
            parse_log(
                replace("QUAVER-LOG v1 mode=smoke end=2000-03 universe=SPY,TLT,GLD,IWM", header)
            )


def test_the_block_must_end_and_carry_a_full_summary() -> None:
    with pytest.raises(LogError, match="no 'QUAVER-END' line after the header"):
        parse_log(GOOD[: GOOD.index("QUAVER-END")])
    with pytest.raises(LogError, match="summary is missing orders, min_cash"):
        parse_log(replace("orders 12\nmin_cash 987.65\n", ""))
    with pytest.raises(LogError, match="line 9: fees appears twice"):
        parse_log(replace("orders 12", "fees 1.00"))
    with pytest.raises(LogError, match="line 10: orders appears twice"):
        parse_log(replace("min_cash 987.65", "orders 3"))
    with pytest.raises(LogError, match="line 9: month value after the summary"):
        parse_log(replace("orders 12", "2000-04 1.00"))


def test_values_must_cover_at_least_one_month_and_reach_end() -> None:
    with pytest.raises(LogError, match="need a starting value and at least one month, got 1"):
        start = GOOD.index("2000-03-07 00:00:00 2000-01")
        stop = GOOD.index("2000-03-07 00:00:00 fees")
        parse_log(GOOD[:start] + GOOD[stop:])
    with pytest.raises(
        LogError, match="the last month is 2000-02, but the header says end=2000-03"
    ):
        parse_log(replace("2000-03 103929.00\n", ""))
    with pytest.raises(LogError, match="portfolio values must be positive"):
        parse_log(replace("2000-02 98980.00", "2000-02 0.00"))
