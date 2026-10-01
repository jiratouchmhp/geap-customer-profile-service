"""Review backends: ``offline`` (deterministic heuristics), ``sdk`` (Antigravity SDK), ``cli`` (agy)."""

from __future__ import annotations

from pathlib import Path

from ..gitdiff import DiffInfo
from ..inputs import Skill
from ..models import ReviewResult

BACKENDS = ("offline", "sdk", "cli")


class BackendError(RuntimeError):
    pass


def default_model(backend: str, model: str | None) -> str:
    """Model id recorded in the verdict / cache key. Offline = versioned rule set."""
    if backend == "offline":
        from .offline import OFFLINE_MODEL

        return OFFLINE_MODEL
    if model:
        return model
    # SDK/CLI default model (unpinned). Pin GEAP_HARNESS_REVIEW_MODEL for reproducible gates.
    return f"{backend}-default"


def run_backend(
    backend: str,
    *,
    repo_dir: Path,
    diff: DiffInfo,
    prompt: str,
    skills: list[Skill],
    model: str,
    timeout_s: int = 600,
) -> ReviewResult:
    if backend == "offline":
        from .offline import review

        return review(repo_dir, diff, model=model)
    if backend == "sdk":
        from .sdk import review

        return review(repo_dir, diff, prompt=prompt, skills=skills, model=model, timeout_s=timeout_s)
    if backend == "cli":
        from .cli import review

        return review(repo_dir, diff, prompt=prompt, skills=skills, model=model, timeout_s=timeout_s)
    raise BackendError(f"unknown backend {backend!r}; expected one of {BACKENDS}")
