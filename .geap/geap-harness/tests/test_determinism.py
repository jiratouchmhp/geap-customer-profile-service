from __future__ import annotations

import hashlib
import json

from geap_harness import gate as gate_mod
from geap_harness.cache import compute_cache_key
from geap_harness.gate import run_gate, verdict_json
from geap_harness.inputs import load_skills, prompt_hash
from geap_harness.models import Finding, ReviewResult

from conftest import FIXED_NOW


def _run(sr, **kw):
    repo = sr["repo"]
    return run_gate(repo_dir=repo, base=sr["c0"], head=sr["c1"], policy_path=repo / ".geap/policy.yaml",
                    backend="offline", **kw)


def test_same_inputs_byte_identical_verdict(showcase_repo, tmp_path):
    a = _run(showcase_repo, now=FIXED_NOW, cache_dir=tmp_path / "c1")
    b = _run(showcase_repo, now=FIXED_NOW, cache_dir=tmp_path / "c2")  # independent cache -> recomputed
    assert not a.cache_hit and not b.cache_hit
    assert verdict_json(a.verdict) == verdict_json(b.verdict)


def test_identical_excluding_created_at(showcase_repo):
    a = _run(showcase_repo, now="2026-01-01T00:00:00Z")
    b = _run(showcase_repo, now="2026-02-02T00:00:00Z")
    ja, jb = json.loads(verdict_json(a.verdict)), json.loads(verdict_json(b.verdict))
    assert ja.pop("created_at") != jb.pop("created_at")
    assert ja == jb


def test_cache_hit_second_run(showcase_repo, monkeypatch):
    first = _run(showcase_repo, now=FIXED_NOW)
    assert not first.cache_hit
    cache_file = showcase_repo["repo"] / ".geap/cache" / f"{first.verdict.cache_key}.json"
    assert cache_file.is_file()

    def boom(*a, **k):
        raise AssertionError("backend must not run on a cache hit")

    monkeypatch.setattr(gate_mod, "run_backend", boom)
    second = _run(showcase_repo, now=FIXED_NOW)
    assert second.cache_hit
    assert second.verdict.reproducible
    assert verdict_json(second.verdict) == verdict_json(first.verdict)


def test_cached_llm_result_is_pinned(showcase_repo, monkeypatch):
    """A (simulated) non-deterministic backend: the cache pins the first answer."""
    calls = {"n": 0}

    def flaky(backend, **kw):
        calls["n"] += 1
        sev = "Critical" if calls["n"] == 1 else "Advisory"
        return ReviewResult(backend="sdk", model="m", findings=[Finding(
            severity=sev, category="authz", message="x", control_id="SEC-AUTHZ-01",
            evidence_refs=["app/routers/customers.py:27"])])

    monkeypatch.setattr(gate_mod, "run_backend", flaky)
    a = _run(showcase_repo, now=FIXED_NOW)
    b = _run(showcase_repo, now=FIXED_NOW)
    assert calls["n"] == 1 and b.cache_hit
    assert a.verdict.verdict == b.verdict.verdict == "fail"
    # --replay recomputes: the flaky second answer differs -> not reproducible, pinned verdict kept
    c = _run(showcase_repo, now=FIXED_NOW, replay=True)
    assert c.replay_ok is False and c.verdict.reproducible is False
    assert c.verdict.verdict == "fail"


def test_replay_offline_is_reproducible(showcase_repo):
    _run(showcase_repo, now=FIXED_NOW)
    r = _run(showcase_repo, now=FIXED_NOW, replay=True)
    assert r.replay_ok is True and r.verdict.reproducible is True


def test_cache_key_formula_and_sensitivity(showcase_repo, tmp_path):
    v = _run(showcase_repo, now=FIXED_NOW).verdict
    from geap_harness.gitdiff import compute_diff

    diff = compute_diff(showcase_repo["repo"], showcase_repo["c0"], showcase_repo["c1"])
    shas = {s.name: s.sha for s in load_skills()}
    assert v.skill_shas == dict(sorted(shas.items()))
    assert v.prompt_hash == prompt_hash()
    assert v.cache_key == compute_cache_key(diff.text, v.model, shas, v.prompt_hash, v.policy_hash)
    manual = hashlib.sha256()
    for part in (diff.text, v.model, ",".join(sorted(shas.values())), v.prompt_hash, v.policy_hash):
        manual.update(part.encode() + b"\x1f")
    assert manual.hexdigest() == v.cache_key

    # policy change -> new policy hash -> new cache key
    pol = tmp_path / "policy.yaml"
    pol.write_text((showcase_repo["repo"] / ".geap/policy.yaml").read_text().replace(
        "max_findings_required: 3", "max_findings_required: 0"))
    v2 = run_gate(repo_dir=showcase_repo["repo"], base=showcase_repo["c0"], head=showcase_repo["c1"],
                  policy_path=pol, backend="offline", now=FIXED_NOW).verdict
    assert v2.policy_hash != v.policy_hash and v2.cache_key != v.cache_key


def test_verdict_has_contract_fields(showcase_repo):
    d = json.loads(verdict_json(_run(showcase_repo, now=FIXED_NOW).verdict))
    assert set(d) == {"verdict", "cache_key", "reproducible", "model", "skill_shas", "prompt_hash", "policy_hash",
                      "findings", "rules", "evidence_refs", "created_at"}
    assert set(d["skill_shas"]) == {"enterprise-code-review", "enterprise-secure-coding", "enterprise-unit-test"}
    for r in d["rules"]:
        assert set(r) == {"id", "passed", "detail"}
