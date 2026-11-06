"""Loader for the pinned Ken French 10 industry data. It refuses any file the pin does not name."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

PIN_KEY = "french_10_industries"
TITLE = "Average Value Weighted Returns -- Monthly"
N_INDUSTRIES = 10
MISSING_CODES = (-99.99, -999.0)

_ROW = re.compile(r"^\s*\d{6}\s*,")


class DataError(ValueError):
    """The data file is not the pinned file, or it is not laid out as expected."""


@dataclass(frozen=True, eq=False)
class French10:
    """Monthly value-weighted returns, as decimal fractions."""

    months: tuple[str, ...]
    industries: tuple[str, ...]
    returns: npt.NDArray[np.float64]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pinned_hash(pins_path: Path) -> str:
    try:
        pins = json.loads(pins_path.read_text(encoding="utf-8"))
        pinned = pins[PIN_KEY]["csv_sha256"]
    except (KeyError, TypeError) as error:
        raise DataError(f"{pins_path} has no {PIN_KEY}.csv_sha256") from error
    if not isinstance(pinned, str):
        raise DataError(f"{pins_path} has no {PIN_KEY}.csv_sha256")
    return pinned


def _month(token: str, line_no: int) -> tuple[int, int]:
    year, month = int(token[:4]), int(token[4:])
    if not 1 <= month <= 12:
        raise DataError(f"line {line_no}: {token!r} is not a month")
    return year, month


def _value(token: str, line_no: int, column: str) -> float:
    try:
        value = float(token)
    except ValueError:
        value = math.nan
    if not math.isfinite(value):
        raise DataError(f"line {line_no}, {column}: {token.strip()!r} is not a number")
    if value in MISSING_CODES:
        raise DataError(f"line {line_no}, {column}: missing-value code {token.strip()}")
    return value


def _parse(text: str) -> French10:
    lines = text.splitlines()
    titles = [i for i, line in enumerate(lines) if line.strip() == TITLE]
    if not titles:
        raise DataError(f"table {TITLE!r} not found")
    start = titles[0] + 1
    if start >= len(lines):
        raise DataError(f"table {TITLE!r} has no header row")
    industries = tuple(cell.strip() for cell in lines[start].split(",")[1:])
    if len(industries) != N_INDUSTRIES:
        raise DataError(f"expected {N_INDUSTRIES} industry columns, found {len(industries)}")

    months: list[str] = []
    rows: list[list[float]] = []
    previous: tuple[int, int] | None = None
    for offset, line in enumerate(lines[start + 1 :]):
        if not _ROW.match(line):
            break
        line_no = start + offset + 2
        cells = line.split(",")
        year, month = _month(cells[0].strip(), line_no)
        if previous is not None:
            expected = (previous[0] + previous[1] // 12, previous[1] % 12 + 1)
            if (year, month) != expected:
                raise DataError(
                    f"line {line_no}: expected month {expected[0]}-{expected[1]:02d}, "
                    f"found {year}-{month:02d}"
                )
        previous = (year, month)
        if len(cells) - 1 != N_INDUSTRIES:
            raise DataError(
                f"line {line_no}: expected {N_INDUSTRIES} values, found {len(cells) - 1}"
            )
        months.append(f"{year}-{month:02d}")
        rows.append(
            [_value(cell, line_no, name) for cell, name in zip(cells[1:], industries, strict=True)]
        )
    if not rows:
        raise DataError(f"table {TITLE!r} has no data rows")
    returns = np.array(rows, dtype=np.float64) / 100.0
    returns.setflags(write=False)
    return French10(months=tuple(months), industries=industries, returns=returns)


def load_french10(csv_path: Path, pins_path: Path) -> French10:
    """Load the pinned file. The SHA-256 check always runs and cannot be turned off."""
    pinned = _pinned_hash(pins_path)
    actual = sha256_of(csv_path)
    if actual != pinned:
        raise DataError(f"{csv_path} hash mismatch: file is {actual}, pin expects {pinned}")
    return _parse(csv_path.read_text(encoding="utf-8"))
