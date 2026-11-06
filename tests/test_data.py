import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from quaver.cli import main
from quaver.data import TITLE, DataError, French10, load_french10, sha256_of

FIXTURE = Path(__file__).parent / "fixtures" / "french10-small.csv"
INDUSTRIES = (
    "NoDur",
    "Durbl",
    "Manuf",
    "Enrgy",
    "HiTec",
    "Telcm",
    "Shops",
    "Hlth",
    "Utils",
    "Other",
)


def fixture_text() -> str:
    return FIXTURE.read_bytes().decode("utf-8")


def row_1() -> str:
    return next(line for line in fixture_text().split("\r\n") if line.startswith("199011"))


def pin_for(tmp_path: Path, csv_bytes: bytes) -> Path:
    pins = tmp_path / "pins.json"
    digest = hashlib.sha256(csv_bytes).hexdigest()
    pins.write_text(json.dumps({"french_10_industries": {"csv_sha256": digest}}), encoding="utf-8")
    return pins


def load_text(tmp_path: Path, text: str) -> French10:
    """Write text as the CSV, pin its own hash, and load it."""
    csv = tmp_path / "data.csv"
    csv.write_bytes(text.encode("utf-8"))
    return load_french10(csv, pin_for(tmp_path, csv.read_bytes()))


def test_loads_only_the_value_weighted_monthly_table(tmp_path: Path) -> None:
    data = load_text(tmp_path, fixture_text())
    assert data.months == ("1990-11", "1990-12", "1991-01", "1991-02")
    assert data.industries == INDUSTRIES
    assert data.returns.shape == (4, 10)
    assert data.returns.dtype == np.float64


def test_percent_is_converted_to_fractions(tmp_path: Path) -> None:
    data = load_text(tmp_path, fixture_text())
    np.testing.assert_array_equal(data.returns[0, :2], [-0.03, -0.0275])
    assert data.returns[1, 2] == 0.0
    assert data.returns[3, 9] == 0.0675


def test_returns_are_read_only(tmp_path: Path) -> None:
    data = load_text(tmp_path, fixture_text())
    with pytest.raises(ValueError, match="read-only"):
        data.returns[0, 0] = 1.0


def test_result_is_frozen(tmp_path: Path) -> None:
    data = load_text(tmp_path, fixture_text())
    with pytest.raises(AttributeError):
        data.months = ()  # type: ignore[misc]


def test_hash_mismatch_names_both_hashes(tmp_path: Path) -> None:
    csv = tmp_path / "data.csv"
    csv.write_bytes(fixture_text().encode("utf-8"))
    pins = pin_for(tmp_path, b"some other file")
    with pytest.raises(DataError) as info:
        load_french10(csv, pins)
    message = str(info.value)
    assert sha256_of(csv) in message
    assert hashlib.sha256(b"some other file").hexdigest() in message


def test_one_changed_byte_is_refused(tmp_path: Path) -> None:
    csv = tmp_path / "data.csv"
    original = fixture_text().encode("utf-8")
    pins = pin_for(tmp_path, original)
    csv.write_bytes(original.replace(b"-3.00", b"-3.01", 1))
    with pytest.raises(DataError, match="hash mismatch"):
        load_french10(csv, pins)


@pytest.mark.parametrize("content", ['{"other": {}}', "[]", '{"french_10_industries": {}}'])
def test_pin_without_hash_is_refused(tmp_path: Path, content: str) -> None:
    csv = tmp_path / "data.csv"
    csv.write_bytes(fixture_text().encode("utf-8"))
    pins = tmp_path / "pins.json"
    pins.write_text(content, encoding="utf-8")
    with pytest.raises(DataError, match="csv_sha256"):
        load_french10(csv, pins)


def test_pin_hash_must_be_a_string(tmp_path: Path) -> None:
    csv = tmp_path / "data.csv"
    csv.write_bytes(fixture_text().encode("utf-8"))
    pins = tmp_path / "pins.json"
    pins.write_text('{"french_10_industries": {"csv_sha256": 5}}', encoding="utf-8")
    with pytest.raises(DataError, match="csv_sha256"):
        load_french10(csv, pins)


def test_missing_title(tmp_path: Path) -> None:
    text = fixture_text().replace(TITLE, "Average Value Weighted Returns -- Weekly")
    with pytest.raises(DataError, match="not found"):
        load_text(tmp_path, text)


