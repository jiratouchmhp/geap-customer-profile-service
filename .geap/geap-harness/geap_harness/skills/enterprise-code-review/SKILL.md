---
name: enterprise-code-review
description: 'Code review against general engineering quality and enterprise standards (pre-commit CON-DV-06
  and PR CON-BI-02): API style, validation, exceptions, logging, secrets, dependencies, telemetry, duplication,
  repo conventions.'
metadata:
  geap.agent_id: CON-DV-06,CON-BI-02
  geap.authority:
  - R
  - V
  geap.owner: Engineering CoE
  geap.version: 1.0.0
  geap.retrieval:
  - mode: sql
    query: pr_details
    params:
      pr_id: pr_id
  - mode: fts
    source: StandardChunks
    k: 12
    text: API-REST-01 API-ERR-03 COD-REUSE-02 COD-EXC-03 COD-CONV-04 OBS-LOG-01 OBS-MET-03 SEC-INPUT-02
  - mode: hybrid
    source: CodeChunks
    query_from: diff.text
    k: 5
---

# enterprise-code-review

Owner: **Engineering CoE** · Agent(s): **CON-DV-06,CON-BI-02** · Authority: **R/V**

Follow this skill exactly. Findings MUST cite a control ID and at least one evidence reference; findings without both are rejected by the critic (FR-X-09, NFR-05).

## Required context

- PR diff / staged change.
- STD-API, STD-COD, STD-OBS chunks.
- Similar code chunks (duplication detection).
- Deterministic context is pre-assembled by the ContextBroker from the `geap.retrieval` recipe above and passed as input.

## Engineering policies

- Detect non-conformant API design, e.g. `POST /customer/update` vs `PATCH /customers/{customerId}` (FR-CON-DV-07, API-REST-01).
- Cover each FR-CON-DV-08 category: input validation, exception handling, structured logging, embedded secrets, non-standard dependencies, telemetry, duplicated utility code, repository conventions.
- One finding per issue; cite control ID and file:line.

## Review criteria and severity mapping

| Check | Severity | Control / Ref |
|---|---|---|
| Non-conformant API design | Required | `API-REST-01` |
| Missing input validation | Required | `SEC-INPUT-02` |
| Incorrect exception handling | Required | `COD-EXC-03` |
| Missing structured logging | Advisory | `OBS-LOG-01` |
| Insufficient telemetry | Advisory | `OBS-MET-03` |
| Duplicated utility code (shared lib exists) | Advisory | `COD-REUSE-02` |
| Repository convention violation | Advisory | `COD-CONV-04` |

Severity meanings: **Critical** = must fix before merge/release; **Required** = must fix or get a recorded waiver; **Advisory** = recommended.

## Expected output

JSON FindingList {summary, findings[Finding]} — skill field = enterprise-code-review.

## Escalation rules

- Escalate to Tech Lead when design-level rework is needed.

## Permitted agent actions

Recommend / Validate (R/V). Read-only tools. Cannot approve or merge PRs.

Actions above this authority are blocked by the GovernancePlugin; High-risk actions require explicit human approval (BRD §11.2).

## Evidence requirements

Recorded automatically in `EvidenceRecords` (BRD §11.3): input artefact IDs/versions, standards applied, recommendation, model/agent/skill version, evidence references, human decision, release/deployment ID.

- file:line per finding.

## Authoritative references

- `demo-assets/standards/api-rest-standard.md`
- `demo-assets/standards/code-quality.md`
- `demo-assets/standards/observability-logging.md`
