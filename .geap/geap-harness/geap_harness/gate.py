"""Gate orchestration: pinned inputs -> (cached) review -> deterministic policy -> verdict."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .backends import default_model, run_backend
from .cache import Cache, canonical_json, compute_cache_key
from .gitdiff import DiffInfo, compute_diff
from .inputs import DEFAULT_SKILLS, load_skills, prompt_hash, render_prompt
from .models import ReviewResult, Verdict
from .policy import evaluate, load_policy, policy_hash


@dataclass
class GateRun:
    verdict: Verdict
    review: ReviewResult
    diff: DiffInfo
    cache_hit: bool
    replay_ok: bool | None = None
    dropped: list[dict] = field(default_factory=list)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def verdict_json(v: Verdict) -> str:
    return canonical_json(v.model_dump())


def comparable(v: Verdict) -> dict:
    """Verdict minus fields that legitimately differ between identical runs."""
    d = v.model_dump()
    d.pop("created_at", None)
    d.pop("reproducible", None)
    return d


def run_gate(
    *,
    repo_dir: Path,
    base: str,
    head: str = "HEAD",
    policy_path: Path | None = None,
    use_policy: bool = True,
    backend: str = "offline",
    model: str | None = None,
    skills_dir: Path | None = None,
    skills: tuple[str, ...] | list[str] = DEFAULT_SKILLS,
    cache_dir: Path | None = None,
    cache_uri: str | None = None,
    use_cache: bool = True,
    replay: bool = False,
    junit: Path | None = None,
    timeout_s: int = 600,
    now: str | None = None,
) -> GateRun:
    repo_dir = Path(repo_dir).resolve()
    diff = compute_diff(repo_dir, base, head)
    loaded = load_skills(skills_dir, tuple(skills))
    skill_shas = {s.name: s.sha for s in loaded}
    model_id = default_model(backend, model)
    p_hash = prompt_hash()
    policy = load_policy(policy_path) if use_policy else None
    pol_hash = policy_hash(policy)
    key = compute_cache_key(diff.text, model_id, skill_shas, p_hash, pol_hash)
    cache = Cache(cache_dir or (repo_dir / ".geap" / "cache"), cache_uri)
    prompt = render_prompt(diff.text, diff.files, loaded)

    def fresh() -> ReviewResult:
        return run_backend(backend, repo_dir=repo_dir, diff=diff, prompt=prompt, skills=loaded, model=model_id,
                           timeout_s=timeout_s)

    cached = cache.get(key) if use_cache else None
    cache_hit = cached is not None and not replay
    persisted = cached is not None
    if cache_hit:
        review = cached
    else:
        review = fresh()
        if cached is None and use_cache:
            persisted = cache.put(key, review)

    def build(rv: ReviewResult) -> tuple[Verdict, list[dict]]:
        if policy is not None:
            out = evaluate(policy, rv.findings, repo_dir=repo_dir, diff=diff, junit=junit)
            v, f, rules, ev, dropped = out.verdict, out.findings, out.rules, out.evidence_refs, out.dropped
        else:
            f, rules, dropped = rv.findings, [], []
            ev = sorted({r for x in f for r in x.evidence_refs})
            v = "fail" if any(x.severity == "Critical" for x in f) else "pass"
        return Verdict(
            verdict=v, cache_key=key, reproducible=False, model=model_id, skill_shas=dict(sorted(skill_shas.items())),
            prompt_hash=p_hash, policy_hash=pol_hash, findings=f, rules=rules, evidence_refs=ev,
            created_at=now or utc_now(),
        ), dropped

    verdict, dropped = build(review)
    replay_ok: bool | None = None
    if replay:
        # Compare against the pinned (cached) result if one exists, else against an independent second run.
        other = cached if cached is not None else fresh()
        replay_ok = comparable(build(other)[0]) == comparable(verdict)
        if cached is not None:
            verdict, dropped = build(cached)  # the pinned result stays authoritative
        verdict.reproducible = bool(replay_ok and (persisted or not use_cache))
    else:
        verdict.reproducible = bool(persisted or cache_hit or (backend == "offline"))
    return GateRun(verdict=verdict, review=review, diff=diff, cache_hit=cache_hit, replay_ok=replay_ok,
                   dropped=dropped)


def write_verdict(v: Verdict, out: Path) -> None:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(verdict_json(v), encoding="utf-8")


def read_verdict(path: Path) -> Verdict:
    return Verdict.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
