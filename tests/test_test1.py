"""Test 1 runner tests.

Everything here is made up: a 48-month dataset in the layout of French's file, a spec generated
on it, and a throwaway git repository for each test. The real data and the real spec are never
read, and the real test never runs.
"""

import hashlib
import json
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from quaver import metrics
from quaver.cli import main
from quaver.data import French10, load_french10
from quaver.faber import Weights, benchmark_returns, version_returns
from quaver.test1 import (
    AMENDMENT_01,
    CSV,
    INCONCLUSIVE,
    OUT_DIR,
    PARTLY_MIN,
    PINS,
    PREREG,
    REPRODUCED_MIN,
    SPEC,
    STRATEGY_CLAIMS,
    TOLERANCES,
    UNITS,
    RunRefused,
    is_within,
    metric_value,
    render_report,
    run_test1,
    verdict,
)

TEMPLATE = Path(__file__).parent.parent / "specs" / "TEMPLATE.yaml"
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
N_MONTHS = 48  # 1999-01 to 2002-12: a year of history, then three calendar years of holdings
FIRST, LAST = "2000-01", "2002-12"
LOOKBACKS = [1, 3, 6, 9, 12]
TOP_N = list(range(1, 10))
STRATEGY_METRICS = ("CAGR", "volatility", "Sharpe ratio", "max drawdown")
BENCHMARK_METRICS = (*STRATEGY_METRICS, "best year", "worst year", "turnover")

Row = dict[str, Any]
Shift = Callable[[Row], float]


def csv_bytes() -> bytes:
    values = np.random.default_rng(11).uniform(-8.0, 10.0, size=(N_MONTHS, len(INDUSTRIES)))
    lines = [
        "Made-up data in the layout of French's file. Not real data.",
        "",
        "  Average Value Weighted Returns -- Monthly",
        "," + ",".join(INDUSTRIES),
    ]
    for k, row in enumerate(values):
        lines.append(f"{1999 + k // 12}{k % 12 + 1:02d}," + ",".join(f"{v:8.2f}" for v in row))
    lines += ["", "Copyright 2000 Nobody", ""]
    return "\r\n".join(lines).encode("utf-8")


CSV_BYTES = csv_bytes()
PIN = {
    "french_10_industries": {
        "csv_sha256": hashlib.sha256(CSV_BYTES).hexdigest(),
        "zip_sha256": "0" * 64,
        "downloaded": "2000-01-01",
    }
}


@pytest.fixture(scope="module")
def data(tmp_path_factory: pytest.TempPathFactory) -> French10:
    folder = tmp_path_factory.mktemp("data")
    (folder / "data.csv").write_bytes(CSV_BYTES)
    (folder / "pins.json").write_text(json.dumps(PIN), encoding="utf-8")
    return load_french10(folder / "data.csv", folder / "pins.json")


def ours(data: French10, row: Row, weights: Weights = "reset", ddof: int = 1) -> float:
    if row["subject"] == "benchmark":
        returns = benchmark_returns(data, FIRST, LAST)
        start = data.months.index(FIRST)
        months = data.months[start : start + len(returns)]
    else:
        version = version_returns(data, row["lookback_months"], row["top_n"], FIRST, LAST, weights)
        returns, months = version.returns, version.months
    return metric_value(row["metric"], returns, months, ddof)


def claim_rows() -> list[Row]:
    rows: list[Row] = [
        {"subject": "strategy", "metric": metric, "lookback_months": lookback, "top_n": top_n}
        for lookback in LOOKBACKS
        for top_n in TOP_N
        for metric in STRATEGY_METRICS
    ]
    rows += [
        {"subject": "benchmark", "metric": metric, "lookback_months": None, "top_n": None}
        for metric in BENCHMARK_METRICS
    ]
    for k, row in enumerate(rows, start=1):
        row.update(
            id=f"C{k}",
            statement="Made up.",
            period_start=FIRST,
            period_end=LAST,
            unit=UNITS.get(row["metric"], "%"),
            source={"kind": "table", "page": 1, "section": "Table 1", "locator": "made up"},
        )
    return rows


