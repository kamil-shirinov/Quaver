from pathlib import Path
from typing import Any

import pytest
import yaml

from quaver.cli import main

TEMPLATE = Path(__file__).parent.parent / "specs" / "TEMPLATE.yaml"
FIXTURE = Path(__file__).parent / "fixtures" / "example-paper.txt"


def write_spec(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def template_data() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    return data


def test_validate_spec_success(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    assert main(["validate-spec", str(path)]) == 0
    out = capsys.readouterr().out
    assert out == (
        "valid: Example Paper (2000), 3 claims, sources: 11 stated, 3 inferred, 3 assumed, "
        "1 table\n"
    )


def test_validate_spec_single_claim(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    data = template_data()
    data["claims"] = data["claims"][:1]
    assert main(["validate-spec", str(write_spec(tmp_path, data))]) == 0
    assert "), 1 claim, sources:" in capsys.readouterr().out


def test_validate_spec_unverified(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    data = template_data()
    data["extraction"]["verified_by"] = None
    assert main(["validate-spec", str(write_spec(tmp_path, data))]) == 0
    assert capsys.readouterr().out == (
        "valid: Example Paper (2000), 3 claims, sources: 11 stated, 3 inferred, 3 assumed, "
        "1 table, unverified\n"
    )


def test_validate_spec_invalid_content(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    text = TEMPLATE.read_text(encoding="utf-8").replace('value: "1960-01"', 'value: "1960-13"')
    path.write_text(text, encoding="utf-8")
    assert main(["validate-spec", str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"invalid: {path}" in captured.err
    assert "sample_start.value: Value error, '1960-13' is not a YYYY-MM month" in captured.err


def test_validate_spec_root_not_a_mapping(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    assert main(["validate-spec", str(path)]) == 1
    assert "<root>" in capsys.readouterr().err


def test_validate_spec_missing_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"
    assert main(["validate-spec", str(path)]) == 1
    assert "No such file" in capsys.readouterr().err


def test_validate_spec_broken_yaml(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text("key: [unclosed\n", encoding="utf-8")
    assert main(["validate-spec", str(path)]) == 1
    assert "invalid:" in capsys.readouterr().err


def test_no_subcommand_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as info:
        main([])
    assert info.value.code == 2


# --- check-quotes ---------------------------------------------------------------------------


def test_check_quotes_template_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check-quotes", str(TEMPLATE), str(FIXTURE)]) == 0
    assert capsys.readouterr().out == (
        "all 11 quotes found, 1 table value skipped (not quotable)\n"
    )


def test_check_quotes_reports_each_failure(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    data = template_data()
    data["universe"]["source"]["page"] = 4  # right quote, wrong page
    data["claims"][1]["source"]["quote"] = "earns 0.9 percent per month."  # not verbatim
    assert main(["check-quotes", str(write_spec(tmp_path, data)), str(FIXTURE)]) == 1
    captured = capsys.readouterr()
    assert captured.out == (
        "not found: universe, page 4: "
        "'We use all common stocks listed on the Example Exchange.'\n"
        "not found: C2, page 7: 'earns 0.9 percent per month.'\n"
    )
    assert captured.err == "2 of 11 quotes not found\n"


def test_check_quotes_quote_without_page(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    data = template_data()
    data["costs"]["source"]["quote"] = "Each portfolio is equally weighted."
    assert main(["check-quotes", str(write_spec(tmp_path, data)), str(FIXTURE)]) == 1
    assert "not found: costs, no page: 'Each portfolio is equally weighted.'" in (
        capsys.readouterr().out
    )


def test_check_quotes_page_missing_from_text(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    data = template_data()
    data["weighting"]["source"]["page"] = 99
    assert main(["check-quotes", str(write_spec(tmp_path, data)), str(FIXTURE)]) == 1
    assert "not found: weighting, page 99:" in capsys.readouterr().out


def test_check_quotes_invalid_spec(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text("- a\n", encoding="utf-8")
    assert main(["check-quotes", str(path), str(FIXTURE)]) == 1
    assert f"invalid: {path}" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (None, "No such file"),
        ("no markers here\n", "no '=== page N ===' markers found"),
    ],
)
def test_check_quotes_bad_text(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, content: str | None, message: str
) -> None:
    text = tmp_path / "paper.txt"
    if content is not None:
        text.write_text(content, encoding="utf-8")
    assert main(["check-quotes", str(TEMPLATE), str(text)]) == 1
    err = capsys.readouterr().err
    assert f"invalid: {text}" in err
    assert message in err
