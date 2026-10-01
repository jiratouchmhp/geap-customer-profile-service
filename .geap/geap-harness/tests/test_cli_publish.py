from __future__ import annotations

import json

import httpx
from typer.testing import CliRunner

from geap_harness.cli import app
from geap_harness.gate import read_verdict
from geap_harness.publish import COMMENT_MARKER, publish, render_markdown

from conftest import apply_authz_fix, commit_all

runner = CliRunner()


def test_cli_gate_fail_writes_verdict(showcase_repo, tmp_path, monkeypatch):
    monkeypatch.setenv("GEAP_GATE_NOW", "2026-09-30T00:00:00Z")
    repo, out = showcase_repo["repo"], tmp_path / "gate.json"
    res = runner.invoke(app, ["gate", "--repo-dir", str(repo), "--base", showcase_repo["c0"], "--head",
                              showcase_repo["c1"], "--out", str(out), "--backend", "offline"])
    assert res.exit_code == 1, res.output
    assert "GEAP AI Gate: FAIL" in res.output
    v = json.loads(out.read_text())
    assert v["verdict"] == "fail" and v["created_at"] == "2026-09-30T00:00:00Z"
    # policy auto-discovered from <repo>/.geap/policy.yaml
    assert any(r["id"] == "fail_on_severity" for r in v["rules"])

    res2 = runner.invoke(app, ["gate", "--repo-dir", str(repo), "--base", showcase_repo["c0"], "--head",
                               showcase_repo["c1"], "--out", str(out), "--exit-zero", "--replay"])
    assert res2.exit_code == 0, res2.output
    assert "cache=miss" in res2.output  # replay always recomputes


def test_cli_gate_pass_with_junit(showcase_repo, tmp_path):
    repo = showcase_repo["repo"]
    apply_authz_fix(repo)
    c2 = commit_all(repo, "fix")
    junit = tmp_path / "junit.xml"
    junit.write_text('<testsuite tests="7" failures="0" errors="0"/>')
    out = tmp_path / "gate.json"
    res = runner.invoke(app, ["gate", "--repo-dir", str(repo), "--base", showcase_repo["c1"], "--head", c2,
                              "--policy", str(repo / ".geap/policy.yaml"), "--out", str(out), "--junit", str(junit)])
    assert res.exit_code == 0, res.output
    v = read_verdict(out)
    assert v.verdict == "pass"
    assert {r.id: r for r in v.rules}["tests_passed"].detail.startswith("7 tests")


def test_cli_review_outputs_findings(showcase_repo):
    res = runner.invoke(app, ["review", "--repo-dir", str(showcase_repo["repo"]), "--base", showcase_repo["c0"],
                              "--head", showcase_repo["c1"], "--no-cache"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)
    assert {f["rule_id"] for f in data["findings"]} >= {"SEC-AUTHZ-01", "LOG-PII-01"}


def test_cli_bad_backend_and_bad_rev(showcase_repo):
    r = runner.invoke(app, ["gate", "--repo-dir", str(showcase_repo["repo"]), "--base", "c0", "--backend", "gpt"])
    assert r.exit_code == 2
    r = runner.invoke(app, ["gate", "--repo-dir", str(showcase_repo["repo"]), "--base", "does-not-exist"])
    assert r.exit_code == 2 and "error" in r.output


def test_publish_noop_outside_actions(showcase_repo, tmp_path, monkeypatch):
    for k in ("GITHUB_ACTIONS", "GITHUB_TOKEN", "GITHUB_REPOSITORY"):
        monkeypatch.delenv(k, raising=False)
    out = tmp_path / "gate.json"
    runner.invoke(app, ["gate", "--repo-dir", str(showcase_repo["repo"]), "--base", showcase_repo["c0"],
                        "--head", showcase_repo["c1"], "--out", str(out), "--exit-zero"])
    res = runner.invoke(app, ["publish", "--gate", str(out)])
    assert res.exit_code == 0 and "skipping publish" in res.output


def test_publish_check_run_and_comment_upsert(showcase_repo, tmp_path):
    out = tmp_path / "gate.json"
    runner.invoke(app, ["gate", "--repo-dir", str(showcase_repo["repo"]), "--base", showcase_repo["c0"],
                        "--head", showcase_repo["c1"], "--out", str(out), "--exit-zero"])
    v = read_verdict(out)
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 7, "head": {"sha": "abc123"}}}))
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path, json.loads(req.content) if req.content else None))
        if req.method == "POST" and req.url.path.endswith("/check-runs"):
            return httpx.Response(201, json={"id": 11})
        if req.method == "GET":
            return httpx.Response(200, json=[{"id": 5, "body": "hello"}, {"id": 99, "body": f"{COMMENT_MARKER} old"}])
        if req.method == "PATCH":
            return httpx.Response(200, json={"id": 99})
        return httpx.Response(404)

    client = httpx.Client(base_url="https://api.github.test", transport=httpx.MockTransport(handler))
    env = {"GITHUB_ACTIONS": "true", "GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r",
           "GITHUB_EVENT_PATH": str(event), "GITHUB_RUN_ID": "42"}
    res = publish(v, client=client, env=env)
    assert res.published and res.check_run_id == 11 and res.comment_id == 99
    method, path, body = calls[0]
    assert (method, path) == ("POST", "/repos/o/r/check-runs")
    assert body["name"] == "GEAP AI Gate" and body["head_sha"] == "abc123" and body["conclusion"] == "failure"
    anns = body["output"]["annotations"]
    assert any(a["annotation_level"] == "failure" and a["path"] == "app/routers/customers.py" for a in anns)
    assert calls[-1][0] == "PATCH" and calls[-1][1] == "/repos/o/r/issues/comments/99"  # upsert, not a new comment
    assert render_markdown(v).startswith(COMMENT_MARKER)
