"""Verdict/review cache: local ``.geap/cache/<key>.json`` plus optional GCS mirror (gcloud storage)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from .models import ReviewResult


def compute_cache_key(diff_text: str, model: str, skill_shas: dict[str, str], prompt_hash: str,
                      policy_hash: str) -> str:
    """sha256(diff ∥ model ∥ sorted skill shas ∥ prompt hash ∥ policy hash) — PLATFORM_CONTRACTS §6."""
    h = hashlib.sha256()
    for part in (diff_text, model, ",".join(sorted(skill_shas.values())), prompt_hash, policy_hash):
        h.update(part.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


class Cache:
    def __init__(self, cache_dir: Path, cache_uri: str | None = None):
        self.dir = Path(cache_dir)
        self.uri = (cache_uri or "").rstrip("/") or None
        if self.uri and not self.uri.startswith("gs://"):
            raise ValueError("--cache-uri must be a gs:// URI")

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    @staticmethod
    def _gcloud() -> str | None:
        return shutil.which("gcloud")

    def get(self, key: str) -> ReviewResult | None:
        p = self._path(key)
        if not p.is_file() and self.uri and self._gcloud():
            self.dir.mkdir(parents=True, exist_ok=True)
            subprocess.run([self._gcloud(), "storage", "cp", f"{self.uri}/{key}.json", str(p), "--quiet"],
                           capture_output=True, check=False)
        if not p.is_file():
            return None
        try:
            return ReviewResult.model_validate_json(p.read_text(encoding="utf-8"))
        except ValueError:
            return None

    def put(self, key: str, review: ReviewResult) -> bool:
        """Returns True when the entry is persisted locally (GCS upload is best-effort)."""
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            p = self._path(key)
            p.write_text(canonical_json(review.model_dump()), encoding="utf-8")
        except OSError:
            return False
        if self.uri and self._gcloud():
            subprocess.run([self._gcloud(), "storage", "cp", str(p), f"{self.uri}/{key}.json", "--quiet"],
                           capture_output=True, check=False)
        return True
