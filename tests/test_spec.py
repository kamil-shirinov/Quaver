import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from quaver.spec import Claim, Paper, Provenance, Source, StrategySpec, load_spec, provenance_counts

TEMPLATE = Path(__file__).parent.parent / "specs" / "TEMPLATE.yaml"

Data = dict[str, Any]


def template_data() -> Data:
    data: Data = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    return copy.deepcopy(data)


def words(n: int) -> str:
    return " ".join(["word"] * n)


# --- Source ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "stated", "page": 1, "quote": "a short quote"},
        {"kind": "stated", "page": 5, "quote": words(25)},
        {"kind": "stated", "page": 5, "quote": "q", "section": "Data"},
        {"kind": "inferred", "page": 2, "reason": "implied by Table 1"},
        {"kind": "assumed", "reason": "the paper is silent"},
    ],
)
def test_source_valid(fields: Data) -> None:
    assert Source.model_validate(fields).kind == Provenance(fields["kind"])


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"kind": "stated", "quote": "q"}, "stated source needs page and quote"),
        ({"kind": "stated", "page": 1}, "stated source needs page and quote"),
        ({"kind": "stated", "page": 1, "quote": words(26)}, "longer than 25 words"),
        ({"kind": "inferred", "reason": "r"}, "inferred source needs page and reason"),
        ({"kind": "inferred", "page": 1}, "inferred source needs page and reason"),
        ({"kind": "assumed"}, "assumed source needs a reason"),
        ({"kind": "assumed", "reason": "r", "page": 3}, "must not have a page"),
        ({"kind": "stated", "page": 0, "quote": "q"}, "greater than or equal to 1"),
        ({"kind": "inferred", "page": -2, "reason": "r"}, "greater than or equal to 1"),
        ({"kind": "guessed", "reason": "r"}, "Input should be"),
    ],
)
def test_source_invalid(fields: Data, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Source.model_validate(fields)


def test_models_are_frozen() -> None:
    source = Source(kind=Provenance.ASSUMED, reason="r")
    with pytest.raises(ValidationError, match="frozen"):
        source.reason = "other"  # type: ignore[misc]


# --- Paper ----------------------------------------------------------------------------------


def paper_fields(sha: str) -> Data:
    return {
        "title": "T",
        "authors": ["A"],
        "year": 2000,
        "url": "https://example.com",
        "version": "January 2000",
        "pdf_sha256": sha,
    }


def test_paper_sha256_valid() -> None:
    assert Paper.model_validate(paper_fields("ab12" * 16)).year == 2000


@pytest.mark.parametrize("sha", ["ab12" * 15 + "ab1", "AB12" * 16, "zz12" * 16, "ab12" * 17])
def test_paper_sha256_invalid(sha: str) -> None:
    with pytest.raises(ValidationError, match="pdf_sha256"):
        Paper.model_validate(paper_fields(sha))


# --- Claim ----------------------------------------------------------------------------------


def claim_fields(**overrides: Any) -> Data:
    fields: Data = copy.deepcopy(template_data()["claims"][0])
    fields.update(overrides)
    return fields


@pytest.mark.parametrize("claim_id", ["C1", "C12", "C007"])
def test_claim_id_valid(claim_id: str) -> None:
    assert Claim.model_validate(claim_fields(id=claim_id)).id == claim_id


@pytest.mark.parametrize("claim_id", ["C", "X1", "c1", "C1a", " C1", "1"])
def test_claim_id_invalid(claim_id: str) -> None:
    with pytest.raises(ValidationError, match="String should match pattern"):
        Claim.model_validate(claim_fields(id=claim_id))


# --- YYYY-MM everywhere ---------------------------------------------------------------------


@pytest.mark.parametrize("month", ["1990-01", "1990-12", "2024-09"])
def test_year_month_valid(month: str) -> None:
    assert Claim.model_validate(claim_fields(period_start=month, period_end=month))


@pytest.mark.parametrize(
    "month", ["1990-13", "1990-00", "1990-1", "199-01", "1990/01", "1990-01-01"]
)
def test_year_month_invalid_in_claim(month: str) -> None:
    with pytest.raises(ValidationError, match="not a YYYY-MM month"):
        Claim.model_validate(claim_fields(period_start=month))
    with pytest.raises(ValidationError, match="not a YYYY-MM month"):
        Claim.model_validate(claim_fields(period_end=month))


@pytest.mark.parametrize("field", ["sample_start", "sample_end"])
def test_year_month_invalid_in_sample(field: str) -> None:
    data = template_data()
    data[field]["value"] = "1990-13"
    with pytest.raises(ValidationError, match="not a YYYY-MM month"):
        StrategySpec.model_validate(data)


# --- StrategySpec rules ---------------------------------------------------------------------


def test_template_loads() -> None:
    spec = load_spec(TEMPLATE)
    assert spec.paper.title == "Example Paper"
    assert spec.paper.year == 2000
    assert len(spec.claims) == 1


def test_sample_start_before_end() -> None:
    data = template_data()
    data["sample_start"]["value"] = "1989-12"
    data["sample_end"]["value"] = "1990-01"
    data["claims"][0].update(period_start="1989-12", period_end="1990-01")
    StrategySpec.model_validate(data)


@pytest.mark.parametrize(("start", "end"), [("1990-12", "1990-12"), ("1991-01", "1990-12")])
def test_sample_start_not_before_end(start: str, end: str) -> None:
    data = template_data()
    data["sample_start"]["value"] = start
    data["sample_end"]["value"] = end
    data["claims"] = []
    with pytest.raises(ValidationError, match="sample_start must be before sample_end"):
        StrategySpec.model_validate(data)


@pytest.mark.parametrize("field", ["lookbacks_months", "top_n"])
def test_int_lists_valid(field: str) -> None:
    data = template_data()
    data[field]["value"] = [1, 5, 100]
    data["claims"] = []
    assert StrategySpec.model_validate(data)


@pytest.mark.parametrize("field", ["lookbacks_months", "top_n"])
@pytest.mark.parametrize(
    ("values", "message"),
    [
        ([0, 6], "must be positive"),
        ([-3, 6], "must be positive"),
        ([6, 6, 12], "must be unique"),
        ([12, 6], "must be sorted ascending"),
    ],
)
def test_int_lists_invalid(field: str, values: list[int], message: str) -> None:
    data = template_data()
    data[field]["value"] = values
    data["claims"] = []
    with pytest.raises(ValidationError, match=message):
        StrategySpec.model_validate(data)


def test_claim_ids_unique() -> None:
    data = template_data()
    second = copy.deepcopy(data["claims"][0])
    second["id"] = "C2"
    data["claims"].append(second)
    assert len(StrategySpec.model_validate(data).claims) == 2
    second["id"] = "C1"
    with pytest.raises(ValidationError, match="claim ids must be unique"):
        StrategySpec.model_validate(data)


def test_claim_lookback_must_be_in_list() -> None:
    data = template_data()
    data["claims"][0]["lookback_months"] = 6
    StrategySpec.model_validate(data)
    data["claims"][0]["lookback_months"] = 7
    with pytest.raises(ValidationError, match=r"C1: lookback_months is not in lookbacks_months"):
        StrategySpec.model_validate(data)


def test_claim_top_n_must_be_in_list() -> None:
    data = template_data()
    data["claims"][0]["top_n"] = 20
    StrategySpec.model_validate(data)
    data["claims"][0]["top_n"] = 15
    with pytest.raises(ValidationError, match=r"C1: top_n is not in top_n"):
        StrategySpec.model_validate(data)


def test_claim_period_inside_sample() -> None:
    data = template_data()
    data["claims"][0].update(period_start="1960-01", period_end="1990-12")  # exactly the sample
    StrategySpec.model_validate(data)
    data["claims"][0].update(period_start="1970-01", period_end="1980-12")
    StrategySpec.model_validate(data)


@pytest.mark.parametrize(("start", "end"), [("1959-12", "1990-12"), ("1960-01", "1991-01")])
def test_claim_period_outside_sample(start: str, end: str) -> None:
    data = template_data()
    data["claims"][0].update(period_start=start, period_end=end)
    with pytest.raises(ValidationError, match="C1: period lies outside the sample"):
        StrategySpec.model_validate(data)


def test_all_problems_reported_together() -> None:
    data = template_data()
    data["claims"][0].update(lookback_months=7, top_n=15)
    with pytest.raises(ValidationError) as info:
        StrategySpec.model_validate(data)
    text = str(info.value)
    assert "lookback_months" in text
    assert "top_n is not in top_n" in text


# --- load_spec and provenance_counts --------------------------------------------------------


def test_load_spec_rejects_non_mapping(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_spec(path)


def test_provenance_counts_template() -> None:
    counts = provenance_counts(load_spec(TEMPLATE))
    assert counts == {Provenance.STATED: 10, Provenance.INFERRED: 2, Provenance.ASSUMED: 2}


def test_provenance_counts_includes_zero_entries() -> None:
    data = template_data()
    data["claims"] = []
    for field in data.values():
        if isinstance(field, dict) and "source" in field:
            field["source"] = {"kind": "assumed", "reason": "r"}
    counts = provenance_counts(StrategySpec.model_validate(data))
    assert counts == {Provenance.STATED: 0, Provenance.INFERRED: 0, Provenance.ASSUMED: 13}
