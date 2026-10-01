"""Publish a gate verdict to GitHub: check run 'GEAP AI Gate' + one upserted PR comment.

Uses only ``GITHUB_TOKEN``, ``GITHUB_REPOSITORY``, ``GITHUB_EVENT_PATH`` (+ ``GITHUB_SHA``,
``GITHUB_API_URL``, ``GITHUB_SERVER_URL``, ``GITHUB_RUN_ID``). Outside GitHub Actions it is a no-op.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import httpx

from .models import Verdict
from .policy import parse_ref

CHECK_NAME = "GEAP AI Gate"
COMMENT_MARKER = "<!-- geap-ai-gate -->"
_LEVEL = {"Critical": "failure", "Required": "warning", "Advisory": "notice"}
_ICON = {"Critical": "🔴", "Required": "🟠", "Advisory": "🔵"}


@dataclass
class PublishResult:
    published: bool
    message: str
    check_run_id: int | None = None
    comment_id: int | None = None


def render_markdown(v: Verdict, run_url: str | None = None) -> str:
    head = "✅ **GEAP AI Gate: PASS**" if v.verdict == "pass" else "❌ **GEAP AI Gate: FAIL**"
    lines = [COMMENT_MARKER, f"### {head}", ""]
    lines.append("| Rule | Result | Detail |")
    lines.append("|---|---|---|")
    for r in v.rules:
        lines.append(f"| `{r.id}` | {'✅' if r.passed else '❌'} | {r.detail.replace('|', '/')} |")
    if not v.rules:
        lines.append("| _(no policy)_ | – | review only |")
    lines += ["", f"**Findings ({len(v.findings)})**", ""]
    if v.findings:
        for f in v.findings:
            ev = ", ".join(f"`{e}`" for e in f.evidence_refs)
            lines.append(f"- {_ICON.get(f.severity, '')} **{f.severity}** `{f.control_id or f.rule_id}` — "
                         f"{f.message} ({ev})")
    else:
        lines.append("_No findings._")
    skills = ", ".join(f"`{k}@{s[:10]}`" for k, s in v.skill_shas.items())
    lines += [
        "",
        "<details><summary>Determinism record</summary>",
        "",
        f"- model: `{v.model}`",
        f"- cache_key: `{v.cache_key}`",
        f"- reproducible: `{str(v.reproducible).lower()}`",
        f"- prompt_hash: `{v.prompt_hash[:16]}` · policy_hash: `{v.policy_hash[:16]}`",
        f"- skills: {skills}",
        "",
        "</details>",
        "",
        "_The LLM proposes findings; the deterministic policy in `.geap/policy.yaml` decides. "
        "Merge and production deploy remain human decisions._",
    ]
    if run_url:
        lines.append(f"\n[Workflow run]({run_url})")
    return "\n".join(lines) + "\n"


def annotations(v: Verdict) -> list[dict]:
    out = []
    for f in v.findings:
        for ref in f.evidence_refs[:1]:
            p = parse_ref(ref)
            if not p or p.start is None:
                continue
            out.append({
                "path": p.path, "start_line": p.start, "end_line": p.end or p.start,
                "annotation_level": _LEVEL.get(f.severity, "notice"),
                "title": f"{f.severity}: {f.control_id or f.rule_id}",
                "message": f.message[:1000] + (f"\n\n{f.rationale}" if f.rationale else ""),
            })
    return out[:50]  # API limit per request


def _event(env: dict) -> dict:
    p = env.get("GITHUB_EVENT_PATH")
    if p and Path(p).is_file():
        try:
            return json.loads(Path(p).read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def publish(v: Verdict, *, sha: str | None = None, pr_number: int | None = None,
            client: httpx.Client | None = None, env: dict | None = None) -> PublishResult:
    env = dict(os.environ if env is None else env)
    token, repo = env.get("GITHUB_TOKEN"), env.get("GITHUB_REPOSITORY")
    if env.get("GITHUB_ACTIONS") != "true" or not token or not repo:
        return PublishResult(False, "not running in GitHub Actions with GITHUB_TOKEN/GITHUB_REPOSITORY; "
                                    "skipping publish (verdict: %s)" % v.verdict)
    event = _event(env)
    pr = event.get("pull_request") or {}
    sha = sha or (pr.get("head") or {}).get("sha") or env.get("GITHUB_SHA")
    pr_number = pr_number or pr.get("number")
    server = env.get("GITHUB_SERVER_URL", "https://github.com")
    run_url = f"{server}/{repo}/actions/runs/{env['GITHUB_RUN_ID']}" if env.get("GITHUB_RUN_ID") else None
    body = render_markdown(v, run_url)

    own = client is None
    client = client or httpx.Client(
        base_url=env.get("GITHUB_API_URL", "https://api.github.com"), timeout=30.0,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    try:
        check_id = None
        if sha:
            r = client.post(f"/repos/{repo}/check-runs", json={
                "name": CHECK_NAME, "head_sha": sha, "status": "completed",
                "conclusion": "success" if v.verdict == "pass" else "failure",
                "external_id": v.cache_key,
                "output": {
                    "title": f"GEAP AI Gate: {v.verdict.upper()} ({len(v.findings)} finding(s))",
                    "summary": body[:65000], "annotations": annotations(v)},
            })
            r.raise_for_status()
            check_id = r.json().get("id")
        comment_id = None
        if pr_number:
            existing = None
            page = 1
            while existing is None:
                r = client.get(f"/repos/{repo}/issues/{pr_number}/comments", params={"per_page": 100, "page": page})
                r.raise_for_status()
                items = r.json()
                existing = next((c for c in items if COMMENT_MARKER in (c.get("body") or "")), None)
                if len(items) < 100:
                    break
                page += 1
            if existing:
                r = client.patch(f"/repos/{repo}/issues/comments/{existing['id']}", json={"body": body})
            else:
                r = client.post(f"/repos/{repo}/issues/{pr_number}/comments", json={"body": body})
            r.raise_for_status()
            comment_id = r.json().get("id")
        return PublishResult(True, f"published check run {check_id} and PR comment {comment_id}", check_id,
                             comment_id)
    finally:
        if own:
            client.close()