def no_shift(row: Row) -> float:
    return 0.0


def spec_data(data: French10, shift: Shift = no_shift) -> dict[str, Any]:
    """A valid spec whose "paper" values are ours rounded to two decimals, plus ``shift``."""
    spec: dict[str, Any] = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    made_up = {"kind": "assumed", "reason": "Made up."}
    spec["sample_start"] = {"value": FIRST, "source": made_up}
    spec["sample_end"] = {"value": LAST, "source": made_up}
    spec["lookbacks_months"] = {"value": LOOKBACKS, "source": made_up}
    spec["top_n"] = {"value": TOP_N, "source": made_up}
    spec["metrics"] = {m: {"value": "Made up.", "source": made_up} for m in BENCHMARK_METRICS}
    claims = claim_rows()
    for row in claims:
        paper = 0.0 if row["metric"] == "turnover" else round(ours(data, row), 2)
        row["value"] = paper + shift(row)
    spec["claims"] = claims
    return spec


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def commit_all(repo: Path, message: str = "Change") -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def write_locks(prereg: Path) -> None:
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}"
        for p in sorted(prereg.glob("*.md"))
    ]
    (prereg / "LOCKS.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_spec(repo: Path, spec: dict[str, Any]) -> None:
    (repo / SPEC).write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")


def make_repo(
    tmp_path: Path, data: French10, shift: Shift = no_shift, *, amendment: bool = True
) -> Path:
    repo = tmp_path / "repo"
    for folder in ("src", "prereg", "specs", "data/raw"):
        (repo / folder).mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    (repo / ".gitignore").write_text("data/raw/\n", encoding="utf-8")
    (repo / "src" / "code.py").write_text("# Made up.\n", encoding="utf-8")
    (repo / PREREG).write_text("# Made-up pre-registration\n", encoding="utf-8")
    if amendment:
        (repo / AMENDMENT_01).write_text("# Made-up amendment\n", encoding="utf-8")
    write_locks(repo / "prereg")
    write_spec(repo, spec_data(data, shift))
    (repo / CSV).write_bytes(CSV_BYTES)
    (repo / PINS).write_text(json.dumps(PIN), encoding="utf-8")
    commit_all(repo, "Set up")
    return repo


def result_of(repo: Path, name: str = "result.json") -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((repo / OUT_DIR / name).read_text(encoding="utf-8"))
    return loaded


def report_of(repo: Path) -> str:
    return (repo / OUT_DIR / "REPORT.md").read_text(encoding="utf-8")


def out_by(metric: str, amount: float = 2.0) -> Callable[[Row], float]:
    """A shift that puts every claim of ``metric`` ``amount`` tolerances away from ours."""
    return lambda row: amount * TOLERANCES[row["metric"]] if row["metric"] == metric else 0.0


# --- Pure rules ---------------------------------------------------------------------------------


def test_tolerances_are_the_preregistered_ones() -> None:
    assert TOLERANCES == {
        "CAGR": 0.50,
        "volatility": 0.50,
        "Sharpe ratio": 0.03,
        "max drawdown": 2.0,
        "best year": 1.0,
        "worst year": 1.0,
    }
    assert (STRATEGY_CLAIMS, REPRODUCED_MIN, PARTLY_MIN) == (180, 162, 90)


@pytest.mark.parametrize(
    ("difference", "tolerance", "expected"),
    [
        (0.0, 0.50, True),
        (0.50, 0.50, True),
        (-0.50, 0.50, True),
        (12.13 - 12.63, 0.50, True),  # exactly the tolerance, up to floating-point error
        (0.37 - 0.40, 0.03, True),
        (0.5001, 0.50, False),
        (-0.5001, 0.50, False),
        (0.031, 0.03, False),
        (-2.01, 2.0, False),
        (2.0, 2.0, True),
        (1.0, 1.0, True),
        (1.001, 1.0, False),
    ],
)
def test_tolerance_edges(difference: float, tolerance: float, expected: bool) -> None:
    assert is_within(difference, tolerance) is expected


@pytest.mark.parametrize(
    ("passed", "within", "expected"),
    [
        (True, 180, "reproduced"),
        (True, 162, "reproduced"),
        (True, 161, "partly reproduced"),
        (True, 90, "partly reproduced"),
        (True, 89, "not reproduced"),
        (True, 0, "not reproduced"),
        (False, 180, INCONCLUSIVE),
        (False, 0, INCONCLUSIVE),
    ],
)
def test_verdict_bands(passed: bool, within: int, expected: str) -> None:
    assert verdict(passed, within) == expected


def test_units_are_percent_except_sharpe(data: French10) -> None:
    version = version_returns(data, 3, 2, FIRST, LAST)
    r, months = version.returns, version.months
    assert metric_value("CAGR", r, months) == pytest.approx(100 * metrics.cagr(r))
    assert metric_value("volatility", r, months) == pytest.approx(100 * metrics.volatility(r))
    assert metric_value("volatility", r, months, ddof=0) == pytest.approx(
        100 * metrics.volatility(r, ddof=0)
    )
    assert metric_value("Sharpe ratio", r, months) == pytest.approx(metrics.sharpe_paper(r))
    drawdown = metric_value("max drawdown", r, months)
    assert drawdown == pytest.approx(100 * metrics.max_drawdown(r))
    assert drawdown < 0
    worst = metric_value("worst year", r, months)
    assert worst == pytest.approx(100 * metrics.worst_year(r, months))
    assert metric_value("best year", r, months) == pytest.approx(100 * metrics.best_year(r, months))
    assert worst < metric_value("best year", r, months)


def test_unknown_metric_is_refused(data: French10) -> None:
    version = version_returns(data, 1, 1, FIRST, LAST)
    with pytest.raises(ValueError, match="no rule for metric 'turnover'"):
        metric_value("turnover", version.returns, version.months)


# --- A full run ---------------------------------------------------------------------------------


def test_reproduced(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data)
    outcome = run_test1(repo)
    assert (outcome.verdict, outcome.within, outcome.total) == ("reproduced", 180, 180)
    assert outcome.result_path == repo / OUT_DIR / "result.json"
    result = result_of(repo)
    assert result["verdict"] == "reproduced"
    assert result["data_check"]["passed"] is True
    assert len(result["claims"]) == 186
    assert result["not_tested"] == [{"id": "C187", "metric": "turnover"}]
    assert all(c["metric"] != "turnover" for c in result["claims"])
    assert result["strategy_claims"]["by_metric"] == {
        m: {"within": 45, "of": 45} for m in STRATEGY_METRICS
    }
    first = result["claims"][0]
    assert set(first) == {
        "id",
        "subject",
        "lookback",
        "top_n",
        "metric",
        "period_start",
        "period_end",
        "paper",
        "ours",
        "difference",
        "tolerance",
        "within",
    }
    assert (first["id"], first["lookback"], first["top_n"], first["metric"]) == ("C1", 1, 1, "CAGR")
    assert first["difference"] == pytest.approx(first["ours"] - first["paper"])
    head = git(repo, "rev-parse", "HEAD").strip()
    assert result["commits"] == {
        "preregistration": head,
        "amendment_01": head,
        "spec": head,
        "code": head,
    }
    assert result["preregistration_files"] == {
        name: {
            "sha256": hashlib.sha256((repo / name).read_bytes()).hexdigest(),
            "commit": head,
        }
        for name in (AMENDMENT_01, PREREG)
    }
    assert result["data"]["csv_sha256"] == PIN["french_10_industries"]["csv_sha256"]
    assert result["data"]["pinned_csv_sha256"] == PIN["french_10_industries"]["csv_sha256"]
    assert result["data"]["zip_sha256"] == "0" * 64
    assert result["rerun"] is None
    assert datetime.fromisoformat(result["run_at_utc"]).utcoffset() is not None
    report = report_of(repo)
    assert report.startswith(
        "# Test 1 (reproduce): Example Paper (2000)\n\n**Verdict: reproduced.**"
    )
    assert " ✗**" not in report  # no marked cell
    sha = result["preregistration_files"][PREREG]["sha256"]
    assert "- Locked pre-registration files:\n  - `prereg/" in report
    assert f"  - `{PREREG}`: commit `{head}`, SHA-256 `{sha}`" in report


def test_each_claim_uses_its_own_version(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data)
    run_test1(repo)
    for claim in result_of(repo)["claims"]:
        row = {"subject": claim["subject"], "metric": claim["metric"]}
        row |= {"lookback_months": claim["lookback"], "top_n": claim["top_n"]}
        assert claim["ours"] == pytest.approx(ours(data, row))


def first_out(k: int) -> Shift:
    """A shift that puts the first ``k`` strategy claims (C1 to Ck) out of tolerance."""

    def shift(row: Row) -> float:
        out = row["subject"] == "strategy" and int(row["id"][1:]) <= k
        return 2 * TOLERANCES[row["metric"]] if out else 0.0

    return shift


@pytest.mark.parametrize(
    ("k", "expected"),
    [
        (18, "reproduced"),
        (19, "partly reproduced"),
        (90, "partly reproduced"),
        (91, "not reproduced"),
        (180, "not reproduced"),
    ],
)
def test_verdict_bands_end_to_end(tmp_path: Path, data: French10, k: int, expected: str) -> None:
    repo = make_repo(tmp_path, data, first_out(k))
    outcome = run_test1(repo)
    assert (outcome.verdict, outcome.within) == (expected, 180 - k)
    assert result_of(repo)["verdict"] == expected
    assert sum(not c["within"] for c in result_of(repo)["claims"]) == k


def test_paper_values_off_in_both_directions(tmp_path: Path, data: French10) -> None:
    def shift(row: Row) -> float:
        if row["subject"] != "strategy" or row["top_n"] != 1:
            return 0.0
        return (1.5 if row["lookback_months"] % 2 else -1.5) * TOLERANCES[row["metric"]]

    repo = make_repo(tmp_path, data, shift)
    assert run_test1(repo).within == 160
    differences = [c["difference"] for c in result_of(repo)["claims"] if not c["within"]]
    assert min(differences) < 0 < max(differences)


@pytest.mark.parametrize("metric", ["CAGR", "volatility"])
def test_data_check_failure_is_inconclusive(tmp_path: Path, data: French10, metric: str) -> None:
    def shift(row: Row) -> float:
        return 0.6 if row["subject"] == "benchmark" and row["metric"] == metric else 0.0

    repo = make_repo(tmp_path, data, shift)
    outcome = run_test1(repo)
    assert (outcome.verdict, outcome.within) == (INCONCLUSIVE, 180)
    result = result_of(repo)
    assert result["data_check"]["passed"] is False
    assert result["data_check"][metric]["within"] is False
    assert len(result["claims"]) == 186  # everything is still reported
    report = report_of(repo)
    assert f"**Verdict: {INCONCLUSIVE}.**" in report
    assert "Data check, benchmark: **failed**" in report


def test_other_benchmark_claims_do_not_decide_the_data_check(
    tmp_path: Path, data: French10
) -> None:
    # Benchmark Sharpe, drawdown, best and worst year are off; CAGR and volatility are not.
    def shift(row: Row) -> float:
        off = row["metric"] not in ("CAGR", "volatility", "turnover")
        return 5.0 if row["subject"] == "benchmark" and off else 0.0

    repo = make_repo(tmp_path, data, shift)
    assert run_test1(repo).verdict == "reproduced"
    bench = [c for c in result_of(repo)["claims"] if c["subject"] == "benchmark"]
    assert [c["within"] for c in bench] == [True, True, False, False, False, False]
    assert "| **no** |" in report_of(repo)


def test_report_marks_cells_out_of_tolerance(tmp_path: Path, data: French10) -> None:
    def shift(row: Row) -> float:
        hit = row["metric"] == "max drawdown" and (row["lookback_months"], row["top_n"]) == (6, 4)
        return 2.5 if hit else 0.0

    repo = make_repo(tmp_path, data, shift)
    run_test1(repo)
    report = report_of(repo)
    section = report.split("### max drawdown (tolerance 2.00 pp)")[1].split("###")[0]
    row_6 = next(line for line in section.splitlines() if line.startswith("| 6 mo |"))
    cells = [cell.strip() for cell in row_6.strip("|").split("|")]
    assert cells[4].startswith("**-2.5") and cells[4].endswith(" ✗**")
    assert report.count("✗") == 2  # the cell and the legend
    assert "### Sharpe ratio (tolerance 0.030)" in report
    assert "| Lookback | Top1 | Top2 | Top3 | Top4 | Top5 | Top6 | Top7 | Top8 | Top9 |" in report


def test_report_grid_shows_a_dash_for_a_missing_claim(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data)
    run_test1(repo)
    result = result_of(repo)
    result["claims"] = [c for c in result["claims"] if c["id"] != "C1"]
    section = render_report(result).split("### CAGR")[1].split("###")[0]
    assert "| 1 mo | — |" in section


def test_sensitivity_counts(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data)
    run_test1(repo)
    rows = [row for row in claim_rows() if row["subject"] == "strategy"]
    papers = {c["id"]: c["paper"] for c in result_of(repo)["claims"]}
    sensitivity = result_of(repo)["sensitivity"]
    checks: tuple[tuple[str, Weights, int], ...] = (
        ("drift_weights", "drift", 1),
        ("volatility_ddof_0", "reset", 0),
    )
    for key, weights, ddof in checks:
        by_metric = {m: 0 for m in STRATEGY_METRICS}
        for row in rows:
            difference = ours(data, row, weights, ddof) - papers[row["id"]]
            by_metric[row["metric"]] += is_within(difference, TOLERANCES[row["metric"]])
        assert sensitivity[key]["of"] == 180
        assert sensitivity[key]["within"] == sum(by_metric.values())
        assert {m: c["within"] for m, c in sensitivity[key]["by_metric"].items()} == by_metric
    # ddof changes only volatility and the Sharpe ratio.
    ddof0 = sensitivity["volatility_ddof_0"]["by_metric"]
    assert ddof0["CAGR"]["within"] == ddof0["max drawdown"]["within"] == 45
    assert "| Drift weights |" in report_of(repo)


def test_sensitivity_moves_with_the_paper_value(tmp_path: Path, data: French10) -> None:
    """Paper volatility 0.49 pp below our ddof=0 value: only the ddof=0 check passes all 45.

    ddof=1 always gives the larger value, so with ddof=1 every difference is above 0.49 pp.
    """

    def shift(row: Row) -> float:
        if row["subject"] != "strategy" or row["metric"] != "volatility":
            return 0.0
        return ours(data, row, ddof=0) - 0.49 - round(ours(data, row), 2)

    repo = make_repo(tmp_path, data, shift)
    run_test1(repo)
    sensitivity = result_of(repo)["sensitivity"]["volatility_ddof_0"]["by_metric"]
    main_counts = result_of(repo)["strategy_claims"]["by_metric"]
    assert sensitivity["volatility"]["within"] == 45
    assert main_counts["volatility"]["within"] == 0


def test_beat_benchmark_shares(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data)
    run_test1(repo)
    beat = result_of(repo)["beat_benchmark"]
    assert (beat["first"], beat["last"]) == (FIRST, LAST)
    assert [(v["lookback"], v["top_n"]) for v in beat["versions"]] == [
        (lb, n) for lb in LOOKBACKS for n in TOP_N
    ]
    bench = metrics.calendar_year_returns(benchmark_returns(data, FIRST, LAST), data.months[12:])
    for v in beat["versions"]:
        version = version_returns(data, v["lookback"], v["top_n"], FIRST, LAST)
        years = metrics.calendar_year_returns(version.returns, version.months)
        expected = sum(years[y] > bench[y] for y in years)
        assert (v["years"], v["beat"]) == (3, expected)
        assert v["share"] == pytest.approx(expected / 3)
    assert "Calendar years 2000 to 2002 (3 years)" in report_of(repo)


# --- Guards -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["src/new.py", "src/code.py", PREREG, "prereg/0002-new.md", SPEC, "specs/other.yaml", PINS],
)
def test_uncommitted_changes_are_refused(tmp_path: Path, data: French10, path: str) -> None:
    repo = make_repo(tmp_path, data)
    target = repo / path
    target.write_text(
        (target.read_text(encoding="utf-8") if target.exists() else "") + "\n", encoding="utf-8"
    )
    with pytest.raises(RunRefused, match="uncommitted changes in src, prereg, specs") as info:
        run_test1(repo)
    assert path in str(info.value)
    assert not (repo / OUT_DIR).exists()