def test_title_without_header_row(tmp_path: Path) -> None:
    with pytest.raises(DataError, match="no header row"):
        load_text(tmp_path, f"  {TITLE}")


def test_wrong_number_of_columns(tmp_path: Path) -> None:
    text = fixture_text().replace(",Other\r\n", "\r\n", 1)
    with pytest.raises(DataError, match="expected 10 industry columns, found 9"):
        load_text(tmp_path, text)


def test_row_with_wrong_number_of_values(tmp_path: Path) -> None:
    text = fixture_text().replace(row_1(), row_1().rsplit(",", 1)[0])
    with pytest.raises(DataError, match="expected 10 values, found 9"):
        load_text(tmp_path, text)


def test_missing_month(tmp_path: Path) -> None:
    text = fixture_text().replace("199101,", "199102,", 1)
    with pytest.raises(DataError, match="expected month 1991-01, found 1991-02"):
        load_text(tmp_path, text)


def test_months_out_of_order(tmp_path: Path) -> None:
    text = fixture_text().replace("199012,", "199010,", 1)
    with pytest.raises(DataError, match="expected month 1990-12, found 1990-10"):
        load_text(tmp_path, text)


def test_repeated_month(tmp_path: Path) -> None:
    text = fixture_text().replace("199012,", "199011,", 1)
    with pytest.raises(DataError, match="expected month 1990-12, found 1990-11"):
        load_text(tmp_path, text)


def test_impossible_month(tmp_path: Path) -> None:
    text = fixture_text().replace("199011,", "199013,", 1)
    with pytest.raises(DataError, match="not a month"):
        load_text(tmp_path, text)


@pytest.mark.parametrize("bad", ["abc", "", "nan", "inf", "1.2.3"])
def test_value_that_is_not_a_number(tmp_path: Path, bad: str) -> None:
    text = fixture_text().replace("   -2.75,", f"{bad},", 1)
    with pytest.raises(DataError, match=r"Durbl.*is not a number"):
        load_text(tmp_path, text)


@pytest.mark.parametrize("code", ["-99.99", "-999", "-999.0"])
def test_missing_value_codes(tmp_path: Path, code: str) -> None:
    text = fixture_text().replace("   -2.75,", f"{code},", 1)
    with pytest.raises(DataError, match="missing-value code"):
        load_text(tmp_path, text)


def test_table_without_rows(tmp_path: Path) -> None:
    header = "," + ",".join(INDUSTRIES)
    with pytest.raises(DataError, match="no data rows"):
        load_text(tmp_path, f"  {TITLE}\r\n{header}\r\n\r\n")


def test_stops_at_first_line_that_is_not_a_row(tmp_path: Path) -> None:
    text = fixture_text()
    lines = text.split("\r\n")
    # A bad row after the blank line that ends the table must be ignored.
    index = lines.index(next(line for line in lines if line.startswith("199102")))
    lines.insert(index + 2, "199105,    abc")
    assert len(load_text(tmp_path, "\r\n".join(lines)).months) == 4


def test_tolerates_lf_line_endings(tmp_path: Path) -> None:
    data = load_text(tmp_path, fixture_text().replace("\r\n", "\n"))
    assert len(data.months) == 4


def test_data_check_prints_one_line(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    csv = tmp_path / "data.csv"
    csv.write_bytes(FIXTURE.read_bytes())
    pins = pin_for(tmp_path, csv.read_bytes())
    assert main(["data-check", "--csv", str(csv), "--pins", str(pins)]) == 0
    captured = capsys.readouterr()
    assert captured.out == (
        "data.csv: 4 months, 1990-11 to 1991-02, 10 industries, no missing values\n"
    )
    assert captured.err == ""


def test_data_check_reports_hash_mismatch(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    csv = tmp_path / "data.csv"
    csv.write_bytes(FIXTURE.read_bytes())
    pins = pin_for(tmp_path, b"other")
    assert main(["data-check", "--csv", str(csv), "--pins", str(pins)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "hash mismatch" in captured.err


def test_data_check_reports_missing_file(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    pins = pin_for(tmp_path, b"other")
    assert main(["data-check", "--csv", str(tmp_path / "nope.csv"), "--pins", str(pins)]) == 1
    assert capsys.readouterr().err.startswith("invalid:")
