"""``agy`` CLI backend: ``agy -p <prompt> --output-format json --json-schema <file> --sandbox --mode plan``."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..gitdiff import DiffInfo
from ..inputs import Skill
from ..models import FindingList, ReviewResult, sort_findings
from . import BackendError


def _find_finding_list(obj: Any) -> dict | None:
    """agy's JSON envelope may nest the structured result; locate the FindingList dict."""
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except ValueError:
            return None
    if isinstance(obj, dict):
        if isinstance(obj.get("findings"), list):
            return obj
        for key in ("structured_output", "result", "response", "output", "content", "text"):
            if key in obj:
                hit = _find_finding_list(obj[key])
                if hit is not None:
                    return hit
        for v in obj.values():
            hit = _find_finding_list(v)
            if hit is not None:
                return hit
    if isinstance(obj, list):
        for v in obj:
            hit = _find_finding_list(v)
            if hit is not None:
                return hit
    return None


def build_command(repo_dir: Path, prompt: str, schema_path: Path, model: str, timeout_s: int) -> list[str]:
    agy = os.environ.get("GEAP_AGY_BIN") or shutil.which("agy") or "agy"
    cmd = [agy, "-p", prompt, "--output-format", "json", "--json-schema", str(schema_path),
           "--sandbox", "--mode", "plan", "--add-dir", str(repo_dir), "--print-timeout", f"{timeout_s}s"]
    if model and not model.endswith("-default"):
        cmd += ["--model", model]
    return cmd


def review(repo_dir: Path, diff: DiffInfo, *, prompt: str, skills: list[Skill], model: str,
           timeout_s: int = 600) -> ReviewResult:
    skill_note = "\n\nApply these enterprise skills (full text follows):\n" + "\n\n".join(
        f"=== SKILL {s.name} (sha256 {s.sha[:12]}) ===\n{s.body}" for s in skills)
    with tempfile.TemporaryDirectory() as td:
        schema_path = Path(td) / "finding_list.schema.json"
        schema_path.write_text(json.dumps(FindingList.model_json_schema(), sort_keys=True))
        cmd = build_command(repo_dir, prompt + skill_note, schema_path, model, timeout_s)
        try:
            proc = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True, timeout=timeout_s + 30,
                                  check=False)
        except FileNotFoundError as exc:
            raise BackendError("backend 'cli' needs the Antigravity CLI `agy` on PATH (or GEAP_AGY_BIN)") from exc
        except subprocess.TimeoutExpired as exc:
            raise BackendError(f"agy timed out after {timeout_s}s") from exc
    if proc.returncode != 0:
        raise BackendError(f"agy exited {proc.returncode}: {proc.stderr.strip()[-500:]}")
    data = _find_finding_list(proc.stdout.strip())
    if data is None:
        raise BackendError(f"agy output did not contain a FindingList: {proc.stdout[:300]}")
    fl = FindingList.model_validate(data)
    return ReviewResult(backend="cli", model=model, summary=fl.summary, findings=sort_findings(fl.findings),
                        usage={"model": model})