def test_changes_elsewhere_are_allowed(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data)
    (repo / "notes.txt").write_text("scratch\n", encoding="utf-8")
    (repo / "data" / "README.md").write_text("scratch\n", encoding="utf-8")
    assert run_test1(repo).verdict == "reproduced"


def test_not_a_git_repository(tmp_path: Path) -> None:
    with pytest.raises(RunRefused, match="git status --porcelain"):
        run_test1(tmp_path)


def test_failing_prereg_lock_is_refused(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data)
    (repo / PREREG).write_text("# Made-up pre-registration, edited\n", encoding="utf-8")
    commit_all(repo, "Edit a locked file")
    with pytest.raises(RunRefused, match=r"lock fails: 0001-faber-2010\.md has changed"):
        run_test1(repo)


def test_uncommitted_amendment_is_refused(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data, amendment=False)
    with pytest.raises(RunRefused, match=f"{AMENDMENT_01} has never been committed"):
        run_test1(repo)


def test_data_not_matching_pin_is_refused(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data)
    (repo / CSV).write_bytes(CSV_BYTES.replace(b"Not real data.", b"Not real data!"))
    with pytest.raises(RunRefused, match=r"does not match its pin: .*hash mismatch"):
        run_test1(repo)


def test_missing_data_is_refused(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data)
    (repo / CSV).unlink()
    with pytest.raises(RunRefused, match=r"does not match its pin: .*No such file"):
        run_test1(repo)


