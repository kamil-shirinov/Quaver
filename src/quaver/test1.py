"""Test 1 (reproduce), as prereg/0001-faber-2010.md section 4 and its amendment 01 define it.

Every claim in specs/faber-2010.yaml except turnover is recomputed over the claim's period and
compared with the paper's value. The run refuses to start unless the code, pre-registration, spec
and data pin are committed, the pre-registration lock holds and the data file matches its pin.
It writes results/test1/result.json and results/test1/REPORT.md, and runs once: a second run
needs a stated reason, and the earlier result is kept.
"""

import json
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from quaver import metrics
from quaver.data import DataError, French10, load_french10, sha256_of
from quaver.faber import FloatArray, Weights, benchmark_returns, version_returns
from quaver.prereg import lock_problems
from quaver.spec import Claim, StrategySpec, Subject, load_spec

PREREG = "prereg/0001-faber-2010.md"
AMENDMENT_01 = "prereg/0001-faber-2010-amendment-01.md"
PREREG_DIR = "prereg"
SPEC = "specs/faber-2010.yaml"
CSV = "data/raw/10_Industry_Portfolios.csv"
PINS = "data/pins.json"
OUT_DIR = "results/test1"
# Nothing here may differ from the last commit when the test runs.
GUARDED = ("src", "prereg", "specs", "data/pins.json")

# Section 4: "Tolerances (absolute difference): CAGR 0.50 pp, volatility 0.50 pp, Sharpe 0.03,
# max drawdown 2.0 pp, best and worst year 1.0 pp."
TOLERANCES: dict[str, float] = {
    "CAGR": 0.50,
    "volatility": 0.50,
    "Sharpe ratio": 0.03,
    "max drawdown": 2.0,
    "best year": 1.0,
    "worst year": 1.0,
}
# The unit the spec stores each metric in. Drawdown and worst year are negative percentages.
UNITS: dict[str, str] = {
    "CAGR": "% per year",
    "volatility": "% per year",
    "Sharpe ratio": "ratio",
    "max drawdown": "%",
    "best year": "%",
    "worst year": "%",
}
# Section 4: "Turnover is not tested."
NOT_TESTED = frozenset({"turnover"})
# Section 4: "Data check first: our benchmark CAGR and volatility must both be within tolerance."
DATA_CHECK_METRICS = ("CAGR", "volatility")
# Section 4: "Verdict, from the 180 strategy claims: Reproduced: at least 162 (90%) within
# tolerance. Partly reproduced: 90 to 161. Not reproduced: fewer than 90."
STRATEGY_CLAIMS = 180
REPRODUCED_MIN = 162
PARTLY_MIN = 90
INCONCLUSIVE = "inconclusive: data differ"
# The paper prints two decimals. This slack absorbs only binary floating-point error, so that a
# difference of exactly the tolerance (say 12.13 against 12.63) counts as within.
FLOAT_SLACK = 1e-9

_PREVIOUS = re.compile(r"^result-(\d+)\.json$")


class RunRefused(Exception):
    """Test 1 will not run, and nothing was computed or written."""


@dataclass(frozen=True)
class ClaimResult:
    """One claim: the paper's value, ours, the difference (ours minus paper) and the verdict."""

    id: str
    subject: str
    lookback: int | None
    top_n: int | None
    metric: str
    period_start: str
    period_end: str
    paper: float
    ours: float
    difference: float
    tolerance: float
    within: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "lookback": self.lookback,
            "top_n": self.top_n,
            "metric": self.metric,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "paper": self.paper,
            "ours": self.ours,
            "difference": self.difference,
            "tolerance": self.tolerance,
            "within": self.within,
        }


@dataclass(frozen=True)
class Outcome:
    verdict: str
    within: int
    total: int
    result_path: Path
    report_path: Path


Series = Callable[[int | None, int | None, str, str, Weights], tuple[FloatArray, tuple[str, ...]]]


