import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from quaver.cli import main
from quaver.readings import (
    claim_key,
    compare_claims,
    describe_key,
    load_claims,
    locate,
)
from quaver.spec import Claim, Source

TEMPLATE = Path(__file__).parent.parent / "specs" / "TEMPLATE.yaml"

Data = dict[str, Any]


def template_claims() -> list[Data]:
    data: Data = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    return copy.deepcopy(data["claims"])


def write(path: Path, claims: list[Data], **extra: Any) -> Path:
    path.write_text(yaml.safe_dump({"claims": claims, **extra}), encoding="utf-8")
    return path


def claim(**overrides: Any) -> Claim:
    return Claim.model_validate({**template_claims()[2], **overrides})


# --- keys and labels ------------------------------------------------------------------------


def test_claim_key_ignores_id_value_and_source() -> None:
    a = claim(id="C3", value=4.2)
    b = claim(id="C99", value=9.9, statement="other words")
    assert claim_key(a) == claim_key(b)


@pytest.mark.parametrize(
    "override",
    [
        {"metric": "mean_monthly_return"},
        {"lookback_months": 6},
        {"top_n": 20},
        {"period_start": "1961-01"},
        {"period_end": "1989-12"},
        {"subject": "benchmark", "lookback_months": None, "top_n": None},
    ],
)
def test_claim_key_depends_on_what_is_measured(override: Data) -> None:
    assert claim_key(claim()) != claim_key(claim(**override))


def test_describe_key_strategy_and_benchmark() -> None:
    assert describe_key(claim_key(claim())) == (
        "strategy, lookback 12, top 10, annualised_volatility, 1960-01 to 1990-12"
    )
    benchmark = claim(subject="benchmark", lookback_months=None, top_n=None)
    assert describe_key(claim_key(benchmark)) == (
        "benchmark, annualised_volatility, 1960-01 to 1990-12"
    )


def test_locate() -> None:
    table = Source(kind="table", page=8, section="Exhibit 4.1", locator="row CAGR, column Top1")
    assert locate(table) == "page 8, Exhibit 4.1, row CAGR, column Top1"
    assert locate(Source(kind="assumed", reason="r")) == ""
    assert locate(Source(kind="inferred", page=3, reason="r")) == "page 3"


# --- compare_claims -------------------------------------------------------------------------


def test_compare_identical() -> None:
    result = compare_claims([claim()], [claim()])
    assert (result.matched, result.agrees) == (1, True)


def test_compare_matches_regardless_of_id_and_order() -> None:
    a = [claim(id="C1"), claim(id="C2", metric="mean_monthly_return", value=1.1)]
    b = [claim(id="C7", metric="mean_monthly_return", value=1.1), claim(id="C8")]
    result = compare_claims(a, b)
    assert (result.matched, result.agrees) == (2, True)


def test_compare_reports_differing_values() -> None:
    result = compare_claims([claim(id="C1", value=4.2)], [claim(id="C9", value=4.3)])
    assert result.matched == 1
    assert not result.agrees
    (diff,) = result.differing
    assert (diff.a.value, diff.b.value) == (4.2, 4.3)


def test_compare_reports_claims_in_only_one_reading() -> None:
    a = [claim(id="C1"), claim(id="C2", top_n=20)]
    b = [claim(id="C1"), claim(id="C5", lookback_months=6)]
    result = compare_claims(a, b)
    assert result.matched == 1
    assert [c.id for c in result.only_a] == ["C2"]
    assert [c.id for c in result.only_b] == ["C5"]
    assert not result.agrees


# --- load_claims ----------------------------------------------------------------------------


def test_load_claims_accepts_a_bare_claims_file(tmp_path: Path) -> None:
    path = write(tmp_path / "b.yaml", template_claims())
    assert [c.id for c in load_claims(path)] == ["C1", "C2", "C3"]


