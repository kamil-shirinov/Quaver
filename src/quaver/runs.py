"""Runners for Test 3 in-sample, and for Test 2 with Test 3 after publication.

Pre-registration 0001, section 8: "Order: Test 1; then Test 3 in-sample; then Test 2 and Test 3
after publication, in one run. Each verdict is recorded and committed before the next test
runs." Each runner refuses to start unless the code, pre-registration, spec and data pin are
committed, the pre-registration lock holds, the data file matches its pin and the previous
test's result is committed. Each runs once: a second run needs a stated reason, and the
earlier result is kept.
"""

import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from quaver import after, luck
from quaver.data import DataError, French10, load_french10, sha256_of
from quaver.faber import IN_SAMPLE_FIRST, IN_SAMPLE_LAST, FloatArray
from quaver.prereg import lock_problems
from quaver.test1 import (
    AMENDMENT_01,
    CSV,
    PINS,
    PREREG,
    PREREG_DIR,
    SPEC,
    RunRefused,
    _check_committed,
    _commit_of,
    _git,
    _next_index,
)

# Section 2: "After publication: 2010-01 to END." Section 1: "END is the last month in that
# file, fixed by the file before any run." data/pins.json records it as end_month.
AFTER_FIRST = "2010-01"
TEST1_RESULT = "results/test1/result.json"
TEST3_IN_DIR = "results/test3-in"
AFTER_DIR = "results/after"
TEST3_IN_RESULT = f"{TEST3_IN_DIR}/result.json"
PAPER = "Faber (2010), Relative Strength Strategies for Investing"
HISTOGRAM_BINS = 24
HISTOGRAM_WIDTH = 48


@dataclass(frozen=True)
class Outcome:
    verdicts: dict[str, str]
    result_path: Path
    report_path: Path


@dataclass(frozen=True)
class _Ready:
    commits: dict[str, str]
    data: French10
    provenance: dict[str, Any]
    end_month: str


def _check_order(root: Path, required: str, before: str) -> None:
    """Section 8: the earlier test's result must be committed, unchanged, before this one runs."""
    if not _git(root, "ls-tree", "--name-only", "HEAD", "--", required).strip():
        raise RunRefused(f"{required} is not committed: {before} must run and be committed first")
    if _git(root, "status", "--porcelain", "--", required).strip():
        raise RunRefused(f"{required} has uncommitted changes. Commit it first.")


def _prepare(root: Path, rerun: str | None, out_dir: str, required: str, before: str) -> _Ready:
    if rerun is not None and not rerun.strip():
        raise RunRefused("--rerun needs a reason")
    _check_committed(root)
    problems = lock_problems(root / PREREG_DIR)
    if problems:
        raise RunRefused("the pre-registration lock fails: " + "; ".join(problems))
    _check_order(root, required, before)
    if (root / out_dir / "result.json").exists() and rerun is None:
        raise RunRefused(
            f"{out_dir}/result.json already exists and this test runs once. "
            'To run it again, give --rerun "<reason>".'
        )
    commits = {
        "preregistration": _commit_of(root, PREREG),
        "amendment_01": _commit_of(root, AMENDMENT_01),
        "spec": _commit_of(root, SPEC),
        "code": _git(root, "rev-parse", "HEAD").strip(),
    }
    try:
        data = load_french10(root / CSV, root / PINS)
    except (OSError, DataError) as error:
        raise RunRefused(f"the data does not match its pin: {error}") from error
    pins = json.loads((root / PINS).read_text(encoding="utf-8"))["french_10_industries"]
    provenance = {
        "csv": CSV,
        "csv_sha256": sha256_of(root / CSV),
        "pinned_csv_sha256": pins["csv_sha256"],
        "zip_sha256": pins.get("zip_sha256"),
        "downloaded": pins.get("downloaded"),
        "end_month": pins.get("end_month"),
    }
    return _Ready(commits, data, provenance, str(pins.get("end_month")))


