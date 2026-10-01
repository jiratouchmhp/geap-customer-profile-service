"""Deterministic policy engine for ``.geap/policy.yaml`` — the LLM proposes, this code decides.

Supported rules (all optional)::

    version: 1
    rules:
      critic: {require_control_id: true, require_evidence: true}   # filter: drop uncited findings
      known_controls: [SEC-AUTHZ-01, ...]                            # filter: drop unknown control ids
      evidence_must_resolve: changed_files   # changed_files | repo | false  (filter)
      fail_on_severity: [Critical]
      max_findings_required: 3               # fail if more Required findings than this
      max_findings_total: 25
      required_controls_evidenced:
        - control_id: SEC-AUTHZ-01
          pattern: 'authorize_customer_access\\('
          paths: ['app/routers/*.py']
      tests_passed: {required: true, junit_required: false}

Filters always report ``passed: true`` with what they dropped; gating rules
pass/fail. ``verdict = pass`` iff every rule passed. No I/O except reading the
repo at the head commit and the JUnit file; no randomness; no clock.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .gitdiff import DiffInfo, list_files, read_at
from .models import SEVERITY_ORDER, Finding, RuleResult, sort_findings

DEFAULT_POLICY: dict[str, Any] = {
    "version": 1,
    "rules": {
        "critic": {"require_control_id": True, "require_evidence": True},
        "evidence_must_resolve": "changed_files",
        "fail_on_severity": ["Critical"],
    },
}
_REF = re.compile(r"^(?P<path>.+?)(?::(?P<start>\d+)(?:[-:](?P<end>\d+))?)?$")


def load_policy(path: Path | None) -> dict[str, Any]:
    if path is None:
        return json.loads(json.dumps(DEFAULT_POLICY))
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"policy {path} must be a mapping")
    data.setdefault("rules", {})
    return data


def policy_hash(policy: dict[str, Any] | None) -> str:
    """Hash of the *parsed* policy (canonical JSON) — comments/whitespace don't change it."""
    canon = json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canon.encode()).hexdigest()


@dataclass
class ParsedRef:
    path: str
    start: int | None
    end: int | None


def parse_ref(ref: str, repo_dir: Path | None = None) -> ParsedRef | None:
    ref = ref.strip().replace("\\", "/")
    if not ref or "://" in ref:
        return None
    m = _REF.match(ref)
    if not m:
        return None
    path = m.group("path")
    if repo_dir is not None:
        root = str(Path(repo_dir).resolve()).replace("\\", "/") + "/"
        if path.startswith(root):
            path = path[len(root):]
    while path.startswith("./"):
        path = path[2:]
    start = int(m.group("start")) if m.group("start") else None
    end = int(m.group("end")) if m.group("end") else start
    return ParsedRef(path=path, start=start, end=end)


@dataclass
class PolicyOutcome:
    verdict: str
    findings: list[Finding]
    rules: list[RuleResult]
    evidence_refs: list[str]
    dropped: list[dict] = field(default_factory=list)


class _HeadReader:
    def __init__(self, repo_dir: Path, head: str):
        self.repo_dir, self.head = repo_dir, head
        self._cache: dict[str, list[str] | None] = {}

    def lines(self, path: str) -> list[str] | None:
        if path not in self._cache:
            txt = read_at(self.repo_dir, self.head, path)
            self._cache[path] = None if txt is None else txt.splitlines()
        return self._cache[path]


def _resolve_refs(f: Finding, scope: str, diff: DiffInfo, reader: _HeadReader, repo_dir: Path) -> list[str]:
    ok: list[str] = []
    for ref in f.evidence_refs:
        p = parse_ref(ref, repo_dir)
        if p is None:
            continue
        if scope == "changed_files" and p.path not in diff.files:
            continue
        lines = reader.lines(p.path)
        if lines is None:
            continue
        if p.start is not None and not (1 <= p.start <= max(len(lines), 1) and (p.end or p.start) <= max(len(lines), 1)):
            continue
        ok.append(f"{p.path}:{p.start}" if p.start is not None and p.end in (None, p.start)
                  else f"{p.path}:{p.start}-{p.end}" if p.start is not None else p.path)
    return list(dict.fromkeys(ok))


