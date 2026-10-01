"""compute_diff skips generated/vendored paths by default (lockfiles, vendored harness)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from geap_harness.gitdiff import compute_diff


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@e", *args],
                   check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "app.py").write_text("x = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "app.py").write_text("x = 2\n")
    (repo / "uv.lock").write_text("lock\n")
    (repo / ".geap" / "geap-harness").mkdir(parents=True)
    (repo / ".geap" / "geap-harness" / "mod.py").write_text("y = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "head")
    return repo


def test_default_excludes(tmp_path, monkeypatch):
    monkeypatch.delenv("GEAP_GATE_DIFF_EXCLUDE", raising=False)
    d = compute_diff(_repo(tmp_path), "HEAD~1", "HEAD")
    assert d.files == ["app.py"]
    assert "uv.lock" not in d.text and "geap-harness" not in d.text


def test_empty_override_disables_excludes(tmp_path, monkeypatch):
    monkeypatch.setenv("GEAP_GATE_DIFF_EXCLUDE", "")
    d = compute_diff(_repo(tmp_path), "HEAD~1", "HEAD")
    assert d.files == [".geap/geap-harness/mod.py", "app.py", "uv.lock"]
