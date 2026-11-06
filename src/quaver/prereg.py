"""Pre-registration locks: every file in prereg/ is pinned by a SHA-256 in LOCKS.sha256."""

import hashlib
from pathlib import Path

LOCK_FILE = "LOCKS.sha256"


def read_locks(prereg_dir: Path) -> dict[str, str]:
    """The pinned SHA-256 of each file, keyed by file name (``shasum -a 256`` format)."""
    locks: dict[str, str] = {}
    for line in (prereg_dir / LOCK_FILE).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        locks[name.strip().lstrip("*")] = digest.strip()
    return locks


def lock_problems(prereg_dir: Path) -> list[str]:
    """Every way prereg/ differs from its locks. An empty list means the lock holds."""
    if not (prereg_dir / LOCK_FILE).is_file():
        return [f"{prereg_dir / LOCK_FILE} is missing"]
    locks = read_locks(prereg_dir)
    files = {p.name for p in prereg_dir.iterdir() if p.is_file() and p.name != LOCK_FILE}
    problems = [f"{name} is not listed in {LOCK_FILE}" for name in sorted(files - set(locks))]
    for name, expected in sorted(locks.items()):
        path = prereg_dir / name
        if not path.is_file():
            problems.append(f"{name} is listed in {LOCK_FILE} but missing")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            problems.append(f"{name} has changed since it was locked")
    return problems