@pytest.mark.parametrize("content", ["- a\n", "title: x\n", ""])
def test_load_claims_needs_a_claims_list(tmp_path: Path, content: str) -> None:
    path = tmp_path / "b.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="expected a mapping with a 'claims' list"):
        load_claims(path)


def test_load_claims_rejects_two_claims_for_one_measurement(tmp_path: Path) -> None:
    twin = {**template_claims()[2], "id": "C4"}
    path = write(tmp_path / "b.yaml", [*template_claims(), twin])
    with pytest.raises(ValueError, match="C4: more than one claim for strategy, lookback 12"):
        load_claims(path)


def test_load_claims_validates_each_claim(tmp_path: Path) -> None:
    bad = {**template_claims()[0], "period_start": "1990-13"}
    with pytest.raises(ValidationError, match="not a YYYY-MM month"):
        load_claims(write(tmp_path / "b.yaml", [bad]))


# --- the CLI command ------------------------------------------------------------------------


def test_cli_agreeing_readings(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    a = write(tmp_path / "a.yaml", template_claims(), paper={"title": "ignored"})
    b = write(tmp_path / "b.yaml", template_claims())
    assert main(["compare-readings", str(a), str(b)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "matched 3 claims\n"
    assert captured.err == ""


def test_cli_a_full_spec_works_as_a_reading(capsys: pytest.CaptureFixture[str]) -> None:
    b = Path(__file__).parent / "fixtures" / "reading-b.yaml"
    assert main(["compare-readings", str(TEMPLATE), str(b)]) == 0
    assert capsys.readouterr().out == "matched 3 claims\n"


def test_cli_differences_and_missing_claims(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    claims_a = template_claims()
    claims_b = template_claims()
    claims_b[2]["value"] = 4.3
    claims_b[2]["id"] = "C10"
    del claims_b[0]
    claims_b.append({**claims_a[0], "id": "C11", "top_n": 20})
    a = write(tmp_path / "a.yaml", claims_a)
    b = write(tmp_path / "b.yaml", claims_b)
    assert main(["compare-readings", str(a), str(b)]) == 1
    captured = capsys.readouterr()
    where = "page 7, Table 1, row Top-decile 12-month, column Volatility"
    assert captured.out == (
        "matched 2 claims\n"
        "differs: strategy, lookback 12, top 10, annualised_volatility, 1960-01 to 1990-12\n"
        f"  A C3: 4.2 ({where})\n"
        f"  B C10: 4.3 ({where})\n"
        "only in A: C1, strategy, lookback 12, top 10, mean_monthly_return, 1960-01 to 1990-12\n"
        "only in B: C11, strategy, lookback 12, top 20, mean_monthly_return, 1960-01 to 1990-12\n"
    )
    assert captured.err == "1 differ, 1 only in A, 1 only in B\n"


def test_cli_one_matched_claim_is_singular(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    only = template_claims()[:1]
    a, b = write(tmp_path / "a.yaml", only), write(tmp_path / "b.yaml", only)
    assert main(["compare-readings", str(a), str(b)]) == 0
    assert capsys.readouterr().out == "matched 1 claim\n"


@pytest.mark.parametrize("which", ["a", "b"])
def test_cli_invalid_reading(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, which: str
) -> None:
    good = write(tmp_path / "good.yaml", template_claims())
    bad = tmp_path / "bad.yaml"
    bad.write_text("claims: [{id: C1}]\n", encoding="utf-8")
    paths = (good, bad) if which == "b" else (bad, good)
    assert main(["compare-readings", str(paths[0]), str(paths[1])]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("invalid readings\n0.subject: Field required")


@pytest.mark.parametrize(("content", "message"), [(None, "No such file"), ("a: [\n", "while")])
def test_cli_unreadable_reading(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, content: str | None, message: str
) -> None:
    good = write(tmp_path / "good.yaml", template_claims())
    bad = tmp_path / "bad.yaml"
    if content is not None:
        bad.write_text(content, encoding="utf-8")
    assert main(["compare-readings", str(good), str(bad)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("invalid readings\n")
    assert message in err