def test_invalid_spec_is_refused(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data)
    (repo / SPEC).write_text("claims: [unclosed\n", encoding="utf-8")
    commit_all(repo)
    with pytest.raises(RunRefused, match="is not valid"):
        run_test1(repo)


def edited_spec(tmp_path: Path, data: French10, edit: Callable[[dict[str, Any]], None]) -> Path:
    repo = make_repo(tmp_path, data)
    spec = spec_data(data)
    edit(spec)
    write_spec(repo, spec)
    commit_all(repo)
    return repo


def test_metric_without_tolerance_is_refused(tmp_path: Path, data: French10) -> None:
    def edit(spec: dict[str, Any]) -> None:
        spec["metrics"]["alpha"] = spec["metrics"]["CAGR"]
        spec["claims"][-1]["metric"] = "alpha"

    repo = edited_spec(tmp_path, data, edit)
    with pytest.raises(RunRefused, match="C187: no pre-registered tolerance for 'alpha'"):
        run_test1(repo)


def test_wrong_unit_is_refused(tmp_path: Path, data: French10) -> None:
    def edit(spec: dict[str, Any]) -> None:
        spec["claims"][0]["unit"] = "fraction"

    repo = edited_spec(tmp_path, data, edit)
    with pytest.raises(RunRefused, match="C1: unit 'fraction', expected '% per year' for CAGR"):
        run_test1(repo)


