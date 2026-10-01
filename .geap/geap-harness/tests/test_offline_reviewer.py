from __future__ import annotations

from geap_harness.gate import run_gate
from geap_harness.gitdiff import compute_diff
from geap_harness.backends.offline import review

from conftest import FIXED_NOW, apply_authz_fix, commit_all


def test_offline_reviewer_flags_showcase_gap(showcase_repo):
    repo = showcase_repo["repo"]
    diff = compute_diff(repo, showcase_repo["c0"], showcase_repo["c1"])
    rv = review(repo, diff)
    crit = [f for f in rv.findings if f.severity == "Critical"]
    assert [f.rule_id for f in crit] == ["SEC-AUTHZ-01"]
    assert crit[0].control_id == "SEC-AUTHZ-01"
    src = (repo / "app/routers/customers.py").read_text().splitlines()
    path, line = crit[0].evidence_refs[0].rsplit(":", 1)
    assert path == "app/routers/customers.py"
    assert src[int(line) - 1].startswith("def update_customer")
    pii = [f for f in rv.findings if f.rule_id == "LOG-PII-01"]
    assert len(pii) == 1 and pii[0].severity == "Required"
    p, ln = pii[0].evidence_refs[0].rsplit(":", 1)
    assert "print(" in src[int(ln) - 1]
    # get_customer calls authorize_customer_access -> not flagged
    assert all("GET" not in f.message for f in crit)


def test_gate_fails_on_gap(showcase_repo):
    repo = showcase_repo["repo"]
    run = run_gate(repo_dir=repo, base=showcase_repo["c0"], head=showcase_repo["c1"],
                   policy_path=repo / ".geap/policy.yaml", backend="offline", now=FIXED_NOW)
    v = run.verdict
    assert v.verdict == "fail"
    rules = {r.id: r for r in v.rules}
    assert rules["fail_on_severity"].passed is False
    assert "SEC-AUTHZ-01" in rules["fail_on_severity"].detail
    assert rules["required_controls_evidenced:SEC-AUTHZ-01"].passed is False
    assert any(f.rule_id == "SEC-AUTHZ-01" for f in v.findings)


def test_gate_passes_on_patched_copy(showcase_repo):
    repo = showcase_repo["repo"]
    apply_authz_fix(repo)
    c2 = commit_all(repo, "TKT-CPS-118: enforce authorization on POST /customer/update")
    run = run_gate(repo_dir=repo, base=showcase_repo["c1"], head=c2,
                   policy_path=repo / ".geap/policy.yaml", backend="offline", now=FIXED_NOW)
    v = run.verdict
    assert v.verdict == "pass", [r.model_dump() for r in v.rules]
    assert not any(f.severity == "Critical" for f in v.findings)
    rules = {r.id: r for r in v.rules}
    assert rules["required_controls_evidenced:SEC-AUTHZ-01"].passed
    # the remaining print() is reported but does not block (max_findings_required: 3)
    assert any(f.rule_id == "LOG-PII-01" for f in v.findings)
    # no test change in the patch -> advisory test gap
    assert any(f.rule_id == "TEST-GAP-01" and f.severity == "Advisory" for f in v.findings)


def test_patch_with_tests_and_logging_fix_is_clean(showcase_repo):
    repo = showcase_repo["repo"]
    apply_authz_fix(repo)
    p = repo / "app/routers/customers.py"
    p.write_text(p.read_text().replace(
        '    print(f"updating customer {req.customer_id} with {req.model_dump()}")\n', ""))
    t = repo / "tests/test_customers.py"
    t.write_text(t.read_text() + "\n\ndef test_update_other_customer_forbidden(client):\n    pass\n")
    c2 = commit_all(repo, "fix")
    run = run_gate(repo_dir=repo, base=showcase_repo["c1"], head=c2, policy_path=repo / ".geap/policy.yaml",
                   backend="offline", now=FIXED_NOW)
    assert run.verdict.verdict == "pass"
    assert run.verdict.findings == []
