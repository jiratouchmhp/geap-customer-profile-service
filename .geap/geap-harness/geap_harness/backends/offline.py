"""Deterministic heuristic reviewer (no model). Same inputs -> same findings, always.

Rules (versioned by ``OFFLINE_MODEL``):

* ``SEC-AUTHZ-01`` (Critical): an HTTP route handler in a ``routers/`` module
  that operates on a ``customer_id`` (path param, argument or ``<req>.customer_id``)
  without calling ``authorize_customer_access(...)``.
* ``LOG-PII-01`` (Required, control SEC-PII-05): ``print(...)`` of a request
  payload (``.model_dump()`` / ``.dict()`` / ``.json()`` or a ``req``/``request``/
  ``payload``/``body`` name).
* ``TEST-GAP-01`` (Advisory, control TST-UNIT-01): application code changed but
  no test file changed in the same diff.

Only files changed in the diff are reviewed, read at the head commit.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ..gitdiff import DiffInfo, read_at
from ..models import Finding, ReviewResult, sort_findings

OFFLINE_MODEL = "geap-offline-heuristics-v1"
_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
_PAYLOAD_NAMES = {"req", "request", "payload", "body"}
_DUMP_ATTRS = {"model_dump", "dict", "json", "model_dump_json"}
_AUTHZ_FN = "authorize_customer_access"


def _is_test_path(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return path.startswith("tests/") or "/tests/" in path or name.startswith("test_") or name.endswith("_test.py")


def _route_decorator(dec: ast.expr) -> tuple[str, str] | None:
    """Returns (method, path) for ``@router.<method>("<path>", ...)``."""
    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in _HTTP_METHODS:
        path = ""
        if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
            path = dec.args[0].value
        return dec.func.attr.upper(), path
    return None


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _check_authz(path: str, tree: ast.Module) -> list[Finding]:
    out: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        routes = [r for r in (_route_decorator(d) for d in node.decorator_list) if r]
        if not routes:
            continue
        method, route = routes[0]
        params = {a.arg for a in [*node.args.args, *node.args.kwonlyargs]}
        uses_cid = (
            "customer_id" in params
            or "{customer_id}" in route
            or any(isinstance(n, ast.Attribute) and n.attr == "customer_id" for n in ast.walk(node))
        )
        authorized = any(isinstance(n, ast.Call) and _call_name(n) == _AUTHZ_FN for n in ast.walk(node))
        if uses_cid and not authorized:
            out.append(Finding(
                severity="Critical",
                category="authz",
                control_id="SEC-AUTHZ-01",
                standard_id="STD-SEC",
                rule_id="SEC-AUTHZ-01",
                message=(f"{method} {route or node.name} acts on customer_id without object-level authorization "
                         f"({_AUTHZ_FN}() is never called)."),
                evidence_refs=[f"{path}:{node.lineno}"],
                rationale=("Any authenticated caller can modify another customer's record (IDOR). "
                           f"Call {_AUTHZ_FN}(principal, customer_id) before reading or mutating the record."),
                skill="enterprise-secure-coding",
                agent_id="CI-GATE",
            ))
    return out


def _mentions_payload(expr: ast.AST) -> bool:
    attr_bases = {id(n.value) for n in ast.walk(expr) if isinstance(n, ast.Attribute)}
    for n in ast.walk(expr):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in _DUMP_ATTRS:
            return True
        # bare `req` (e.g. print(req)); `req.customer_id` alone is not treated as a payload dump
        if isinstance(n, ast.Name) and n.id in _PAYLOAD_NAMES and id(n) not in attr_bases:
            return True
    return False


def _check_print_pii(path: str, tree: ast.Module) -> list[Finding]:
    out: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            if any(_mentions_payload(a) for a in [*node.args, *(k.value for k in node.keywords)]):
                out.append(Finding(
                    severity="Required",
                    category="logging",
                    control_id="SEC-PII-05",
                    standard_id="STD-SEC",
                    rule_id="LOG-PII-01",
                    message="print() writes the request payload (PII: email/phone/address) to stdout logs.",
                    evidence_refs=[f"{path}:{node.lineno}"],
                    rationale=("PII must not be written to logs (SEC-PII-05); use the structured logger with "
                               "non-PII fields only (OBS-LOG-01)."),
                    skill="enterprise-secure-coding",
                    agent_id="CI-GATE",
                ))
    return out


def review(repo_dir: Path, diff: DiffInfo, *, model: str = OFFLINE_MODEL) -> ReviewResult:
    findings: list[Finding] = []
    py_changed = [f for f in diff.files if f.endswith(".py")]
    for path in py_changed:
        if _is_test_path(path):
            continue
        src = read_at(repo_dir, diff.head, path)
        if src is None:
            continue
        try:
            tree = ast.parse(src, filename=path)
        except SyntaxError as exc:
            findings.append(Finding(
                severity="Critical", category="build", control_id="COD-BUILD-01", rule_id="PY-SYNTAX-01",
                message=f"Python syntax error: {exc.msg}", evidence_refs=[f"{path}:{exc.lineno or 1}"],
                skill="enterprise-code-review", agent_id="CI-GATE",
            ))
            continue
        if "routers/" in f"/{path}":
            findings += _check_authz(path, tree)
        findings += _check_print_pii(path, tree)

    src_changed = [f for f in py_changed if not _is_test_path(f)]
    tests_changed = [f for f in diff.files if _is_test_path(f)]
    if src_changed and not tests_changed:
        first = src_changed[0]
        line = min(diff.added_lines.get(first) or {1})
        findings.append(Finding(
            severity="Advisory",
            category="test-gap",
            control_id="TST-UNIT-01",
            standard_id="STD-TST",
            rule_id="TEST-GAP-01",
            message=f"{len(src_changed)} application file(s) changed without any test changes.",
            evidence_refs=[f"{first}:{line}"],
            rationale="New or changed behaviour should be covered by unit tests (TST-UNIT-01).",
            skill="enterprise-unit-test",
            agent_id="CI-GATE",
        ))

    findings = sort_findings(findings)
    crit = sum(f.severity == "Critical" for f in findings)
    summary = (f"Offline heuristic review of {len(diff.files)} changed file(s): "
               f"{len(findings)} finding(s), {crit} critical.")
    return ReviewResult(backend="offline", model=model, summary=summary, findings=findings, usage={})
