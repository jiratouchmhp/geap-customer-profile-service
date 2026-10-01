# `geap-harness` — Deterministic AI CI Gate

Standalone, CI-installable Python package implementing the **GEAP Deterministic AI Gate** ([`docs/PLATFORM_CONTRACTS.md` §6](../docs/PLATFORM_CONTRACTS.md)).

> **Design rule (ADR-009):** The reviewer backend (Antigravity SDK, `agy` CLI, or deterministic offline heuristics) *proposes* structured findings (`FindingList`). Pure-Python policy code evaluates `.geap/policy.yaml` against the repository at `--head` and *decides* `pass` or `fail`. Merge and production deployment remain human decisions.

---

## Quick Start

```bash
cd geap-harness
uv sync --group dev
uv run pytest -q
```

Run a gate check against a repository range:

```bash
uv run geap-harness gate \
  --repo-dir ../showcase-app \
  --base HEAD~1 \
  --head HEAD \
  --policy ../showcase-app/.geap/policy.yaml \
  --backend offline \
  --out gate.json
```

Install with the Google Antigravity SDK backend (`sdk`):

```bash
uv sync --extra sdk
```

---

## CLI Commands

### `geap-harness gate`

Reviews `base..head`, filters hallucinations via deterministic critics, evaluates `.geap/policy.yaml`, and writes a canonical verdict JSON file.

```bash
geap-harness gate \
  --repo-dir . \
  --base <base_sha> \
  --head <head_sha> \
  [--policy .geap/policy.yaml] \
  [--out gate.json] \
  [--backend offline|sdk|cli] \
  [--model <pinned_model_id>] \
  [--junit junit.xml] \
  [--cache-dir .geap/cache] \
  [--cache-uri gs://bucket/prefix] \
  [--no-cache] \
  [--replay] \
  [--exit-zero]
```

**Exit codes:**
| Code | Meaning |
|---|---|
| `0` | Verdict is `pass` (or `--exit-zero` was supplied after computing a verdict) |
| `1` | Verdict is `fail` |
| `2` | Execution / configuration / git error |
| `3` | `--replay` detected a non-reproducible verdict |

### `geap-harness review`

Runs the reviewer backend only (without policy evaluation) and outputs canonical JSON containing `summary`, `findings`, `backend`, `model`, `cache_key`, `skill_shas`, `prompt_hash`, and `usage`.

```bash
geap-harness review \
  --repo-dir . \
  --base <base_sha> \
  --head <head_sha> \
  [--backend offline|sdk|cli] \
  [--out review.json]
```

### `geap-harness publish`

Publishes a verdict JSON produced by `gate` to GitHub when running inside GitHub Actions (`GITHUB_ACTIONS=true`):
1. Creates a check run named **`GEAP AI Gate`** on the PR head SHA with file/line annotations (up to 50) mapped from `evidence_refs`.
2. Upserts a single PR comment marked with `<!-- geap-ai-gate -->` containing the rule table, findings, and collapsible determinism record.

Outside GitHub Actions (or when `GITHUB_TOKEN` / `GITHUB_REPOSITORY` are unset), `publish` is a safe no-op that exits `0`.

```bash
geap-harness publish --gate gate.json [--sha <head_sha>] [--pr <number>]
```

### `geap-harness show` & `geap-harness version`

- `geap-harness show --gate gate.json` — pretty-prints a verdict file in canonical JSON order.
- `geap-harness version` — prints the package version.

---

## Determinism & Cache Key

To prevent flaky LLM checks from blocking CI or producing different results on re-runs, `geap-harness` pins every input to the review and caches the resulting `ReviewResult`:

1. **Pinned inputs:**
   - **Diff (`diff.text`):** Normalized git diff (`git diff --no-color --no-ext-diff --unified=3 <base>..<head>`).
   - **Model (`model`):** Explicit model ID (`--model` or `$GEAP_HARNESS_REVIEW_MODEL`, e.g. `gemini-2.5-pro`; `offline-rules-v1` for the offline backend).
   - **Skills (`skill_shas`):** Content-addressed SHA-256 over relative file paths and LF-normalized bytes of every file in each active skill (`enterprise-code-review`, `enterprise-secure-coding`, `enterprise-unit-test`).
   - **Prompt (`prompt_hash`):** SHA-256 of the versioned prompt template (`review-v1.md`).
   - **Policy (`policy_hash`):** SHA-256 of the canonical JSON serialization of the parsed `.geap/policy.yaml` (whitespace and comment changes do not invalidate the cache; rule changes do).

2. **Cache key formula (`geap_harness/cache.py`):**
   ```text
   cache_key = sha256(
     diff_text        || 0x1f ||
     model            || 0x1f ||
     sorted_skill_shas|| 0x1f ||
     prompt_hash      || 0x1f ||
     policy_hash      || 0x1f
   )
   ```
   where `sorted_skill_shas` is `",".join(sorted(skill_shas.values()))`.

3. **Two-tier cache & `--replay`:**
   - Reviews are cached locally at `<repo-dir>/.geap/cache/<cache_key>.json` and optionally mirrored to GCS via `--cache-uri gs://...` (`$GEAP_GATE_CACHE_URI`).
   - Passing `--replay` forces a fresh comparison against the cached result (or a second independent run when uncached) and asserts that `comparable(verdict)` is identical; otherwise `geap-harness gate` exits with code `3`.

---

## Policy Engine (`.geap/policy.yaml`)

```yaml
version: 1
service: SVC-CPS
rules:
  # Filters (drop untrusted findings; always report passed=true with drop counts)
  critic:
    require_control_id: true
    require_evidence: true
  known_controls: [SEC-AUTHZ-01, LOG-PII-01, API-REST-01, TST-NEG-03, DOC-API-01]
  evidence_must_resolve: changed_files   # changed_files | repo | false

  # Gating rules (all must pass for verdict == "pass")
  fail_on_severity: [Critical]
  max_findings_required: 3
  max_findings_total: 25
  required_controls_evidenced:
    - control_id: SEC-AUTHZ-01
      pattern: 'authorize_customer_access\('
      paths: ['app/routers/*.py']
  tests_passed:
    required: true
    junit_required: false
```

---

## Verdict JSON Schema (`gate.json`)

```json
{
  "cache_key": "<64-char sha256>",
  "created_at": "2026-09-30T15:00:00Z",
  "evidence_refs": ["app/routers/customers.py:16"],
  "findings": [],
  "model": "offline-rules-v1",
  "policy_hash": "<64-char sha256>",
  "prompt_hash": "<64-char sha256>",
  "reproducible": true,
  "rules": [
    {"detail": "dropped 0 uncited finding(s)", "id": "critic", "passed": true}
  ],
  "skill_shas": {
    "enterprise-code-review": "<sha256>",
    "enterprise-secure-coding": "<sha256>",
    "enterprise-unit-test": "<sha256>"
  },
  "verdict": "pass"
}
```