def metric_value(metric: str, returns: FloatArray, months: Sequence[str], ddof: int = 1) -> float:
    """One metric (prereg section 3) in the spec's units: percent, except the Sharpe ratio."""
    match metric:
        case "CAGR":
            return 100.0 * metrics.cagr(returns)
        case "volatility":
            return 100.0 * metrics.volatility(returns, ddof)
        case "Sharpe ratio":
            return metrics.sharpe_paper(returns, ddof)
        case "max drawdown":
            return 100.0 * metrics.max_drawdown(returns)
        case "best year":
            return 100.0 * metrics.best_year(returns, months)
        case "worst year":
            return 100.0 * metrics.worst_year(returns, months)
    raise ValueError(f"no rule for metric {metric!r}")


def is_within(difference: float, tolerance: float) -> bool:
    """Section 4: an absolute difference no larger than the tolerance."""
    return abs(difference) <= tolerance + FLOAT_SLACK


def verdict(data_check_passed: bool, within: int) -> str:
    """Section 4's verdict from the data check and the strategy claims within tolerance."""
    if not data_check_passed:
        return INCONCLUSIVE
    if within >= REPRODUCED_MIN:
        return "reproduced"
    if within >= PARTLY_MIN:
        return "partly reproduced"
    return "not reproduced"


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RunRefused(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def _check_committed(root: Path) -> None:
    status = _git(root, "status", "--porcelain", "--untracked-files=all", "--", *GUARDED)
    if status.strip():
        changed = ", ".join(line[3:] for line in status.splitlines())
        raise RunRefused(
            f"uncommitted changes in {', '.join(GUARDED)}: {changed}. Commit them first."
        )


def _commit_of(root: Path, path: str) -> str:
    commit = _git(root, "log", "-1", "--format=%H", "--", path).strip()
    if not commit:
        raise RunRefused(f"{path} has never been committed")
    return commit


def _load_checked_spec(path: Path) -> StrategySpec:
    try:
        spec = load_spec(path)
    except (OSError, ValidationError, yaml.YAMLError) as error:
        raise RunRefused(f"the spec {path} is not valid: {error}") from error
    problems: list[str] = []
    for claim in spec.claims:
        if claim.metric in NOT_TESTED:
            continue
        if claim.metric not in TOLERANCES:
            problems.append(f"{claim.id}: no pre-registered tolerance for {claim.metric!r}")
        elif claim.unit != UNITS[claim.metric]:
            problems.append(
                f"{claim.id}: unit {claim.unit!r}, expected {UNITS[claim.metric]!r} "
                f"for {claim.metric}"
            )
    strategy = [c for c in spec.claims if _tested(c) and c.subject is Subject.STRATEGY]
    if len(strategy) != STRATEGY_CLAIMS:
        problems.append(
            f"the verdict is defined for {STRATEGY_CLAIMS} strategy claims; "
            f"the spec has {len(strategy)}"
        )
    for metric in DATA_CHECK_METRICS:
        found = [c for c in spec.claims if c.subject is Subject.BENCHMARK and c.metric == metric]
        if len(found) != 1:
            problems.append(
                f"the data check needs one benchmark {metric} claim, found {len(found)}"
            )
    if problems:
        raise RunRefused(f"the spec {path} cannot be tested: " + "; ".join(problems))
    return spec


def _tested(claim: Claim) -> bool:
    return claim.metric not in NOT_TESTED


def _series(data: French10) -> Series:
    @cache
    def series(
        lookback: int | None, top_n: int | None, first: str, last: str, weights: Weights
    ) -> tuple[FloatArray, tuple[str, ...]]:
        if lookback is None or top_n is None:
            returns = benchmark_returns(data, first, last)
            i = data.months.index(first)
            return returns, data.months[i : i + len(returns)]
        version = version_returns(data, lookback, top_n, first, last, weights)
        return version.returns, version.months

    return series


def _evaluate(
    claim: Claim, series: Series, weights: Weights = "reset", ddof: int = 1
) -> ClaimResult:
    returns, months = series(
        claim.lookback_months, claim.top_n, claim.period_start, claim.period_end, weights
    )
    ours = metric_value(claim.metric, returns, months, ddof)
    difference = ours - claim.value
    tolerance = TOLERANCES[claim.metric]
    return ClaimResult(
        id=claim.id,
        subject=claim.subject.value,
        lookback=claim.lookback_months,
        top_n=claim.top_n,
        metric=claim.metric,
        period_start=claim.period_start,
        period_end=claim.period_end,
        paper=claim.value,
        ours=ours,
        difference=difference,
        tolerance=tolerance,
        within=is_within(difference, tolerance),
    )


def _counts(results: Sequence[ClaimResult]) -> dict[str, Any]:
    by_metric: dict[str, int] = {}
    totals: dict[str, int] = {}
    for result in results:
        totals[result.metric] = totals.get(result.metric, 0) + 1
        by_metric[result.metric] = by_metric.get(result.metric, 0) + int(result.within)
    return {
        "within": sum(by_metric.values()),
        "of": len(results),
        "by_metric": {m: {"within": by_metric[m], "of": totals[m]} for m in totals},
    }


def _beat_shares(spec: StrategySpec, series: Series) -> list[dict[str, Any]]:
    first, last = spec.sample_start.value, spec.sample_end.value
    bench_returns, bench_months = series(None, None, first, last, "reset")
    bench = metrics.calendar_year_returns(bench_returns, bench_months)
    shares: list[dict[str, Any]] = []
    for lookback in spec.lookbacks_months.value:
        for top_n in spec.top_n.value:
            returns, months = series(lookback, top_n, first, last, "reset")
            years = metrics.calendar_year_returns(returns, months)
            beat = sum(1 for year, value in years.items() if value > bench[year])
            shares.append(
                {
                    "lookback": lookback,
                    "top_n": top_n,
                    "years": len(years),
                    "beat": beat,
                    "share": beat / len(years),
                }
            )
    return shares


def _next_index(out_dir: Path) -> int:
    taken = [int(m.group(1)) for p in out_dir.iterdir() if (m := _PREVIOUS.match(p.name))]
    return max(taken, default=0) + 1


def run_test1(root: Path, rerun: str | None = None) -> Outcome:
    """Run Test 1 in the repository at ``root``, after every guard has passed."""
    if rerun is not None and not rerun.strip():
        raise RunRefused("--rerun needs a reason")
    _check_committed(root)
    problems = lock_problems(root / PREREG_DIR)
    if problems:
        raise RunRefused("the pre-registration lock fails: " + "; ".join(problems))
    out_dir = root / OUT_DIR
    result_path, report_path = out_dir / "result.json", out_dir / "REPORT.md"
    if result_path.exists() and rerun is None:
        raise RunRefused(
            f"{OUT_DIR}/result.json already exists and Test 1 runs once. "
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
    spec = _load_checked_spec(root / SPEC)

    series = _series(data)
    tested = [c for c in spec.claims if _tested(c)]
    results = [_evaluate(c, series) for c in tested]
    strategy_claims = [c for c in tested if c.subject is Subject.STRATEGY]
    strategy = [r for r in results if r.subject == Subject.STRATEGY.value]
    checks = {
        r.metric: r
        for r in results
        if r.subject == Subject.BENCHMARK.value and r.metric in DATA_CHECK_METRICS
    }
    passed = all(checks[m].within for m in DATA_CHECK_METRICS)
    counts = _counts(strategy)
    outcome_verdict = verdict(passed, counts["within"])

    previous = None
    if result_path.exists():
        n = _next_index(out_dir)
        previous = f"result-{n}.json"
        result_path.rename(out_dir / previous)
        if report_path.exists():
            report_path.rename(out_dir / f"REPORT-{n}.md")

    result: dict[str, Any] = {
        "test": "Test 1 (reproduce)",
        "paper": {"title": spec.paper.title, "year": spec.paper.year},
        "verdict": outcome_verdict,
        "strategy_claims": counts,
        "data_check": {
            "passed": passed,
            **{m: checks[m].to_json() for m in DATA_CHECK_METRICS},
        },
        "sensitivity": {
            "drift_weights": _counts([_evaluate(c, series, "drift") for c in strategy_claims]),
            "volatility_ddof_0": _counts([_evaluate(c, series, ddof=0) for c in strategy_claims]),
        },
        "beat_benchmark": {
            "first": spec.sample_start.value,
            "last": spec.sample_end.value,
            "versions": _beat_shares(spec, series),
        },
        "claims": [r.to_json() for r in results],
        "not_tested": [{"id": c.id, "metric": c.metric} for c in spec.claims if not _tested(c)],
        "lookbacks": spec.lookbacks_months.value,
        "top_n": spec.top_n.value,
        "tolerances": TOLERANCES,
        "commits": commits,
        "data": {
            "csv": CSV,
            "csv_sha256": sha256_of(root / CSV),
            "pinned_csv_sha256": pins["csv_sha256"],
            "zip_sha256": pins.get("zip_sha256"),
            "downloaded": pins.get("downloaded"),
        },
        "rerun": None if rerun is None else {"reason": rerun, "previous": previous},
        "run_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(render_report(result), encoding="utf-8")
    return Outcome(
        verdict=outcome_verdict,
        within=counts["within"],
        total=counts["of"],
        result_path=result_path,
        report_path=report_path,
    )


def _number(metric: str, value: float, signed: bool = False) -> str:
    digits = 3 if metric == "Sharpe ratio" else 2
    return f"{value:+.{digits}f}" if signed else f"{value:.{digits}f}"


def _unit(metric: str) -> str:
    return "" if metric == "Sharpe ratio" else " pp"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _grid(
    lookbacks: Sequence[int],
    top_ns: Sequence[int],
    cell: Callable[[int, int], str],
) -> list[str]:
    header = ["Lookback", *(f"Top{n}" for n in top_ns)]
    rows = [[f"{lookback} mo", *(cell(lookback, n) for n in top_ns)] for lookback in lookbacks]
    return _table(header, rows)


def render_report(result: dict[str, Any]) -> str:
    """REPORT.md: the verdict first, then every number behind it."""
    counts = result["strategy_claims"]
    check = result["data_check"]
    claims = result["claims"]
    lookbacks, top_ns = result["lookbacks"], result["top_n"]
    lines = [
        f"# Test 1 (reproduce): {result['paper']['title']} ({result['paper']['year']})",
        "",
        f"**Verdict: {result['verdict']}.** {counts['within']} of {counts['of']} strategy "
        "claims are within tolerance.",
        "",
        f"Pre-registered bands: reproduced at least {REPRODUCED_MIN}, partly reproduced "
        f"{PARTLY_MIN} to {REPRODUCED_MIN - 1}, not reproduced fewer than {PARTLY_MIN}; "
        f'"{INCONCLUSIVE}" if the data check fails.',
        "",
    ]
    parts = [
        f"{m}: ours {_number(m, check[m]['ours'])}, paper {_number(m, check[m]['paper'])}, "
        f"difference {_number(m, check[m]['difference'], signed=True)}{_unit(m)} "
        f"(tolerance {_number(m, check[m]['tolerance'])})"
        for m in DATA_CHECK_METRICS
    ]
    lines += [
        f"Data check, benchmark: **{'passed' if check['passed'] else 'failed'}**. "
        + "; ".join(parts)
        + ".",
        "",
    ]
    if result["rerun"] is not None:
        previous = result["rerun"]["previous"] or "none"
        lines += [f"Rerun. Reason: {result['rerun']['reason']}. Previous result: {previous}.", ""]

    lines += ["## Strategy claims within tolerance, by metric", ""]
    lines += _table(
        ["Metric", "Within", "Of", "Tolerance"],
        [
            [m, str(c["within"]), str(c["of"]), f"{_number(m, TOLERANCES[m])}{_unit(m)}"]
            for m, c in counts["by_metric"].items()
        ],
    )
    lines += [
        "",
        "## Differences, ours minus the paper",
        "",
        "Rows are lookbacks, columns are Top N. A cell outside tolerance is bold and marked ✗.",
    ]
    strategy = {
        (c["metric"], c["lookback"], c["top_n"]): c for c in claims if c["subject"] == "strategy"
    }
    for metric in counts["by_metric"]:

        def cell(lookback: int, top_n: int, metric: str = metric) -> str:
            claim = strategy.get((metric, lookback, top_n))
            if claim is None:
                return "—"
            text = _number(metric, claim["difference"], signed=True)
            return text if claim["within"] else f"**{text} ✗**"

        lines += [
            "",
            f"### {metric} (tolerance {_number(metric, TOLERANCES[metric])}{_unit(metric)})",
            "",
        ]
        lines += _grid(lookbacks, top_ns, cell)

    lines += ["", "## Benchmark claims", ""]
    lines += _table(
        ["Claim", "Metric", "Paper", "Ours", "Difference", "Tolerance", "Within"],
        [
            [
                c["id"],
                c["metric"],
                _number(c["metric"], c["paper"]),
                _number(c["metric"], c["ours"]),
                _number(c["metric"], c["difference"], signed=True),
                _number(c["metric"], c["tolerance"]),
                "yes" if c["within"] else "**no**",
            ]
            for c in claims
            if c["subject"] == "benchmark"
        ],
    )
    not_tested = ", ".join(f"{c['id']} ({c['metric']})" for c in result["not_tested"]) or "none"
    lines += ["", f"Not tested, as pre-registered: {not_tested}.", ""]

    lines += [
        "## Sensitivity checks",
        "",
        "Reported only; they never change the verdict. Strategy claims within tolerance when the "
        "weights drift between rebalances (each held sector starts at equal weight in the first "
        "holding month), and when volatility, and so the Sharpe ratio, uses ddof = 0.",
        "",
    ]
    sensitivity = result["sensitivity"]
    labels = {"drift_weights": "Drift weights", "volatility_ddof_0": "Volatility ddof = 0"}
    metric_names = list(counts["by_metric"])
    lines += _table(
        ["Check", "Within", "Of", *metric_names],
        [
            [
                labels[key],
                str(sensitivity[key]["within"]),
                str(sensitivity[key]["of"]),
                *(str(sensitivity[key]["by_metric"][m]["within"]) for m in metric_names),
            ]
            for key in labels
        ],
    )

    beat = result["beat_benchmark"]
    shares = {(v["lookback"], v["top_n"]): v for v in beat["versions"]}
    years = beat["versions"][0]["years"]
    lines += [
        "",
        "## Share of calendar years beating the benchmark",
        "",
        f"Calendar years {beat['first'][:4]} to {beat['last'][:4]} ({years} years) in which the "
        "version's return was above the benchmark's. No verdict.",
        "",
    ]
    lines += _grid(lookbacks, top_ns, lambda lb, n: f"{shares[(lb, n)]['share']:.0%}")

    commits, data = result["commits"], result["data"]
    lines += [
        "",
        "## Provenance",
        "",
        f"- Pre-registration: `{commits['preregistration']}`",
        f"- Amendment 01: `{commits['amendment_01']}`",
        f"- Spec: `{commits['spec']}`",
        f"- Code: `{commits['code']}`",
        f"- Data: `{data['csv']}`, SHA-256 `{data['csv_sha256']}` (pin "
        f"`{data['pinned_csv_sha256']}`), zip SHA-256 `{data['zip_sha256']}`, "
        f"downloaded {data['downloaded']}",
        f"- Run at (UTC): {result['run_at_utc']}",
        "",
    ]
    return "\n".join(lines)
