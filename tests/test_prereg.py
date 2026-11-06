"""Tests for the pre-registration lock check, on made-up files in a temporary directory."""

import hashlib
from pathlib import Path

from quaver.prereg import LOCK_FILE, lock_problems, read_locks


def locked_dir(tmp_path: Path) -> Path:
    prereg = tmp_path / "prereg"
    prereg.mkdir()
    lines = []
    for name, text in (("a.md", "first\n"), ("b.md", "second\n")):
        (prereg / name).write_text(text, encoding="utf-8")
        lines.append(f"{hashlib.sha256(text.encode()).hexdigest()}  {name}")
    (prereg / LOCK_FILE).write_text("\n".join(lines) + "\n\n", encoding="utf-8")
    return prereg


def test_lock_holds(tmp_path: Path) -> None:
    prereg = locked_dir(tmp_path)
    assert lock_problems(prereg) == []
    assert set(read_locks(prereg)) == {"a.md", "b.md"}


def test_binary_marker_is_accepted(tmp_path: Path) -> None:
    prereg = locked_dir(tmp_path)
    lock = prereg / LOCK_FILE
    lock.write_text(lock.read_text(encoding="utf-8").replace("  a.md", "  *a.md"), "utf-8")
    assert lock_problems(prereg) == []


def test_missing_lock_file(tmp_path: Path) -> None:
    prereg = locked_dir(tmp_path)
    (prereg / LOCK_FILE).unlink()
    assert lock_problems(prereg) == [f"{prereg / LOCK_FILE} is missing"]


def test_unlocked_file(tmp_path: Path) -> None:
    prereg = locked_dir(tmp_path)
    (prereg / "c.md").write_text("third\n", encoding="utf-8")
    assert lock_problems(prereg) == [f"c.md is not listed in {LOCK_FILE}"]


def test_locked_file_missing(tmp_path: Path) -> None:
    prereg = locked_dir(tmp_path)
    (prereg / "b.md").unlink()
    assert lock_problems(prereg) == [f"b.md is listed in {LOCK_FILE} but missing"]


def test_changed_file(tmp_path: Path) -> None:
    prereg = locked_dir(tmp_path)
    (prereg / "a.md").write_text("first, edited\n", encoding="utf-8")
    assert lock_problems(prereg) == ["a.md has changed since it was locked"]