def test_wrong_number_of_strategy_claims_is_refused(tmp_path: Path, data: French10) -> None:
    def edit(spec: dict[str, Any]) -> None:
        del spec["claims"][0]

    repo = edited_spec(tmp_path, data, edit)
    with pytest.raises(RunRefused, match="defined for 180 strategy claims; the spec has 179"):
        run_test1(repo)


@pytest.mark.parametrize(("metric", "found"), [("CAGR", 0), ("volatility", 2)])
def test_data_check_needs_one_benchmark_claim(
    tmp_path: Path, data: French10, metric: str, found: int
) -> None:
    def edit(spec: dict[str, Any]) -> None:
        bench = [c for c in spec["claims"] if c["subject"] == "benchmark"]
        if found == 0:
            spec["claims"].remove(next(c for c in bench if c["metric"] == metric))
        else:
            twin = dict(next(c for c in bench if c["metric"] == metric), id="C999")
            spec["claims"].append(twin)

    repo = edited_spec(tmp_path, data, edit)
    with pytest.raises(RunRefused, match=f"one benchmark {metric} claim, found {found}"):
        run_test1(repo)


def test_spec_without_turnover_claim(tmp_path: Path, data: French10) -> None:
    def edit(spec: dict[str, Any]) -> None:
        spec["claims"] = [c for c in spec["claims"] if c["metric"] != "turnover"]

    repo = edited_spec(tmp_path, data, edit)
    run_test1(repo)
    assert result_of(repo)["not_tested"] == []
    assert "Not tested, as pre-registered: none." in report_of(repo)


