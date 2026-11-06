"""Pre-registration files are immutable: each is pinned by a SHA-256 in LOCKS.sha256."""

import hashlib
from pathlib import Path

PREREG_DIR = Path(__file__).resolve().parent.parent / "prereg"
LOCK_FILE = PREREG_DIR / "LOCKS.sha256"
HINT = "Committed pre-registration files never change; make a new dated amendment file instead."


def _read_locks() -> dict[str, str]:
    locks: dict[str, str] = {}
    for line in LOCK_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        locks[name.strip().lstrip("*")] = digest.strip()
    return locks


def _prereg_files() -> set[str]:
    return {p.name for p in PREREG_DIR.iterdir() if p.is_file() and p.name != LOCK_FILE.name}


def test_every_prereg_file_is_locked() -> None:
    missing = sorted(_prereg_files() - set(_read_locks()))
    assert not missing, f"prereg/ file(s) not listed in LOCKS.sha256: {missing}. {HINT}"


def test_every_locked_file_exists() -> None:
    gone = sorted(name for name in _read_locks() if not (PREREG_DIR / name).is_file())
    assert not gone, f"File(s) listed in LOCKS.sha256 are missing from prereg/: {gone}. {HINT}"


def test_hashes_match() -> None:
    for name, expected in sorted(_read_locks().items()):
        path = PREREG_DIR / name
        if not path.is_file():
            continue  # reported by test_every_locked_file_exists
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, f"prereg/{name} has changed since it was locked. {HINT}"
