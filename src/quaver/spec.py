"""Strategy spec format: a paper's method, with a citation for every field."""

import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

MAX_QUOTE_WORDS = 25

_YEAR_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class Provenance(StrEnum):
    """Where a value in a spec came from."""

    STATED = "stated"
    INFERRED = "inferred"
    ASSUMED = "assumed"


def _check_year_month(value: str) -> str:
    if not _YEAR_MONTH.fullmatch(value):
        raise ValueError(f"{value!r} is not a YYYY-MM month")
    return value


def _check_month_list(values: list[int]) -> list[int]:
    if any(v < 1 for v in values):
        raise ValueError("values must be positive")
    if len(set(values)) != len(values):
        raise ValueError("values must be unique")
    if values != sorted(values):
        raise ValueError("values must be sorted ascending")
    return values


type YearMonth = Annotated[str, AfterValidator(_check_year_month)]
type PositiveAscendingInts = Annotated[list[int], AfterValidator(_check_month_list)]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class Source(_Frozen):
    """The origin of one value: a quote, an inference, or an assumption."""

    kind: Provenance
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    quote: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _check_kind_rules(self) -> Self:
        match self.kind:
            case Provenance.STATED:
                if self.page is None or self.quote is None:
                    raise ValueError("a stated source needs page and quote")
                if len(self.quote.split()) > MAX_QUOTE_WORDS:
                    raise ValueError(f"quote is longer than {MAX_QUOTE_WORDS} words")
            case Provenance.INFERRED:
                if self.page is None or self.reason is None:
                    raise ValueError("an inferred source needs page and reason")
            case Provenance.ASSUMED:
                if self.reason is None:
                    raise ValueError("an assumed source needs a reason")
                if self.page is not None:
                    raise ValueError("an assumed source must not have a page")
        return self


class Cited[T](_Frozen):
    """A value together with the source it came from."""

    value: T
    source: Source


class Paper(_Frozen):
    """The paper being replicated, identified down to the exact PDF."""

    title: str
    authors: list[str]
    year: int
    url: str
    version: str
    pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Claim(_Frozen):
    """One headline number the paper reports, to be checked by the replication."""

    id: str = Field(pattern=r"^C\d+$")
    statement: str
    metric: str
    lookback_months: int
    top_n: int
    period_start: YearMonth
    period_end: YearMonth
    value: float
    unit: str
    source: Source

    @model_validator(mode="after")
    def _check_period_order(self) -> Self:
        if self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end")
        return self


class StrategySpec(_Frozen):
    """A momentum strategy as written in a paper, every field cited."""

    paper: Paper
    universe: Cited[str]
    data_source: Cited[str]
    frequency: Cited[str]
    signal: Cited[str]
    weighting: Cited[str]
    rebalance: Cited[str]
    costs: Cited[str]
    benchmark: Cited[str]
    sample_start: Cited[YearMonth]
    sample_end: Cited[YearMonth]
    lookbacks_months: Cited[PositiveAscendingInts]
    top_n: Cited[PositiveAscendingInts]
    signal_lag_months: Cited[int]
    claims: list[Claim]

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        start, end = self.sample_start.value, self.sample_end.value
        problems: list[str] = []
        if start >= end:
            problems.append("sample_start must be before sample_end")
        ids = [claim.id for claim in self.claims]
        if len(set(ids)) != len(ids):
            problems.append("claim ids must be unique")
        for claim in self.claims:
            if claim.lookback_months not in self.lookbacks_months.value:
                problems.append(f"{claim.id}: lookback_months is not in lookbacks_months")
            if claim.top_n not in self.top_n.value:
                problems.append(f"{claim.id}: top_n is not in top_n")
            if claim.period_start < start or claim.period_end > end:
                problems.append(f"{claim.id}: period lies outside the sample")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def load_spec(path: Path) -> StrategySpec:
    """Read a YAML spec file and validate it."""
    return StrategySpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def provenance_counts(spec: StrategySpec) -> dict[Provenance, int]:
    """Count the sources of all cited fields and all claims, by provenance."""
    counts = dict.fromkeys(Provenance, 0)
    for name in type(spec).model_fields:
        field = getattr(spec, name)
        if isinstance(field, Cited):
            counts[field.source.kind] += 1
    for claim in spec.claims:
        counts[claim.source.kind] += 1
    return counts
