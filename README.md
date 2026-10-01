# Customer Profile Service (SVC-CPS)

Customer self-service profile API used by the Customer Mobile App (via the
mobile BFF). Owned by **Team Customer Experience**. Tier 1.

## Layout

```
app/
  main.py              FastAPI app
  config.py            settings (env vars)
  security.py          authentication + authorize_customer_access()
  schemas.py           Pydantic models
  repository.py        profile store (Cloud SQL DS-CPS-PROFILE, in-memory locally)
  routers/customers.py HTTP routes
  validators/address.py address normalisation
  clients/notification.py notification-service client
tests/                 pytest suite
openapi.yaml           API contract
runbook.md             on-call runbook
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/customers/{customer_id}` | Get profile |
| POST | `/customer/update` | Update contact details |
| GET | `/healthz` | Health |

## Run locally

```bash
pip install -r requirements.txt
CPS_ENV=dev uvicorn app.main:app --reload --port 8080
pytest -q
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `CPS_ENV` | `dev` | environment |
| `CDA_URL` | `http://customer-domain-api:8080` | Customer Domain API |
| `NTF_URL` | `http://notification-service:8080` | Notification service |
| `CPS_DATABASE_URL` | see config.py | profile DB |

## GEAP-Managed Repository

This repository is the showcase application for the **GEAP AI-Enabled SDLC Platform** (`SVC-CPS`, showcase ticket `TKT-CPS-118` / `REQ-CPS-007` / `SEC-AUTHZ-01`).

- **Deterministic AI CI Gate ([`.geap/policy.yaml`](.geap/policy.yaml)):** Every pull request runs [`ci.yml`](.github/workflows/ci.yml), which executes `uv run pytest -q --junitxml=junit.xml` followed by `geap-harness gate` and `geap-harness publish`. The Antigravity reviewer proposes structured findings (`FindingList`), and the pure-Python policy engine deterministically decides `pass` or `fail` (caching verdicts under `.geap/cache` keyed by `sha256(diff ∥ model ∥ skill_shas ∥ prompt_hash ∥ policy_hash)`).
- **Continuous Delivery ([`cd.yml`](.github/workflows/cd.yml)):** Pushes to `main` build the container image via Cloud Build (Workload Identity Federation), deploy `cps-staging` on Cloud Run, verify `/healthz`, and pause at the `production` GitHub Environment until an accountable human release manager approves deployment to `cps-prod` from the GEAP Platform UI.
- **Human Authority:** Agents may propose code changes and open pull requests, but never approve PRs, merge PRs, or approve production deployments (`FR-CON-BI-11`, `FR-CON-DD-03`).

