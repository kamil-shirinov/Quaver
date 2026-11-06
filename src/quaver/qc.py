"""Parser for the log of the LEAN algorithm in lean/faber_etf, into monthly returns.

The block the algorithm writes (lean/faber_etf/logic.py, ``format_log``)::

    QUAVER-LOG v1 mode=family end=2026-09 universe=XLB,XLE,...
    1999-12 100000.00        one line per month-end portfolio value, no gaps
    2000-01 101234.56
    ...
    fees 1234.56
    orders 789
    min_cash 950.12
    QUAVER-END

QuantConnect may put a timestamp in front of a line; it is ignored. Lines outside the block are
ignored. Inside it, every line must be one of the above, or the parser refuses the log.
"""

import re
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

BEGIN = "QUAVER-LOG v1"
END = "QUAVER-END"
MODES = ("family", "benchmark", "smoke")
SUMMARY_KEYS = ("fees", "orders", "min_cash")

_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)? ")
_MONTH = r"\d{4}-(?:0[1-9]|1[0-2])"
_HEADER = re.compile(
    rf"^{re.escape(BEGIN)} mode=(?P<mode>{'|'.join(MODES)}) end=(?P<end>{_MONTH}) "
    r"universe=(?P<universe>[A-Z]+(?:,[A-Z]+)*)$"
)
_VALUE = re.compile(rf"^(?P<month>{_MONTH}) (?P<value>\d+\.\d{{2}})$")
_MONEY = re.compile(r"^(?P<key>fees|min_cash) (?P<value>-?\d+\.\d{2})$")
_COUNT = re.compile(r"^orders (?P<value>\d+)$")


class LogError(ValueError):
    """The log is not a complete, well-formed QUAVER-LOG block."""


@dataclass(frozen=True, eq=False)
class QcRun:
    """One LEAN run: month-end values and the monthly returns they give.

    ``months`` are the holding months; ``values`` has one more entry, the starting value at
    the end of the month before ``months[0]``. ``returns[k]`` is month ``months[k]``'s return.
    """

    mode: str
    end: str
    universe: tuple[str, ...]
    months: tuple[str, ...]
    values: npt.NDArray[np.float64]
    returns: npt.NDArray[np.float64]
    fees: float
    orders: int
    min_cash: float


def _next_month(month: str) -> str:
    index = int(month[:4]) * 12 + int(month[5:])
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _body(line: str) -> str:
    return _PREFIX.sub("", line.rstrip(), count=1)


def _add(summary: dict[str, float], key: str, number: str, where: str) -> None:
    if key in summary:
        raise LogError(f"{where}: {key} appears twice")
    summary[key] = float(number)


def parse_log(text: str) -> QcRun:
    """Parse a QuantConnect log holding exactly one QUAVER-LOG block."""
    lines = [_body(line) for line in text.splitlines()]
    starts = [i for i, line in enumerate(lines) if line.startswith(BEGIN)]
    if len(starts) != 1:
        raise LogError(f"expected one {BEGIN!r} line, found {len(starts)}")
    start = starts[0]
    header = _HEADER.match(lines[start])
    if header is None:
        raise LogError(f"line {start + 1}: malformed header: {lines[start]!r}")

    months: list[str] = []
    values: list[float] = []
    summary: dict[str, float] = {}
    finished = False
    for i in range(start + 1, len(lines)):
        line, where = lines[i], f"line {i + 1}"
        if line == END:
            finished = True
            break
        if not line:
            continue
        value, money, count = _VALUE.match(line), _MONEY.match(line), _COUNT.match(line)
        if value is not None:
            if summary:
                raise LogError(f"{where}: month value after the summary: {line!r}")
            month = value["month"]
            if months and month != _next_month(months[-1]):
                if month <= months[-1]:
                    raise LogError(f"{where}: {month} is out of order after {months[-1]}")
                raise LogError(f"{where}: gap: {_next_month(months[-1])} is missing")
            months.append(month)
            values.append(float(value["value"]))
        elif money is not None:
            _add(summary, money["key"], money["value"], where)
        elif count is not None:
            _add(summary, "orders", count["value"], where)
        else:
            raise LogError(f"{where}: malformed line: {line!r}")
    if not finished:
        raise LogError(f"no {END!r} line after the header")

    missing = [key for key in SUMMARY_KEYS if key not in summary]
    if missing:
        raise LogError(f"summary is missing {', '.join(missing)}")
    if len(months) < 2:
        raise LogError(f"need a starting value and at least one month, got {len(months)} lines")
    if months[-1] != header["end"]:
        raise LogError(f"the last month is {months[-1]}, but the header says end={header['end']}")
    levels = np.array(values, dtype=np.float64)
    if np.any(levels <= 0.0):
        raise LogError("portfolio values must be positive")
    returns = levels[1:] / levels[:-1] - 1.0
    levels.setflags(write=False)
    returns.setflags(write=False)
    return QcRun(
        mode=header["mode"],
        end=header["end"],
        universe=tuple(header["universe"].split(",")),
        months=tuple(months[1:]),
        values=levels,
        returns=returns,
        fees=summary["fees"],
        orders=int(summary["orders"]),
        min_cash=summary["min_cash"],
    )