# --- Running once ---------------------------------------------------------------------------


def test_second_run_is_refused(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data)
    run_test1(repo)
    before = (repo / OUT_DIR / "result.json").read_bytes()
    with pytest.raises(
        RunRefused, match=r'already exists and Test 1 runs once\. .*--rerun "<reason>"'
    ):
        run_test1(repo)
    assert (repo / OUT_DIR / "result.json").read_bytes() == before


@pytest.mark.parametrize("reason", ["", "   "])
def test_rerun_needs_a_reason(tmp_path: Path, data: French10, reason: str) -> None:
    repo = make_repo(tmp_path, data)
    run_test1(repo)
    with pytest.raises(RunRefused, match="--rerun needs a reason"):
        run_test1(repo, rerun=reason)


def test_rerun_keeps_the_old_results(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data)
    run_test1(repo)
    first = (repo / OUT_DIR / "result.json").read_bytes()
    first_report = (repo / OUT_DIR / "REPORT.md").read_bytes()
    run_test1(repo, rerun="crashed while writing")
    assert (repo / OUT_DIR / "result-1.json").read_bytes() == first
    assert (repo / OUT_DIR / "REPORT-1.md").read_bytes() == first_report
    assert result_of(repo)["rerun"] == {
        "reason": "crashed while writing",
        "previous": "result-1.json",
    }
    assert "Rerun. Reason: crashed while writing. Previous result: result-1.json." in report_of(
        repo
    )
    run_test1(repo, rerun="again")
    assert result_of(repo, "result-2.json")["rerun"]["reason"] == "crashed while writing"
    assert result_of(repo)["rerun"]["previous"] == "result-2.json"


