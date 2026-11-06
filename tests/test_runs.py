"""Runner tests for Test 3 in-sample and the after-publication run.

Everything here is made up: a dataset from 1927-01 to 2011-09 in the layout of French's file,
and a throwaway git repository for each test. The real data is never read, and neither real
run happens. k is patched down from 10,000 to keep the tests fast.
"""

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from quaver import after, luck
from quaver.cli import main
from quaver.data import load_french10
from quaver.runs import (
    AFTER_DIR,
    TEST1_RESULT,
    TEST3_IN_DIR,
    TEST3_IN_RESULT,
    histogram,
    run_after,
    run_test3_in,
)
from quaver.test1 import AMENDMENT_01, CSV, PINS, PREREG, SPEC, RunRefused

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
N_MONTHS = 1017  # 1927-01 to 2011-09: a year of history, the in-sample span, then 21 months
END = "2011-09"
K = 200


def csv_bytes(after_2009: float = 0.0) -> bytes:
    """Made-up returns in percent; ``after_2009`` is added to every month after 2009-12."""
    values = np.random.default_rng(12).uniform(-8.0, 10.0, size=(N_MONTHS, len(INDUSTRIES)))
    values[(2010 - 1927) * 12 :] += after_2009
    lines = [
        "Made-up data in the layout of French's file. Not real data.",
        "",
        "  Average Value Weighted Returns -- Monthly",
        "," + ",".join(INDUSTRIES),
    ]
    for k, row in enumerate(values):
        lines.append(f"{1927 + k // 12}{k % 12 + 1:02d}," + ",".join(f"{v:8.2f}" for v in row))
    lines += ["", "Copyright 2000 Nobody", ""]
    return "\r\n".join(lines).encode("utf-8")


CSV_BYTES = csv_bytes()


def pin(data: bytes, end: str = END) -> dict[str, Any]:
    return {
        "french_10_industries": {
            "csv_sha256": hashlib.sha256(data).hexdigest(),
            "zip_sha256": "0" * 64,
            "downloaded": "2000-01-01",
            "end_month": end,
        }
    }


