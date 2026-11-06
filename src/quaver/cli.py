"""Command-line entry point: ``quaver validate-spec PATH``."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml
from pydantic import ValidationError

from quaver.spec import Provenance, load_spec, provenance_counts


def _format_errors(error: ValidationError) -> str:
    lines = [
        f"{'.'.join(str(part) for part in e['loc']) or '<root>'}: {e['msg']}"
        for e in error.errors()
    ]
    return "\n".join(lines)


def _validate_spec(path: Path) -> int:
    try:
        spec = load_spec(path)
    except ValidationError as error:
        print(f"invalid: {path}\n{_format_errors(error)}", file=sys.stderr)
        return 1
    except (OSError, yaml.YAMLError) as error:
        print(f"invalid: {path}\n{error}", file=sys.stderr)
        return 1
    counts = provenance_counts(spec)
    n_claims = len(spec.claims)
    claims = "1 claim" if n_claims == 1 else f"{n_claims} claims"
    print(
        f"valid: {spec.paper.title} ({spec.paper.year}), {claims}, "
        f"sources: {counts[Provenance.STATED]} stated, "
        f"{counts[Provenance.INFERRED]} inferred, "
        f"{counts[Provenance.ASSUMED]} assumed"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quaver")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-spec", help="validate a strategy spec file")
    validate.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    return _validate_spec(args.path)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
