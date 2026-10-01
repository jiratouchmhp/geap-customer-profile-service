"""Schemas for the deterministic gate (PLATFORM_CONTRACTS.md §6).

``Finding`` / ``FindingList`` are wire-compatible with
``geap_sdlc.schemas.Finding`` / ``FindingList`` (same field names and
severity vocabulary) plus an optional ``rule_id`` for the heuristic rule that
produced the finding. geap-harness deliberately does not import geap-sdlc so it
stays a small, CI-installable package.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["Critical", "Required", "Advisory"]
SEVERITY_ORDER: dict[str, int] = {"Critical": 0, "Required": 1, "Advisory": 2}


class Finding(BaseModel):
    """A single reviewer finding. Must cite a control and file:line evidence."""

    severity: Severity
    category: str = Field(description="Review category, e.g. authz, logging, test-gap.")
    message: str
    control_id: str | None = Field(default=None, description="Enterprise control ID, e.g. SEC-AUTHZ-01.")
    standard_id: str | None = Field(default=None, description="Enterprise standard ID, e.g. STD-SEC.")
    evidence_refs: list[str] = Field(default_factory=list, description="Evidence refs as 'path:line' (repo-relative).")
    rationale: str = ""
    skill: str | None = None
    agent_id: str | None = None
    rule_id: str | None = Field(default=None, description="Heuristic/LLM rule id, e.g. SEC-AUTHZ-01, LOG-PII-01.")


class FindingList(BaseModel):
    """Structured reviewer output (``response_schema`` for the SDK / ``--json-schema`` for agy)."""

    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)


class RuleResult(BaseModel):
    id: str
    passed: bool
    detail: str = ""


class ReviewResult(BaseModel):
    """What a backend returns (before policy). This is what gets cached."""

    backend: str
    model: str
    summary: str = ""
    findings: list[Finding] = Field(default_factory=list)
    usage: dict = Field(default_factory=dict)


class Verdict(BaseModel):
    """Gate verdict JSON — field set fixed by PLATFORM_CONTRACTS.md §6."""

    verdict: Literal["pass", "fail"]
    cache_key: str
    reproducible: bool
    model: str
    skill_shas: dict[str, str]
    prompt_hash: str
    policy_hash: str
    findings: list[Finding]
    rules: list[RuleResult]
    evidence_refs: list[str]
    created_at: str


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Canonical order so identical inputs always serialise identically."""
    return sorted(
        findings,
        key=lambda f: (
            SEVERITY_ORDER.get(f.severity, 9),
            f.control_id or "~",
            f.rule_id or "~",
            f.evidence_refs[0] if f.evidence_refs else "~",
            f.message,
        ),
    )
