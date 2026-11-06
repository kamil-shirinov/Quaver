"""The arithmetic of Faber's family on sector ETFs, for the LEAN algorithm in main.py.

Pure Python, standard library only and no LEAN imports, so it runs the same inside
QuantConnect (which loads it next to main.py) and in the test suite. It must stay valid on the
Python version LEAN runs (3.11).

Prices are month-end adjusted closes, one row per month, oldest first, one column per ETF in
universe order. Every function that makes a decision for the month after row t reads only rows
up to t, so no decision can see its own holding month or anything later.
"""

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

UNIVERSE = ("XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY")
# A dummy universe for checking the mechanics without producing any result of the real test.
SMOKE_UNIVERSE = ("SPY", "TLT", "GLD", "IWM")
MODES = ("family", "benchmark", "smoke")

LOOKBACKS = (1, 3, 6, 9, 12)
HOLDINGS = (1, 2, 3)
MAX_LOOKBACK = max(LOOKBACKS)

FIRST_HOLDING_MONTH = "2000-01"
# GLD's first month-end close is 2004-11, so a 12-month signal can first be read at 2005-12.
SMOKE_FIRST_HOLDING_MONTH = "2006-01"

INITIAL_CASH = 100_000
FEE_RATE = 0.001  # 10 bps of traded value
# Targets are sized on (1 - CASH_BUFFER) of the portfolio value at the signal close. The 1%
# left in cash pays the fees (at most 0.2% of value a month: 10 bps on 200% turnover) and
# absorbs the move from that close to the next open, when the orders fill.
CASH_BUFFER = 0.01

LOG_BEGIN = "QUAVER-LOG v1"
LOG_END = "QUAVER-END"
LOG_LIMIT_BYTES = 8000
# Allowance per log message for the timestamp QuantConnect puts in front of it.
LOG_PREFIX_BYTES = 32

_MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
_DAY = re.compile(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")


def parse_month(text: str) -> str:
    """``text`` if it is a month written YYYY-MM, else ValueError."""
    if not _MONTH.fullmatch(text):
        raise ValueError(f"{text!r} is not a month written YYYY-MM")
    return text


def add_months(month: str, k: int) -> str:
    """The month ``k`` months after ``month`` (before it if ``k`` is negative)."""
    parse_month(month)
    index = int(month[:4]) * 12 + int(month[5:]) - 1 + k
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


@dataclass(frozen=True)
class RunSettings:
    """What one run trades and over which months.

    ``base`` is the month before the first holding month: its month-end value is the starting
    point, and the first orders are placed after its close.
    """

    mode: str
    tickers: tuple[str, ...]
    first: str
    end: str

    @property
    def base(self) -> str:
        return add_months(self.first, -1)

    @property
    def follows_family(self) -> bool:
        return self.mode in ("family", "smoke")


def run_settings(mode: str | None, end: str | None) -> RunSettings:
    """Check the two algorithm parameters and turn them into a run's settings."""
    if mode not in MODES:
        raise ValueError(f"parameter mode must be one of {', '.join(MODES)}, got {mode!r}")
    if end is None:
        raise ValueError("parameter end (the last holding month, YYYY-MM) is missing")
    parse_month(end)
    first = SMOKE_FIRST_HOLDING_MONTH if mode == "smoke" else FIRST_HOLDING_MONTH
    if end < first:
        raise ValueError(f"end {end} is before the first holding month {first}")
    tickers = SMOKE_UNIVERSE if mode == "smoke" else UNIVERSE
    return RunSettings(mode=mode, tickers=tickers, first=first, end=end)


def month_end_closes(bars: Sequence[tuple[str, float]], day: str) -> dict[str, float]:
    """Each month's last close up to and including ``day``, from (YYYY-MM-DD, close) bars.

    Bars after ``day`` are ignored. ``day`` itself must have a bar, so the current month's
    entry is that day's close and not a stale one.
    """
    if not _DAY.fullmatch(day):
        raise ValueError(f"{day!r} is not a day written YYYY-MM-DD")
    closes: dict[str, float] = {}
    last = ""
    for bar_day, close in bars:
        if not _DAY.fullmatch(bar_day):
            raise ValueError(f"{bar_day!r} is not a day written YYYY-MM-DD")
        if bar_day > day:
            break
        if bar_day <= last:
            raise ValueError(f"bars are not in time order: {bar_day} follows {last}")
        if not (math.isfinite(close) and close > 0.0):
            raise ValueError(f"close on {bar_day} is {close}, not a positive number")
        closes[bar_day[:7]] = close
        last = bar_day
    if last != day:
        raise ValueError(f"no close on {day}; the last bar is {last or 'missing'}")
    return closes


def close_matrix(
    month_ends: Sequence[Mapping[str, float]], tickers: Sequence[str], month: str
) -> list[list[float]]:
    """Month-end closes for the MAX_LOOKBACK + 1 months ending ``month``, one column per ETF."""
    if len(month_ends) != len(tickers):
        raise ValueError(f"{len(month_ends)} close series for {len(tickers)} tickers")
    months = [add_months(month, k) for k in range(-MAX_LOOKBACK, 1)]
    rows: list[list[float]] = []
    for m in months:
        row = []
        for ticker, closes in zip(tickers, month_ends, strict=True):
            if m not in closes:
                raise ValueError(
                    f"{ticker} has no month-end close for {m}; a {MAX_LOOKBACK}-month signal "
                    f"at {month} needs closes from {months[0]}"
                )
            row.append(closes[m])
        rows.append(row)
    return rows


def trailing_returns(closes: Sequence[Sequence[float]], t: int, lookback: int) -> list[float]:
    """Each ETF's total return over the ``lookback`` months ending at row t.

    That is close[t] / close[t - lookback] - 1, from adjusted closes: the same as compounding
    the monthly total returns of months t-lookback+1 to t.
    """
    if lookback < 1:
        raise ValueError(f"lookback must be at least 1 month, got {lookback}")
    if not 0 <= t < len(closes):
        raise ValueError(f"month index {t} is outside the closes (0 to {len(closes) - 1})")
    if t - lookback < 0:
        raise ValueError(
            f"a {lookback}-month return at month index {t} needs {lookback + 1} month-end "
            f"closes, only {t + 1} are available"
        )
    now, then = closes[t], closes[t - lookback]
    return [a / b - 1.0 for a, b in zip(now, then, strict=True)]


def select(scores: Sequence[float], n: int) -> tuple[int, ...]:
    """Indices of the n highest scores, best first. Ties go to the ETF listed first."""
    if not 1 <= n <= len(scores):
        raise ValueError(f"cannot hold {n} of {len(scores)} ETFs")
    if not all(math.isfinite(s) for s in scores):
        raise ValueError("scores must be finite")
    # sorted() is stable, so equal scores keep universe order.
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    return tuple(order[:n])


def version_weights(
    closes: Sequence[Sequence[float]], t: int, lookback: int, n: int
) -> list[float]:
    """One version's weights for the month after row t: 1/n in each of its top n ETFs."""
    held = select(trailing_returns(closes, t, lookback), n)
    weights = [0.0] * len(closes[t])
    for i in held:
        weights[i] = 1.0 / n
    return weights


def family_weights(closes: Sequence[Sequence[float]], t: int) -> list[float]:
    """The average of the 15 versions' weights (every lookback with N in 1, 2, 3)."""
    versions = [version_weights(closes, t, lookback, n) for lookback in LOOKBACKS for n in HOLDINGS]
    return [sum(column) / len(versions) for column in zip(*versions, strict=True)]


def benchmark_weights(n_assets: int) -> list[float]:
    """1/n in each ETF."""
    if n_assets < 1:
        raise ValueError(f"the benchmark needs at least one ETF, got {n_assets}")
    return [1.0 / n_assets] * n_assets


def order_quantities(
    weights: Sequence[float],
    value: float,
    prices: Sequence[float],
    held: Sequence[int],
    buffer: float = CASH_BUFFER,
) -> list[int]:
    """Whole-share orders that move ``held`` to ``weights`` of (1 - buffer) * value.

    Target shares are rounded down, so rounding never spends more than the target.
    """
    if not len(weights) == len(prices) == len(held):
        raise ValueError(f"{len(weights)} weights, {len(prices)} prices, {len(held)} holdings")
    if not 0.0 <= buffer < 1.0:
        raise ValueError(f"buffer must be in [0, 1), got {buffer}")
    if not (math.isfinite(value) and value > 0.0):
        raise ValueError(f"portfolio value is {value}, not a positive number")
    if any(not (math.isfinite(w) and w >= 0.0) for w in weights) or sum(weights) > 1.0 + 1e-9:
        raise ValueError(f"weights must be non-negative and sum to at most 1, got {weights}")
    if any(not (math.isfinite(p) and p > 0.0) for p in prices):
        raise ValueError(f"prices must be positive, got {prices}")
    budget = (1.0 - buffer) * value
    targets = [math.floor(w * budget / p) for w, p in zip(weights, prices, strict=True)]
    return [target - h for target, h in zip(targets, held, strict=True)]


def submission_order(quantities: Sequence[int]) -> list[int]:
    """Indices of the non-zero orders: sells first, then buys, each in universe order.

    LEAN fills pending orders in the order they were submitted, so sells free cash before the
    buys are checked for buying power.
    """
    sells = [i for i, q in enumerate(quantities) if q < 0]
    buys = [i for i, q in enumerate(quantities) if q > 0]
    return sells + buys


def fee(traded_value: float) -> float:
    """The fee on one order: FEE_RATE of its traded value."""
    return FEE_RATE * abs(traded_value)


def format_log(
    settings: RunSettings,
    months: Sequence[str],
    values: Sequence[float],
    fees: float,
    orders: int,
    min_cash: float,
) -> list[str]:
    """The run's log as a few messages: a header, one message per calendar year, a summary.

    ``months`` runs from ``settings.base`` to ``settings.end`` without a gap; ``values`` are
    the portfolio values at those months' last closes. Raises if the log would exceed
    LOG_LIMIT_BYTES, counting LOG_PREFIX_BYTES for each message's timestamp.
    """
    if len(months) != len(values):
        raise ValueError(f"{len(months)} months but {len(values)} values")
    expected = [add_months(settings.base, k) for k in range(len(months))]
    if list(months) != expected or not months or months[-1] != settings.end:
        raise ValueError(
            f"months must run from {settings.base} to {settings.end} without a gap, "
            f"got {months[0] if months else 'none'} to {months[-1] if months else 'none'}"
        )
    header = f"{LOG_BEGIN} mode={settings.mode} end={settings.end} universe=" + ",".join(
        settings.tickers
    )
    messages = [header]
    year_lines: list[str] = []
    for k, (month, value) in enumerate(zip(months, values, strict=True)):
        year_lines.append(f"{month} {value:.2f}")
        if k + 1 == len(months) or months[k + 1][:4] != month[:4]:
            messages.append("\n".join(year_lines))
            year_lines = []
    messages.append(f"fees {fees:.2f}\norders {orders}\nmin_cash {min_cash:.2f}\n{LOG_END}")
    size = sum(len(m.encode()) + 1 + LOG_PREFIX_BYTES for m in messages)
    if size > LOG_LIMIT_BYTES:
        raise ValueError(f"the log would be about {size} bytes, over {LOG_LIMIT_BYTES}")
    return messages
