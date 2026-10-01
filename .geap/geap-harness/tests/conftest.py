from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = HARNESS_DIR.parent
SHOWCASE = REPO_ROOT / "showcase-app"
FIXED_NOW = "2026-09-30T00:00:00Z"

_IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".venv", "*.pyc", ".geap/cache", "cache", "uv.lock")


def git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
    }
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
                          env=env).stdout.strip()


def commit_all(repo: Path, msg: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


AUTHZ_FIX = (
    '    """Update customer contact details (legacy endpoint)."""\n'
    '    authorize_customer_access(principal, req.customer_id, action="write")\n'
)


def apply_authz_fix(repo: Path) -> None:
    p = repo / "app" / "routers" / "customers.py"
    src = p.read_text()
    marker = '    """Update customer contact details (legacy endpoint)."""\n'
    assert marker in src and "authorize_customer_access(principal, req.customer_id" not in src
    p.write_text(src.replace(marker, AUTHZ_FIX, 1))


@pytest.fixture
def showcase_repo(tmp_path: Path) -> dict:
    """git repo: c0 = README only, c1 = current showcase-app (with the intentional gap)."""
    if not SHOWCASE.is_dir():
        pytest.skip("showcase-app/ not present")
    repo = tmp_path / "cps"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("# init\n")
    c0 = commit_all(repo, "init")
    for item in SHOWCASE.iterdir():
        if item.name in ("README.md", ".pytest_cache", ".venv", "__pycache__", "uv.lock"):
            continue
        dst = repo / item.name
        if item.is_dir():
            shutil.copytree(item, dst, ignore=_IGNORE)
        else:
            shutil.copy2(item, dst)
    (repo / "README.md").write_text("# cps\n")
    c1 = commit_all(repo, "customer profile service")
    return {"repo": repo, "c0": c0, "c1": c1}
