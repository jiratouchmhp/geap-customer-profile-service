from __future__ import annotations

from pathlib import Path

from geap_harness.gitdiff import compute_diff
from geap_harness.models import Finding
from geap_harness.policy import evaluate, load_policy, parse_ref, policy_hash

from conftest import apply_authz_fix, commit_all


def F(sev="Critical", cid="SEC-AUTHZ-01", refs=("app/routers/customers.py:27",), **kw):
    return Finding(severity=sev, category="c", message=kw.pop("message", "m"), control_id=cid,
                   evidence_refs=list(refs), **kw)


def _ctx(sr, head="c1"):
    return sr["repo"], compute_diff(sr["repo"], sr["c0"], sr[head])


def test_parse_ref_variants(tmp_path):
    assert parse_ref("a/b.py:12").start == 12
    r = parse_ref("./a/b.py:3-7")
    assert (r.path, r.start, r.end) == ("a/b.py", 3, 7)
    assert parse_ref("a/b.py").start is None
    assert parse_ref(f"{tmp_path.resolve()}/x.py:2", tmp_path).path == "x.py"
    assert parse_ref("https://example.com/x") is None


def test_evidence_resolution_drops_unresolvable(showcase_repo):
    repo, diff = _ctx(showcase_repo)
    findings = [
        F(refs=["app/routers/customers.py:27"]),                  # ok
        F(cid="SEC-PII-05", sev="Required", refs=["app/nope.py:1"]),  # file missing
        F(cid="OBS-LOG-01", sev="Required", refs=["app/main.py:9999"]),  # line out of range
        F(cid="TST-UNIT-01", sev="Advisory", refs=["./app/main.py:3", "bogus.py:1"]),  # partially ok
    ]
    out = evaluate({"rules": {"evidence_must_resolve": "changed_files"}}, findings, repo_dir=repo, diff=diff)
    assert [f.control_id for f in out.findings] == ["SEC-AUTHZ-01", "TST-UNIT-01"]
    assert out.findings[1].evidence_refs == ["app/main.py:3"]
    assert len(out.dropped) == 2
    assert out.rules[0].id == "evidence_must_resolve" and out.rules[0].passed


def test_evidence_scope_changed_files_vs_repo(showcase_repo):
    repo = showcase_repo["repo"]
    apply_authz_fix(repo)
    c2 = commit_all(repo, "fix")
    diff = compute_diff(repo, showcase_repo["c1"], c2)
    f = [F(sev="Advisory", cid="OBS-LOG-01", refs=["app/main.py:3"])]  # exists, but not changed in this diff
    assert evaluate({"rules": {"evidence_must_resolve": "changed_files"}}, f, repo_dir=repo, diff=diff).findings == []
    assert len(evaluate({"rules": {"evidence_must_resolve": "repo"}}, f, repo_dir=repo, diff=diff).findings) == 1


def test_critic_and_known_controls(showcase_repo):
    repo, diff = _ctx(showcase_repo)
    findings = [F(), F(cid=None), F(refs=()), F(cid="MADE-UP-99")]
    pol = {"rules": {"critic": True, "known_controls": ["SEC-AUTHZ-01"]}}
    out = evaluate(pol, findings, repo_dir=repo, diff=diff)
    assert [f.control_id for f in out.findings] == ["SEC-AUTHZ-01"]
    assert {r.id for r in out.rules} == {"critic", "known_controls"}
    assert out.verdict == "pass"


def test_fail_on_severity_and_max_required(showcase_repo):
    repo, diff = _ctx(showcase_repo)
    req = [F(sev="Required", cid=f"C-{i}") for i in range(3)]
    pol = {"rules": {"fail_on_severity": ["Critical"], "max_findings_required": 2}}
    out = evaluate(pol, req, repo_dir=repo, diff=diff)
    r = {x.id: x for x in out.rules}
    assert r["fail_on_severity"].passed and not r["max_findings_required"].passed
    assert out.verdict == "fail"
    out2 = evaluate(pol, [F()], repo_dir=repo, diff=diff)
    assert out2.verdict == "fail" and not {x.id: x for x in out2.rules}["fail_on_severity"].passed
    assert evaluate(pol, [], repo_dir=repo, diff=diff).verdict == "pass"


def test_required_controls_evidenced(showcase_repo):
    repo, diff = _ctx(showcase_repo)
    spec = {"control_id": "SEC-AUTHZ-01", "pattern": r"authorize_customer_access\(", "paths": ["app/routers/*.py"]}
    out = evaluate({"rules": {"required_controls_evidenced": [spec]}}, [], repo_dir=repo, diff=diff)
    assert out.verdict == "pass"
    assert any(e.startswith("app/routers/customers.py:") for e in out.evidence_refs)
    missing = dict(spec, pattern=r"definitely_not_here\(")
    assert evaluate({"rules": {"required_controls_evidenced": [missing]}}, [], repo_dir=repo,
                    diff=diff).verdict == "fail"
    blocked = evaluate({"rules": {"required_controls_evidenced": [spec]}}, [F()], repo_dir=repo, diff=diff)
    assert blocked.verdict == "fail" and "cites this control" in blocked.rules[0].detail


def test_tests_passed_junit(showcase_repo, tmp_path: Path):
    repo, diff = _ctx(showcase_repo)
    ok = tmp_path / "ok.xml"
    ok.write_text('<testsuites><testsuite name="p" tests="5" failures="0" errors="0" skipped="1"/></testsuites>')
    bad = tmp_path / "bad.xml"
    bad.write_text('<testsuite name="p" tests="5" failures="1" errors="0"/>')
    pol = {"rules": {"tests_passed": {"required": True, "junit_required": True}}}
    assert evaluate(pol, [], repo_dir=repo, diff=diff, junit=ok).verdict == "pass"
    assert evaluate(pol, [], repo_dir=repo, diff=diff, junit=bad).verdict == "fail"
    assert evaluate(pol, [], repo_dir=repo, diff=diff).verdict == "fail"  # junit required but missing
    lax = {"rules": {"tests_passed": {"required": True, "junit_required": False}}}
    out = evaluate(lax, [], repo_dir=repo, diff=diff)
    assert out.verdict == "pass" and "skipped" in out.rules[0].detail


def test_policy_hash_ignores_formatting(tmp_path):
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text("version: 1\nrules:\n  fail_on_severity: [Critical]\n")
    b.write_text("# comment\nrules:\n    fail_on_severity:\n      - Critical\nversion: 1\n")
    assert policy_hash(load_policy(a)) == policy_hash(load_policy(b))
    assert policy_hash(load_policy(None)) != policy_hash(load_policy(a))