@pytest.fixture(autouse=True)
def small_k(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(luck, "K", K)


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


def make_repo(
    tmp_path: Path,
    *,
    data: bytes = CSV_BYTES,
    end: str = END,
    test1: bool = True,
    test3_in: bool = False,
    amendment: bool = True,
    name: str = "repo",
) -> Path:
    repo = tmp_path / name
    for folder in ("src", "prereg", "specs", "data/raw", "results/test1"):
        (repo / folder).mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    (repo / ".gitignore").write_text("data/raw/\n", encoding="utf-8")
    (repo / "src" / "code.py").write_text("# Made up.\n", encoding="utf-8")
    (repo / PREREG).write_text("# Made-up pre-registration\n", encoding="utf-8")
    if amendment:
        (repo / AMENDMENT_01).write_text("# Made-up amendment\n", encoding="utf-8")
    write_locks(repo / "prereg")
    (repo / SPEC).write_text("made_up: true\n", encoding="utf-8")
    (repo / CSV).write_bytes(data)
    (repo / PINS).write_text(json.dumps(pin(data, end)), encoding="utf-8")
    if test1:
        (repo / TEST1_RESULT).write_text('{"verdict": "made up"}\n', encoding="utf-8")
    if test3_in:
        (repo / TEST3_IN_DIR).mkdir(parents=True)
        (repo / TEST3_IN_RESULT).write_text('{"verdict": "made up"}\n', encoding="utf-8")
    commit_all(repo, "Set up")
    return repo


def result_of(repo: Path, out_dir: str, name: str = "result.json") -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((repo / out_dir / name).read_text(encoding="utf-8"))
    return loaded


def report_of(repo: Path, out_dir: str) -> str:
    return (repo / out_dir / "REPORT.md").read_text(encoding="utf-8")


def made_up_data(repo: Path) -> Any:
    return load_french10(repo / CSV, repo / PINS)


# --- Test 3 in-sample ---------------------------------------------------------------------------


def test_test3_in(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    outcome = run_test3_in(repo)
    result = result_of(repo, TEST3_IN_DIR)
    t3 = result["test3"]
    assert outcome.verdicts == {"test3": t3["verdict"]}
    assert outcome.result_path == repo / TEST3_IN_DIR / "result.json"
    assert result["verdict"] == t3["verdict"]
    assert (t3["first"], t3["last"], t3["months"]) == ("1928-01", "2009-12", 984)
    data = made_up_data(repo)
    assert t3["real"] == pytest.approx(after.family_statistic(data, "1928-01", "2009-12"))
    assert t3["random_families"] == len(t3["randoms"]) == K
    assert t3["p"] == luck.p_value(t3["real"], np.array(t3["randoms"]))
    assert t3["verdict"] == luck.verdict(t3["p"])
    assert (result["seed"], result["k"]) == (20261106, K)
    head = git(repo, "rev-parse", "HEAD").strip()
    assert result["commits"] == {
        "preregistration": head,
        "amendment_01": head,
        "spec": head,
        "code": head,
    }
    digest = hashlib.sha256(CSV_BYTES).hexdigest()
    assert result["data"]["csv_sha256"] == result["data"]["pinned_csv_sha256"] == digest
    assert result["data"]["zip_sha256"] == "0" * 64
    assert result["data"]["end_month"] == END
    assert result["rerun"] is None
    assert datetime.fromisoformat(result["run_at_utc"]).utcoffset() is not None
    assert result["runtime_seconds"] > 0
    report = report_of(repo, TEST3_IN_DIR)
    assert report.startswith(
        "# Test 3 (luck), in-sample: Faber (2010), Relative Strength Strategies for Investing\n\n"
        f"**Verdict: {t3['verdict']}.** p = {t3['p']:.4f}."
    )
    verdict_at, statistic_at = report.index("**Verdict"), report.index("Statistic:")
    histogram_at = report.index("```text")
    assert verdict_at < statistic_at < histogram_at
    assert report.count("<-- real") == 1
    assert f"k = {K}, numpy.random.default_rng(20261106)" in report


def test_test3_in_draws_match_the_luck_module(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    run_test3_in(repo)
    randoms = luck.random_family_stats(made_up_data(repo), "1928-01", "2009-12", k=K)
    assert result_of(repo, TEST3_IN_DIR)["test3"]["randoms"] == randoms.tolist()


def test_test3_in_never_sees_data_after_2009(tmp_path: Path) -> None:
    first = make_repo(tmp_path, name="a")
    second = make_repo(tmp_path, data=csv_bytes(after_2009=5.0), name="b")
    run_test3_in(first)
    run_test3_in(second)
    a, b = result_of(first, TEST3_IN_DIR), result_of(second, TEST3_IN_DIR)
    assert a["data"]["csv_sha256"] != b["data"]["csv_sha256"]
    assert a["test3"] == b["test3"]


# --- After publication --------------------------------------------------------------------------


def test_after(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, test3_in=True)
    outcome = run_after(repo)
    result = result_of(repo, AFTER_DIR)
    t2, t3 = result["test2"], result["test3"]
    assert (
        outcome.verdicts == result["verdicts"] == {"test2": t2["verdict"], "test3": t3["verdict"]}
    )
    data = made_up_data(repo)
    assert t2 == after.test2(data, "2010-01", END).to_json()
    assert (t2["months"], t2["lags"]) == (21, 2)
    assert (t3["first"], t3["last"], t3["months"]) == ("2010-01", END, 21)
    assert t3["real"] == pytest.approx(t2["estimate"])
    assert t3["randoms"] == luck.random_family_stats(data, "2010-01", END, k=K).tolist()
    assert result["in_sample"]["estimate"] == pytest.approx(
        after.family_statistic(data, "1928-01", "2009-12")
    )
    assert result["ratio_after_to_in_sample"] == pytest.approx(
        t2["estimate"] / result["in_sample"]["estimate"]
    )
    assert len(result["versions"]) == 15
    assert list(result["family"]["calendar_years"]) == ["2010"]
    assert result["family"]["partial_years"][0] | {"return": 0} == {
        "year": 2011,
        "first": "2011-01",
        "last": "2011-09",
        "months": 9,
        "return": 0,
    }
    assert (result["seed"], result["k"]) == (20261106, K)
    assert result["commits"]["code"] == git(repo, "rev-parse", "HEAD").strip()
    assert result["runtime_seconds"] > 0
    report = report_of(repo, AFTER_DIR)
    assert report.startswith(
        "# After publication: Faber (2010), Relative Strength Strategies for Investing\n\n"
        f"**Test 2 (after publication): {t2['verdict']}.** p = {t2['p']:.4f}.\n\n"
        f"**Test 3 (luck), after publication: {t3['verdict']}.** p = {t3['p']:.4f}."
    )
    assert report.index("Statistic:") < report.index("```text")
    assert report.count("<-- real") == 1
    assert "| L12 Top3 |" in report
    assert "| 2010 |" in report
    assert "Partial year, reported separately" in report
    assert "2011-01 to 2011-09" in report
    assert "McLean and Pontiff (2016)" in report


def test_after_refuses_an_end_other_than_the_pin(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, test3_in=True, end="2011-08")
    with pytest.raises(
        RunRefused, match=r"data ends 2011-09 but data/pins\.json fixes END as 2011-08"
    ):
        run_after(repo)
    assert not (repo / AFTER_DIR).exists()


# --- Guards, for both runners -------------------------------------------------------------------


def ready_for(tmp_path: Path, out_dir: str, **options: Any) -> Path:
    """A repository where every earlier result is committed and this runner's own is absent."""
    return make_repo(tmp_path, test3_in=out_dir == AFTER_DIR, **options)


RUNNERS = [
    pytest.param(run_test3_in, TEST3_IN_DIR, id="test3-in"),
    pytest.param(run_after, AFTER_DIR, id="after"),
]


@pytest.mark.parametrize(("runner", "out_dir"), RUNNERS)
@pytest.mark.parametrize("path", ["src/new.py", "src/code.py", PREREG, SPEC, PINS])
def test_uncommitted_changes_are_refused(
    tmp_path: Path, runner: Any, out_dir: str, path: str
) -> None:
    repo = ready_for(tmp_path, out_dir)
    target = repo / path
    target.write_text(
        (target.read_text(encoding="utf-8") if target.exists() else "") + "\n", encoding="utf-8"
    )
    with pytest.raises(RunRefused, match="uncommitted changes in src, prereg, specs") as info:
        runner(repo)
    assert path in str(info.value)
    assert not (repo / out_dir / "REPORT.md").exists()


@pytest.mark.parametrize(("runner", "out_dir"), RUNNERS)
def test_failing_prereg_lock_is_refused(tmp_path: Path, runner: Any, out_dir: str) -> None:
    repo = ready_for(tmp_path, out_dir)
    (repo / PREREG).write_text("# Edited\n", encoding="utf-8")
    commit_all(repo, "Edit a locked file")
    with pytest.raises(RunRefused, match=r"lock fails: 0001-faber-2010\.md has changed"):
        runner(repo)


@pytest.mark.parametrize(("runner", "out_dir"), RUNNERS)
def test_uncommitted_amendment_is_refused(tmp_path: Path, runner: Any, out_dir: str) -> None:
    repo = ready_for(tmp_path, out_dir, amendment=False)
    with pytest.raises(RunRefused, match=f"{AMENDMENT_01} has never been committed"):
        runner(repo)


@pytest.mark.parametrize(("runner", "out_dir"), RUNNERS)
def test_data_not_matching_pin_is_refused(tmp_path: Path, runner: Any, out_dir: str) -> None:
    repo = ready_for(tmp_path, out_dir)
    (repo / CSV).write_bytes(CSV_BYTES.replace(b"Not real data.", b"Not real data!"))
    with pytest.raises(RunRefused, match=r"does not match its pin: .*hash mismatch"):
        runner(repo)


@pytest.mark.parametrize(("runner", "out_dir"), RUNNERS)
@pytest.mark.parametrize("reason", ["", "   "])
def test_rerun_needs_a_reason(tmp_path: Path, runner: Any, out_dir: str, reason: str) -> None:
    repo = ready_for(tmp_path, out_dir)
    with pytest.raises(RunRefused, match="--rerun needs a reason"):
        runner(repo, rerun=reason)


@pytest.mark.parametrize(("runner", "out_dir"), RUNNERS)
def test_second_run_is_refused(tmp_path: Path, runner: Any, out_dir: str) -> None:
    repo = ready_for(tmp_path, out_dir)
    (repo / out_dir).mkdir(parents=True, exist_ok=True)
    (repo / out_dir / "result.json").write_text("{}\n", encoding="utf-8")
    if out_dir == TEST3_IN_DIR:
        commit_all(repo, "Earlier result")
    with pytest.raises(RunRefused, match=r'already exists and this test runs once\. .*--rerun "'):
        runner(repo)
    assert (repo / out_dir / "result.json").read_text(encoding="utf-8") == "{}\n"


def test_not_a_git_repository(tmp_path: Path) -> None:
    with pytest.raises(RunRefused, match="git status --porcelain"):
        run_test3_in(tmp_path)


# --- Order guards -------------------------------------------------------------------------------

ORDER = [
    pytest.param(run_test3_in, TEST1_RESULT, "Test 1", id="test3-in-needs-test1"),
    pytest.param(run_after, TEST3_IN_RESULT, "Test 3 in-sample", id="after-needs-test3-in"),
]


def repo_without(tmp_path: Path, required: str) -> Path:
    if required == TEST1_RESULT:
        return make_repo(tmp_path, test1=False)
    return make_repo(tmp_path, test3_in=False)


@pytest.mark.parametrize(("runner", "required", "before"), ORDER)
def test_order_guard_when_the_earlier_result_is_missing(
    tmp_path: Path, runner: Any, required: str, before: str
) -> None:
    repo = repo_without(tmp_path, required)
    with pytest.raises(
        RunRefused, match=f"{required} is not committed: {before} must run and be committed first"
    ):
        runner(repo)


@pytest.mark.parametrize(("runner", "required", "before"), ORDER)
def test_order_guard_when_the_earlier_result_is_not_committed(
    tmp_path: Path, runner: Any, required: str, before: str
) -> None:
    repo = repo_without(tmp_path, required)
    (repo / required).parent.mkdir(parents=True, exist_ok=True)
    (repo / required).write_text("{}\n", encoding="utf-8")
    with pytest.raises(RunRefused, match=f"{required} is not committed"):
        runner(repo)
    git(repo, "add", required)  # staged is still not committed
    with pytest.raises(RunRefused, match=f"{required} is not committed"):
        runner(repo)


@pytest.mark.parametrize(("runner", "required", "before"), ORDER)
def test_order_guard_when_the_earlier_result_has_changed(
    tmp_path: Path, runner: Any, required: str, before: str
) -> None:
    repo = make_repo(tmp_path, test3_in=True)
    (repo / required).write_text('{"verdict": "edited"}\n', encoding="utf-8")
    with pytest.raises(RunRefused, match=f"{required} has uncommitted changes"):
        runner(repo)
    (repo / required).unlink()
    with pytest.raises(RunRefused, match=f"{required} has uncommitted changes"):
        runner(repo)


def test_after_runs_once_test3_in_is_committed(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    with pytest.raises(RunRefused, match="Test 3 in-sample must run and be committed first"):
        run_after(repo)
    run_test3_in(repo)
    with pytest.raises(RunRefused, match=f"{TEST3_IN_RESULT} is not committed"):
        run_after(repo)
    commit_all(repo, "Test 3 in-sample")
    assert set(run_after(repo).verdicts) == {"test2", "test3"}


# --- Reruns -------------------------------------------------------------------------------------


def test_rerun_keeps_the_old_results(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    run_test3_in(repo)
    first = (repo / TEST3_IN_DIR / "result.json").read_bytes()
    first_report = (repo / TEST3_IN_DIR / "REPORT.md").read_bytes()
    run_test3_in(repo, rerun="crashed while writing")
    assert (repo / TEST3_IN_DIR / "result-1.json").read_bytes() == first
    assert (repo / TEST3_IN_DIR / "REPORT-1.md").read_bytes() == first_report
    assert result_of(repo, TEST3_IN_DIR)["rerun"] == {
        "reason": "crashed while writing",
        "previous": "result-1.json",
    }
    assert "Rerun. Reason: crashed while writing. Previous result: result-1.json." in report_of(
        repo, TEST3_IN_DIR
    )
    # Same seed, same data: the same numbers.
    again = result_of(repo, TEST3_IN_DIR)["test3"]
    assert again == result_of(repo, TEST3_IN_DIR, "result-1.json")["test3"]


def test_rerun_without_a_report_or_an_earlier_result(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, test3_in=True)
    run_after(repo, rerun="first run after a crash before writing")
    assert result_of(repo, AFTER_DIR)["rerun"] == {
        "reason": "first run after a crash before writing",
        "previous": None,
    }
    assert "Previous result: none." in report_of(repo, AFTER_DIR)
    (repo / AFTER_DIR / "REPORT.md").unlink()
    run_after(repo, rerun="numbering")
    assert (repo / AFTER_DIR / "result-1.json").exists()
    assert not (repo / AFTER_DIR / "REPORT-1.md").exists()


# --- Histogram ----------------------------------------------------------------------------------


def count_of(line: str) -> int:
    return int(line.split("|")[1].split("<--")[0].split()[-1])


def test_histogram_marks_the_real_value() -> None:
    randoms = np.random.default_rng(2).normal(0.0, 0.01, size=1000)
    lines = histogram(randoms, 0.05)
    assert len(lines) == 24
    assert lines[-1].endswith("<-- real +5.00")
    assert sum(count_of(line) for line in lines) == 1000
    assert sum("<-- real" in line for line in lines) == 1


def test_histogram_of_identical_values() -> None:
    lines = histogram(np.zeros(10), 0.0)
    assert len(lines) == 24
    marked = [line for line in lines if "<-- real" in line]
    assert len(marked) == 1
    assert " 10  <-- real +0.00" in marked[0]


def test_histogram_with_the_real_value_below_every_random() -> None:
    lines = histogram(np.array([0.01, 0.02, 0.03]), -0.01)
    assert lines[0].endswith("<-- real -1.00")
    assert count_of(lines[0]) == 0


# --- Command line -------------------------------------------------------------------------------


def test_cli_run_test3_in_and_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.chdir(repo)
    assert main(["run-after"]) == 1
    assert "refused: results/test3-in/result.json is not committed" in capsys.readouterr().err
    assert main(["run-test3-in"]) == 0
    out = capsys.readouterr().out
    verdict = result_of(repo, TEST3_IN_DIR)["verdict"]
    assert out.startswith(f"Test 3 (luck): {verdict}\nwrote ")
    assert main(["run-test3-in"]) == 1
    assert capsys.readouterr().err.startswith("refused: results/test3-in/result.json already")
    assert main(["run-test3-in", "--rerun", "testing the flag"]) == 0
    assert result_of(repo, TEST3_IN_DIR)["rerun"]["reason"] == "testing the flag"
    capsys.readouterr()
    commit_all(repo, "Test 3 in-sample")
    assert main(["run-after"]) == 0
    verdicts = result_of(repo, AFTER_DIR)["verdicts"]
    assert capsys.readouterr().out.startswith(
        f"Test 2 (after publication): {verdicts['test2']}\nTest 3 (luck): {verdicts['test3']}\n"
    )