def _through(data: French10, last: str) -> French10:
    """The data up to and including ``last``: nothing later can be computed on."""
    j = data.months.index(last)
    returns = data.returns[: j + 1]
    return French10(months=data.months[: j + 1], industries=data.industries, returns=returns)


def _archive(out_dir: Path) -> str | None:
    """Keep an earlier result as result-N.json and REPORT-N.md; return its name."""
    result_path, report_path = out_dir / "result.json", out_dir / "REPORT.md"
    if not result_path.exists():
        return None
    n = _next_index(out_dir)
    result_path.rename(out_dir / f"result-{n}.json")
    if report_path.exists():
        report_path.rename(out_dir / f"REPORT-{n}.md")
    return f"result-{n}.json"


def _write(
    root: Path, out_dir: str, result: dict[str, Any], report: str, verdicts: dict[str, str]
) -> Outcome:
    folder = root / out_dir
    folder.mkdir(parents=True, exist_ok=True)
    result_path, report_path = folder / "result.json", folder / "REPORT.md"
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(report, encoding="utf-8")
    return Outcome(verdicts=verdicts, result_path=result_path, report_path=report_path)


def _common(
    ready: _Ready, rerun: str | None, previous: str | None, runtime: float
) -> dict[str, Any]:
    return {
        "seed": luck.SEED,
        "commits": ready.commits,
        "data": ready.provenance,
        "rerun": None if rerun is None else {"reason": rerun, "previous": previous},
        "run_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "runtime_seconds": round(runtime, 3),
    }


def run_test3_in(root: Path, rerun: str | None = None) -> Outcome:
    """Test 3 for holding months 1928-01 to 2009-12, after every guard has passed."""
    ready = _prepare(root, rerun, TEST3_IN_DIR, TEST1_RESULT, "Test 1")
    started = time.perf_counter()
    in_sample = _through(ready.data, IN_SAMPLE_LAST)
    result3 = luck.test3(in_sample, IN_SAMPLE_FIRST, IN_SAMPLE_LAST, k=luck.K)
    runtime = time.perf_counter() - started
    previous = _archive(root / TEST3_IN_DIR)
    result: dict[str, Any] = {
        "test": "Test 3 (luck), in-sample",
        "paper": PAPER,
        "verdict": result3.verdict,
        "unit": "decimal fraction per year",
        "k": len(result3.randoms),
        "test3": result3.to_json(),
        **_common(ready, rerun, previous, runtime),
    }
    return _write(root, TEST3_IN_DIR, result, render_test3_in(result), {"test3": result3.verdict})


def run_after(root: Path, rerun: str | None = None) -> Outcome:
    """Test 2 and Test 3 for holding months 2010-01 to END, in one run."""
    ready = _prepare(root, rerun, AFTER_DIR, TEST3_IN_RESULT, "Test 3 in-sample")
    end = ready.data.months[-1]
    if end != ready.end_month:
        raise RunRefused(f"the data ends {end} but data/pins.json fixes END as {ready.end_month}")
    started = time.perf_counter()
    details = after.after_publication(ready.data, AFTER_FIRST, end, IN_SAMPLE_FIRST, IN_SAMPLE_LAST)
    result3 = luck.test3(ready.data, AFTER_FIRST, end, k=luck.K)
    runtime = time.perf_counter() - started
    previous = _archive(root / AFTER_DIR)
    verdicts = {"test2": details["test2"]["verdict"], "test3": result3.verdict}
    result: dict[str, Any] = {
        "test": "Test 2 (after publication) and Test 3 (luck), after publication",
        "paper": PAPER,
        "verdicts": verdicts,
        "unit": "decimal fraction per year",
        "k": len(result3.randoms),
        **details,
        "test3": result3.to_json(),
        **_common(ready, rerun, previous, runtime),
    }
    return _write(root, AFTER_DIR, result, render_after(result), verdicts)


# --- Reports ------------------------------------------------------------------------------------


def _pp(value: float) -> str:
    return f"{100.0 * value:+.2f}"


