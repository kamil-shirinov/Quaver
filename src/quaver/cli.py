"""Command-line entry point: ``quaver <command>``, one subcommand per check."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml
from pydantic import ValidationError

from quaver.data import DataError, load_french10
from quaver.quotes import check_quotes, load_pages
from quaver.readings import claim_key, compare_claims, describe_key, load_claims, locate
from quaver.spec import Provenance, StrategySpec, load_spec, provenance_counts
from quaver.test1 import RunRefused, run_test1

DEFAULT_CSV = Path("data/raw/10_Industry_Portfolios.csv")
DEFAULT_PINS = Path("data/pins.json")


def _format_errors(error: ValidationError) -> str:
    lines = [
        f"{'.'.join(str(part) for part in e['loc']) or '<root>'}: {e['msg']}"
        for e in error.errors()
    ]
    return "\n".join(lines)


def _load_or_report(path: Path) -> StrategySpec | None:
    try:
        return load_spec(path)
    except ValidationError as error:
        print(f"invalid: {path}\n{_format_errors(error)}", file=sys.stderr)
    except (OSError, yaml.YAMLError) as error:
        print(f"invalid: {path}\n{error}", file=sys.stderr)
    return None


def _validate_spec(path: Path) -> int:
    spec = _load_or_report(path)
    if spec is None:
        return 1
    counts = provenance_counts(spec)
    n_claims = len(spec.claims)
    claims = "1 claim" if n_claims == 1 else f"{n_claims} claims"
    print(
        f"valid: {spec.paper.title} ({spec.paper.year}), {claims}, "
        f"sources: {counts[Provenance.STATED]} stated, "
        f"{counts[Provenance.INFERRED]} inferred, "
        f"{counts[Provenance.ASSUMED]} assumed, "
        f"{counts[Provenance.TABLE]} table"
        + (", unverified" if spec.extraction.verified_by is None else "")
    )
    return 0


def _check_quotes(spec_path: Path, text_path: Path) -> int:
    spec = _load_or_report(spec_path)
    if spec is None:
        return 1
    try:
        pages = load_pages(text_path)
    except (OSError, ValueError) as error:
        print(f"invalid: {text_path}\n{error}", file=sys.stderr)
        return 1
    result = check_quotes(spec, pages)
    for failure in result.failures:
        page = "no page" if failure.page is None else f"page {failure.page}"
        print(f"not found: {failure.where}, {page}: {failure.quote!r}")
    if result.failures:
        print(f"{len(result.failures)} of {result.checked} quotes not found", file=sys.stderr)
        return 1
    values = "1 table value" if result.skipped == 1 else f"{result.skipped} table values"
    print(f"all {result.checked} quotes found, {values} skipped (not quotable)")
    return 0


def _compare_readings(path_a: Path, path_b: Path) -> int:
    try:
        claims_a, claims_b = load_claims(path_a), load_claims(path_b)
    except ValidationError as error:
        print(f"invalid readings\n{_format_errors(error)}", file=sys.stderr)
        return 1
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"invalid readings\n{error}", file=sys.stderr)
        return 1
    result = compare_claims(claims_a, claims_b)
    print(f"matched {result.matched} claim" + ("" if result.matched == 1 else "s"))
    for diff in result.differing:
        print(f"differs: {describe_key(claim_key(diff.a))}")
        print(f"  A {diff.a.id}: {diff.a.value} ({locate(diff.a.source)})")
        print(f"  B {diff.b.id}: {diff.b.value} ({locate(diff.b.source)})")
    for label, claims in (("A", result.only_a), ("B", result.only_b)):
        for claim in claims:
            print(f"only in {label}: {claim.id}, {describe_key(claim_key(claim))}")
    if result.agrees:
        return 0
    print(
        f"{len(result.differing)} differ, {len(result.only_a)} only in A, "
        f"{len(result.only_b)} only in B",
        file=sys.stderr,
    )
    return 1


def _data_check(csv: Path, pins: Path) -> int:
    try:
        data = load_french10(csv, pins)
    except (OSError, DataError) as error:
        print(f"invalid: {error}", file=sys.stderr)
        return 1
    print(
        f"{csv.name}: {len(data.months)} months, {data.months[0]} to {data.months[-1]}, "
        f"{len(data.industries)} industries, no missing values"
    )
    return 0


def _run_test1(rerun: str | None) -> int:
    try:
        outcome = run_test1(Path.cwd(), rerun)
    except RunRefused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    print(
        f"Test 1 (reproduce): {outcome.verdict}, {outcome.within} of {outcome.total} "
        "strategy claims within tolerance"
    )
    print(f"wrote {outcome.result_path} and {outcome.report_path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quaver")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-spec", help="validate a strategy spec file")
    validate.add_argument("path", type=Path)
    quotes = subparsers.add_parser(
        "check-quotes", help="check that every quote in a spec appears on its cited page"
    )
    quotes.add_argument("spec", type=Path)
    quotes.add_argument("text", type=Path, help='paper text with "=== page N ===" markers')
    compare = subparsers.add_parser(
        "compare-readings", help="compare the claims of two independent readings of one paper"
    )
    compare.add_argument("a", type=Path, help="YAML file with a claims list (a full spec works)")
    compare.add_argument("b", type=Path, help="YAML file with a claims list (nothing else needed)")
    check = subparsers.add_parser(
        "data-check", help="verify the pinned French 10 industry file and parse it"
    )
    check.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    check.add_argument("--pins", type=Path, default=DEFAULT_PINS)
    test1 = subparsers.add_parser(
        "run-test1", help="run Test 1 (reproduce) of pre-registration 0001; it runs once"
    )
    test1.add_argument(
        "--rerun",
        metavar="REASON",
        help="run again although a result exists; the old result is kept and the reason recorded",
    )
    args = parser.parse_args(argv)
    if args.command == "run-test1":
        return _run_test1(args.rerun)
    if args.command == "data-check":
        return _data_check(args.csv, args.pins)
    if args.command == "check-quotes":
        return _check_quotes(args.spec, args.text)
    if args.command == "compare-readings":
        return _compare_readings(args.a, args.b)
    return _validate_spec(args.path)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
