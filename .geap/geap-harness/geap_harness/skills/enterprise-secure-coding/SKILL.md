---
name: enterprise-secure-coding
description: 'Shift-left security analysis in the IDE / pre-commit: secrets, authN/authZ, input validation,
  dependency checks.'
metadata:
  geap.agent_id: CON-DV-05
  geap.authority:
  - R
  - V
  geap.owner: Security
  geap.version: 1.0.0
  geap.retrieval:
  - mode: fts
    source: StandardChunks
    k: 10
    text: SEC-AUTHN-01 SEC-AUTHZ-01 SEC-INPUT-02 SEC-SECRETS-01 SEC-DEP-03 SEC-ERR-04 SEC-PII-05
  - mode: fts
    source: Dependencies
    query_from: diff.imports
    k: 10
---

# enterprise-secure-coding

Owner: **Security** · Agent(s): **CON-DV-05** · Authority: **R/V**

Follow this skill exactly. Findings MUST cite a control ID and at least one evidence reference; findings without both are rejected by the critic (FR-X-09, NFR-05).

## Required context

- Changed code / staged diff.
- Secure coding standard STD-SEC, approved dependency list.
- Deterministic context is pre-assembled by the ContextBroker from the `geap.retrieval` recipe above and passed as input.

## Engineering policies

- Flag secrets and insecure patterns before commit (FR-CON-DV-05).
- Never echo secret values — reference file:line only.

## Review criteria and severity mapping

| Check | Severity | Control / Ref |
|---|---|---|
| Hard-coded secret | Critical | `SEC-SECRETS-01` |
| Missing object-level authorization | Critical | `SEC-AUTHZ-01` |
| Unvalidated input | Required | `SEC-INPUT-02` |
| Non-approved / vulnerable dependency | Required | `SEC-DEP-03` |
| PII in logs | Required | `SEC-PII-05` |

Severity meanings: **Critical** = must fix before merge/release; **Required** = must fix or get a recorded waiver; **Advisory** = recommended.

## Expected output

JSON FindingList {summary, findings[Finding]}.

## Escalation rules

- Escalate to Security Champion on any Critical; waivers are human-only (High risk).

## Permitted agent actions

Recommend / Validate (R/V). Read-only tools.

Actions above this authority are blocked by the GovernancePlugin; High-risk actions require explicit human approval (BRD §11.2).

## Evidence requirements

Recorded automatically in `EvidenceRecords` (BRD §11.3): input artefact IDs/versions, standards applied, recommendation, model/agent/skill version, evidence references, human decision, release/deployment ID.

- file:line evidence for each finding (secret values redacted).

## Authoritative references

- `demo-assets/standards/secure-coding.md`
- `demo-assets/standards/approved-dependencies.yaml`
- `demo-assets/standards/devsecops.md (DSO-SECRETSCAN-03)`