def histogram(randoms: FloatArray, real: float) -> list[str]:
    """A text histogram of the random statistics in pp per year, with the real value marked."""
    values = 100.0 * np.asarray(randoms, dtype=np.float64)
    mark = 100.0 * real
    lo, hi = min(float(values.min()), mark), max(float(values.max()), mark)
    if hi == lo:
        lo, hi = lo - 0.5, hi + 0.5
    edges = np.linspace(lo, hi, HISTOGRAM_BINS + 1)
    counts, _ = np.histogram(values, bins=edges)
    real_bin = min(int(np.searchsorted(edges, mark, side="right")) - 1, HISTOGRAM_BINS - 1)
    top = int(counts.max())
    lines = []
    for b, count in enumerate(counts):
        bar = "#" * (max(1, round(HISTOGRAM_WIDTH * count / top)) if count else 0)
        line = f"{edges[b]:+7.2f} to {edges[b + 1]:+7.2f} | {bar:<{HISTOGRAM_WIDTH}} {count:>5}"
        if b == real_bin:
            line += f"  <-- real {mark:+.2f}"
        lines.append(line.rstrip())
    return lines


def _test3_section(t3: dict[str, Any], randoms: FloatArray) -> list[str]:
    q = t3["percentiles"]
    return [
        f"Statistic: the family's annualised mean excess return over the benchmark, "
        f"{t3['first']} to {t3['last']} ({t3['months']} months).",
        "",
        f"- Real family: {_pp(t3['real'])} pp per year",
        f"- Random families at least as high: {t3['random_at_least_real']:,} of "
        f"{t3['random_families']:,}",
        f"- p = (1 + {t3['random_at_least_real']:,}) / {t3['random_families'] + 1:,} = "
        f"{t3['p']:.4f}",
        f"- Random families, pp per year: 5th percentile {_pp(q['5'])}, median {_pp(q['50'])}, "
        f"95th percentile {_pp(q['95'])}",
        "",
        "Random families, pp per year (bins, bar, count):",
        "",
        "```text",
        *histogram(randoms, t3["real"]),
        "```",
    ]


def _provenance(result: dict[str, Any]) -> list[str]:
    commits, data = result["commits"], result["data"]
    lines = [
        "## Provenance",
        "",
        f"- Pre-registration: `{commits['preregistration']}`",
        f"- Amendment 01: `{commits['amendment_01']}`",
        f"- Spec: `{commits['spec']}`",
        f"- Code: `{commits['code']}`",
        f"- Data: `{data['csv']}`, SHA-256 `{data['csv_sha256']}` (pin "
        f"`{data['pinned_csv_sha256']}`), zip SHA-256 `{data['zip_sha256']}`, "
        f"downloaded {data['downloaded']}",
        f"- Random families: k = {result['k']:,}, numpy.random.default_rng({result['seed']}), "
        f"drawn in chunks of {luck.CHUNK}",
        f"- Run at (UTC): {result['run_at_utc']}, runtime {result['runtime_seconds']:.1f} s",
    ]
    if result["rerun"] is not None:
        previous = result["rerun"]["previous"] or "none"
        lines.append(f"- Rerun. Reason: {result['rerun']['reason']}. Previous result: {previous}.")
    return [*lines, ""]


def render_test3_in(result: dict[str, Any]) -> str:
    """REPORT.md for Test 3 in-sample: the verdict, the statistic and p, then the histogram."""
    t3 = result["test3"]
    lines = [
        f"# Test 3 (luck), in-sample: {result['paper']}",
        "",
        f"**Verdict: {t3['verdict']}.** p = {t3['p']:.4f}. Pre-registered: "
        f'"{luck.BEATS}" if p < {luck.ALPHA}, otherwise "{luck.NOT_DISTINGUISHABLE}".',
        "",
        *_test3_section(t3, np.asarray(t3["randoms"], dtype=np.float64)),
        "",
        *_provenance(result),
    ]
    return "\n".join(lines)


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return lines + ["| " + " | ".join(row) + " |" for row in rows]


def _share(described: dict[str, Any]) -> str:
    share = described["share_of_years_beating_benchmark"]
    return "—" if share is None else f"{share:.0%}"