def parse_junit(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    tot = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for s in suites:
        for k in tot:
            tot[k] += int(float(s.get(k, 0) or 0))
    return tot


def evaluate(
    policy: dict[str, Any],
    findings: list[Finding],
    *,
    repo_dir: Path,
    diff: DiffInfo,
    junit: Path | None = None,
) -> PolicyOutcome:
    rules_cfg: dict[str, Any] = dict(policy.get("rules") or {})
    results: list[RuleResult] = []
    dropped: list[dict] = []
    reader = _HeadReader(repo_dir, diff.head)
    current = [f.model_copy(deep=True) for f in findings]

    # ---- filters -----------------------------------------------------------------------------
    critic = rules_cfg.get("critic")
    if critic:
        critic = critic if isinstance(critic, dict) else {}
        need_cid = critic.get("require_control_id", True)
        need_ev = critic.get("require_evidence", True)
        keep = []
        for f in current:
            reasons = []
            if need_cid and not f.control_id:
                reasons.append("missing control_id")
            if need_ev and not f.evidence_refs:
                reasons.append("missing evidence_refs")
            (dropped.append({"finding": f.model_dump(), "reasons": reasons}) if reasons else keep.append(f))
        results.append(RuleResult(id="critic", passed=True,
                                  detail=f"dropped {len(current) - len(keep)} uncited finding(s)"))
        current = keep

    known = rules_cfg.get("known_controls")
    if known:
        known_set = {str(c).upper() for c in known}
        keep = [f for f in current if (f.control_id or "").upper() in known_set]
        for f in current:
            if f not in keep:
                dropped.append({"finding": f.model_dump(), "reasons": [f"unknown control_id {f.control_id}"]})
        results.append(RuleResult(id="known_controls", passed=True,
                                  detail=f"dropped {len(current) - len(keep)} finding(s) citing unknown controls"))
        current = keep

    scope = rules_cfg.get("evidence_must_resolve")
    if scope:
        scope = "changed_files" if scope is True else str(scope)
        if scope not in ("changed_files", "repo"):
            raise ValueError(f"evidence_must_resolve must be changed_files|repo|false, got {scope!r}")
        keep = []
        for f in current:
            refs = _resolve_refs(f, scope, diff, reader, repo_dir)
            if refs:
                f.evidence_refs = refs
                keep.append(f)
            else:
                dropped.append({"finding": f.model_dump(), "reasons": [f"evidence not resolvable in {scope}"]})
        results.append(RuleResult(id="evidence_must_resolve", passed=True,
                                  detail=f"scope={scope}; dropped {len(current) - len(keep)} finding(s) "
                                         "with unresolvable file:line evidence"))
        current = keep

    current = sort_findings(current)
    counts = {s: sum(f.severity == s for f in current) for s in SEVERITY_ORDER}
    extra_refs: list[str] = []

    # ---- gating rules --------------------------------------------------------------------------
    fos = rules_cfg.get("fail_on_severity")
    if fos:
        sev = [str(s).capitalize() for s in (fos if isinstance(fos, list) else [fos])]
        hits = [f for f in current if f.severity in sev]
        ids = sorted({f.control_id or f.rule_id or "?" for f in hits})
        results.append(RuleResult(
            id="fail_on_severity", passed=not hits,
            detail=(f"{len(hits)} finding(s) with severity in {sev}: {', '.join(ids)}" if hits
                    else f"no findings with severity in {sev}")))

    if "max_findings_required" in rules_cfg:
        mx = int(rules_cfg["max_findings_required"])
        results.append(RuleResult(id="max_findings_required", passed=counts["Required"] <= mx,
                                  detail=f"{counts['Required']} Required finding(s) (max {mx})"))

    if "max_findings_total" in rules_cfg:
        mx = int(rules_cfg["max_findings_total"])
        results.append(RuleResult(id="max_findings_total", passed=len(current) <= mx,
                                  detail=f"{len(current)} finding(s) (max {mx})"))

    rce = rules_cfg.get("required_controls_evidenced") or []
    if rce:
        head_files = list_files(repo_dir, diff.head)
        blocking = {(f.control_id or "").upper() for f in current if f.severity in ("Critical", "Required")}
        for spec in rce:
            spec = spec if isinstance(spec, dict) else {"control_id": str(spec)}
            cid = str(spec["control_id"])
            pattern = spec.get("pattern")
            globs = spec.get("paths") or ["**"]
            refs: list[str] = []
            if pattern:
                rx = re.compile(pattern)
                for path in head_files:
                    if not any(fnmatch.fnmatch(path, g) for g in globs):
                        continue
                    for i, line in enumerate(reader.lines(path) or [], start=1):
                        if rx.search(line):
                            refs.append(f"{path}:{i}")
                            break
            evidenced = bool(refs) or not pattern
            ok = evidenced and cid.upper() not in blocking
            why = []
            if not evidenced:
                why.append(f"no match for /{pattern}/ in {globs}")
            if cid.upper() in blocking:
                why.append("a Critical/Required finding cites this control")
            results.append(RuleResult(id=f"required_controls_evidenced:{cid}", passed=ok,
                                      detail=("evidenced at " + ", ".join(refs)) if ok else "; ".join(why)))
            extra_refs += refs

    tp = rules_cfg.get("tests_passed")
    if tp:
        tp = tp if isinstance(tp, dict) else {"required": True}
        if junit is None or not Path(junit).is_file():
            need = bool(tp.get("junit_required", False))
            results.append(RuleResult(id="tests_passed", passed=not need,
                                      detail="no JUnit report provided" + ("" if need else " (skipped)")))
        else:
            t = parse_junit(Path(junit))
            ok = t["tests"] > 0 and t["failures"] == 0 and t["errors"] == 0
            results.append(RuleResult(
                id="tests_passed", passed=ok,
                detail=f"{t['tests']} tests, {t['failures']} failures, {t['errors']} errors, {t['skipped']} skipped"))

    verdict = "pass" if all(r.passed for r in results) else "fail"
    evidence = sorted(set([r for f in current for r in f.evidence_refs] + extra_refs))
    return PolicyOutcome(verdict=verdict, findings=current, rules=results, evidence_refs=evidence, dropped=dropped)
