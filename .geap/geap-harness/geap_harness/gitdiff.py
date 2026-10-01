"""Git helpers: diff base..head and read files at a commit (never the working tree)."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


class GitError(RuntimeError):
    pass


def _git(repo_dir: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=false", "-C", str(repo_dir), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


@dataclass
class DiffInfo:
    base: str
    head: str
    text: str
    files: list[str] = field(default_factory=list)  # changed (added/modified) files at head, sorted
    deleted: list[str] = field(default_factory=list)
    added_lines: dict[str, set[int]] = field(default_factory=dict)  # path -> head line numbers added/changed


def resolve_sha(repo_dir: Path, rev: str) -> str:
    return _git(repo_dir, "rev-parse", "--verify", f"{rev}^{{commit}}").strip()


def compute_diff(repo_dir: Path, base: str, head: str) -> DiffInfo:
    """Unified diff base..head (no renames, no colour, stable options)."""
    base_sha, head_sha = resolve_sha(repo_dir, base), resolve_sha(repo_dir, head)
    text = _git(
        repo_dir, "diff", "--no-color", "--no-ext-diff", "--no-renames", "--unified=3",
        f"{base_sha}", f"{head_sha}",
    )
    info = DiffInfo(base=base_sha, head=head_sha, text=text)
    cur: str | None = None
    old: str | None = None
    line_no = 0
    for raw in text.splitlines():
        if raw.startswith("--- "):
            old = raw[4:]
            continue
        if raw.startswith("+++ "):
            target = raw[4:]
            if target == "/dev/null":
                cur = None
                if old and old.startswith("a/"):
                    info.deleted.append(old[2:])
            else:
                cur = target[2:] if target.startswith("b/") else target
                info.added_lines.setdefault(cur, set())
            continue
        m = _HUNK.match(raw)
        if m:
            line_no = int(m.group(1))
            continue
        if cur is None or raw.startswith("diff --git") or raw.startswith("index "):
            continue
        if raw.startswith("+"):
            info.added_lines[cur].add(line_no)
            line_no += 1
        elif raw.startswith("-") or raw.startswith("\\"):
            continue
        else:
            line_no += 1
    info.files = sorted(info.added_lines)
    info.deleted = sorted(set(info.deleted))
    return info


def read_at(repo_dir: Path, rev: str, path: str) -> str | None:
    """File content at ``rev`` or None if absent/binary."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_dir), "show", f"{rev}:{path}"],
            capture_output=True, check=False,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    try:
        return out.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None


def list_files(repo_dir: Path, rev: str) -> list[str]:
    return sorted(p for p in _git(repo_dir, "ls-tree", "-r", "--name-only", rev).splitlines() if p)