def _partial(described: dict[str, Any]) -> str:
    return "; ".join(
        f"{p['first']} to {p['last']}: {_pp(p['return'])}" for p in described["partial_years"]
    )


def render_after(result: dict[str, Any]) -> str:
    """REPORT.md for the after-publication run: both verdicts, then every number behind them."""
    t2, t3 = result["test2"], result["test3"]
    ratio = result["ratio_after_to_in_sample"]
    family, bench = result["family"], result["benchmark"]
    lines = [
        f"# After publication: {result['paper']}",
        "",
        f"**Test 2 (after publication): {t2['verdict']}.** p = {t2['p']:.4f}.",
        "",
        f"**Test 3 (luck), after publication: {t3['verdict']}.** p = {t3['p']:.4f}.",
        "",
        f'Pre-registered: Test 2 "{after.SURVIVED}" if p < {after.ALPHA}, "{after.WEAKENED}" '
        f'if the estimate is above zero with p >= {after.ALPHA}, "{after.GONE}" if it is zero '
        f'or below. Test 3 "{luck.BEATS}" if p < {luck.ALPHA}.',
        "",
        "## Test 2",
        "",
        f"Statistic: the family's annualised mean excess return over the benchmark, "
        f"{t2['first']} to {t2['last']} ({t2['months']} months).",
        "",
        f"- Estimate: {_pp(t2['estimate'])} pp per year",
        f"- Newey-West standard error ({t2['lags']} lags): {100.0 * t2['standard_error']:.2f} pp",
        f"- z = {t2['z']:.3f}, one-sided p = {t2['p']:.4f}",
        "",
        "Reported without a verdict:",
        "",
        f"- In-sample ({result['in_sample']['first']} to {result['in_sample']['last']}): "
        f"{_pp(result['in_sample']['estimate'])} pp per year",
        "- After publication / in-sample: "
        + ("— (in-sample estimate is zero)" if ratio is None else f"{ratio:.2f}")
        + ". For comparison, McLean and Pontiff (2016) found returns 58% lower after "
        "publication on average (a ratio of 0.42).",
        "",
        "## Test 3",
        "",
        *_test3_section(t3, np.asarray(t3["randoms"], dtype=np.float64)),
        "",
        "## Every version after publication",
        "",
        "Percent. CAGR, volatility, max drawdown and excess use every month. Years beating the "
        "benchmark use complete calendar years only; partial years are listed separately "
        "(amendment 01, item 1).",
        "",
    ]
    rows = [
        [
            label,
            f"{100.0 * d['cagr']:.2f}",
            f"{100.0 * d['volatility']:.2f}",
            f"{100.0 * d['max_drawdown']:.2f}",
            _pp(d["annualised_excess"]),
            f"{d['years_beating_benchmark']} of {d['complete_years']} ({_share(d)})",
            _partial(d) or "—",
        ]
        for label, d in [
            *((f"L{v['lookback']} Top{v['top_n']}", v) for v in result["versions"]),
            ("Family", family),
            ("Benchmark", bench),
        ]
    ]
    lines += _table(
        [
            "Version",
            "CAGR",
            "Volatility",
            "Max drawdown",
            "Excess (pp/yr)",
            "Years beating",
            "Partial year",
        ],
        rows,
    )
    lines += ["", "## Calendar years, complete years only", ""]
    lines += _table(
        ["Year", "Family", "Benchmark", "Difference (pp)"],
        [
            [
                year,
                f"{100.0 * value:.2f}",
                f"{100.0 * bench['calendar_years'][year]:.2f}",
                _pp(value - bench["calendar_years"][year]),
            ]
            for year, value in family["calendar_years"].items()
        ],
    )
    if family["partial_years"]:
        lines += [
            "",
            f"Partial year, reported separately and used in no calendar-year figure: family "
            f"{_partial(family)}; benchmark {_partial(bench)}.",
        ]
    lines += ["", *_provenance(result)]
    return "\n".join(lines)