def test_rerun_numbering_skips_taken_numbers(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data)
    run_test1(repo)
    (repo / OUT_DIR / "REPORT.md").unlink()
    (repo / OUT_DIR / "result-3.json").write_text("{}", encoding="utf-8")
    (repo / OUT_DIR / "result-x.json").write_text("{}", encoding="utf-8")
    run_test1(repo, rerun="numbering")
    assert (repo / OUT_DIR / "result-4.json").exists()
    assert not (repo / OUT_DIR / "REPORT-4.md").exists()


def test_rerun_without_an_earlier_result(tmp_path: Path, data: French10) -> None:
    repo = make_repo(tmp_path, data)
    run_test1(repo, rerun="first run after a crash before writing")
    assert result_of(repo)["rerun"] == {
        "reason": "first run after a crash before writing",
        "previous": None,
    }
    assert "Previous result: none." in report_of(repo)


# --- Command line -------------------------------------------------------------------------------


def test_cli_run_test1(
    tmp_path: Path,
    data: French10,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_repo(tmp_path, data)
    monkeypatch.chdir(repo)
    assert main(["run-test1"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(
        "Test 1 (reproduce): reproduced, 180 of 180 strategy claims within tolerance\n"
    )
    assert "result.json and" in out
    assert main(["run-test1"]) == 1
    assert capsys.readouterr().err.startswith("refused: results/test1/result.json already exists")
    assert main(["run-test1", "--rerun", "testing the flag"]) == 0
    assert result_of(repo)["rerun"]["reason"] == "testing the flag"
