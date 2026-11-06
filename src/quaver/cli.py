"""Command-line entry point: ``quaver validate-spec SPEC`` and ``quaver check-quotes SPEC TEXT``."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml
from pydantic import ValidationError

from quaver.quotes import check_quotes, load_pages
from quaver.spec import Provenance, StrategySpec, load_spec, provenance_counts


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
        f"{counts[Provenance.ASSUMED]} assumed"
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
    checked, failures = check_quotes(spec, pages)
    for failure in failures:
        page = "no page" if failure.page is None else f"page {failure.page}"
        print(f"not found: {failure.where}, {page}: {failure.quote!r}")
    if failures:
        print(f"{len(failures)} of {checked} quotes not found", file=sys.stderr)
        return 1
    print(f"all {checked} quotes found")
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
    args = parser.parse_args(argv)
    if args.command == "check-quotes":
        return _check_quotes(args.spec, args.text)
    return _validate_spec(args.path)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
