"""Compare two independent readings of the same paper's claims.

A reading is a YAML file with a ``claims`` list (a full spec works too; everything else in the
file is ignored). Claims are matched on what they measure, not on their id, because two readers
number their claims independently. Table values cannot be quote-checked, so a second reading
compared with the first is the check on them.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import TypeAdapter

from quaver.spec import Claim, Source

type ClaimKey = tuple[str, int | None, int | None, str, str, str]

_CLAIMS = TypeAdapter(list[Claim])


@dataclass(frozen=True)
class Difference:
    """Two matched claims whose values differ."""

    a: Claim
    b: Claim


@dataclass(frozen=True)
class Comparison:
    """Matched claims, split into those that differ, and claims found in only one reading."""

    matched: int
    differing: list[Difference]
    only_a: list[Claim]
    only_b: list[Claim]

    @property
    def agrees(self) -> bool:
        return not (self.differing or self.only_a or self.only_b)


def claim_key(claim: Claim) -> ClaimKey:
    """What a claim measures: its identity when comparing readings."""
    return (
        claim.subject.value,
        claim.lookback_months,
        claim.top_n,
        claim.metric,
        claim.period_start,
        claim.period_end,
    )


def describe_key(key: ClaimKey) -> str:
    """A claim's key in words, for messages."""
    subject, lookback, top_n, metric, start, end = key
    parts = [subject]
    if lookback is not None:
        parts.append(f"lookback {lookback}")
    if top_n is not None:
        parts.append(f"top {top_n}")
    return f"{', '.join(parts)}, {metric}, {start} to {end}"


def locate(source: Source) -> str:
    """Where a value was read: page, section and locator, as far as they are known."""
    parts = [f"page {source.page}" if source.page is not None else None, source.section]
    parts.append(source.locator)
    return ", ".join(part for part in parts if part)


def load_claims(path: Path) -> list[Claim]:
    """Read the ``claims`` list of a YAML file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "claims" not in data:
        raise ValueError("expected a mapping with a 'claims' list")
    claims = _CLAIMS.validate_python(data["claims"])
    seen: set[ClaimKey] = set()
    for claim in claims:
        key = claim_key(claim)
        if key in seen:
            raise ValueError(f"{claim.id}: more than one claim for {describe_key(key)}")
        seen.add(key)
    return claims


def compare_claims(a: list[Claim], b: list[Claim]) -> Comparison:
    """Match claims on (subject, lookback_months, top_n, metric, period_start, period_end)."""
    by_key_b = {claim_key(claim): claim for claim in b}
    differing: list[Difference] = []
    only_a: list[Claim] = []
    matched = 0
    for claim in a:
        other = by_key_b.pop(claim_key(claim), None)
        if other is None:
            only_a.append(claim)
            continue
        matched += 1
        if claim.value != other.value:
            differing.append(Difference(claim, other))
    return Comparison(matched, differing, only_a, list(by_key_b.values()))
