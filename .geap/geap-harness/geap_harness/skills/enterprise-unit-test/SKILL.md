---
name: enterprise-unit-test
description: Generate unit tests linked to acceptance criteria and requirement IDs (developer workspace).
metadata:
  geap.agent_id: CON-DV-04
  geap.authority:
  - E
  geap.owner: QA
  geap.version: 1.0.0
  geap.retrieval:
  - mode: fts
    source: StandardChunks
    text: TST-UNIT-01 TST-NEG-03 TST-TRACE-07
    k: 6
  - mode: sql
    query: test_inventory
    params:
      repo_id: repo_id
---

# enterprise-unit-test

Owner: **QA** · Agent(s): **CON-DV-04** · Authority: **E**

Follow this skill exactly. Findings MUST cite a control ID and at least one evidence reference; findings without both are rejected by the critic (FR-X-09, NFR-05).

## Required context

- Code under test, acceptance criteria / requirement IDs, existing test inventory.
- Deterministic context is pre-assembled by the ContextBroker from the `geap.retrieval` recipe above and passed as input.

## Engineering policies

- Each test references a requirement/story ID (FR-CON-DV-04, TST-TRACE-07).
- Cover changed behaviour and negative paths (TST-UNIT-01, TST-NEG-03).
- pytest style; deterministic; no network.

## Review criteria and severity mapping

| Check | Severity | Control / Ref |
|---|---|---|
| Test without requirement reference | Required | `TST-TRACE-07` |
| No negative-path test for protected operation | Required | `TST-NEG-03` |

Severity meanings: **Critical** = must fix before merge/release; **Required** = must fix or get a recorded waiver; **Advisory** = recommended.

## Expected output

Python pytest code with `@pytest.mark.req("REQ-…")` markers + coverage notes.

## Escalation rules

- Escalate to QA Lead when acceptance criteria are untestable.

## Permitted agent actions

Execute in developer workspace (E); test PRs via open_test_pr only.

Actions above this authority are blocked by the GovernancePlugin; High-risk actions require explicit human approval (BRD §11.2).

## Evidence requirements

Recorded automatically in `EvidenceRecords` (BRD §11.3): input artefact IDs/versions, standards applied, recommendation, model/agent/skill version, evidence references, human decision, release/deployment ID.

- Requirement IDs covered.

## Authoritative references

- `demo-assets/standards/testing-strategy.md (TST-UNIT-01, TST-NEG-03, TST-TRACE-07)`
