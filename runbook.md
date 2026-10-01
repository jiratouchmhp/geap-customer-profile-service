# Customer Profile Service - On-call Runbook

Service: SVC-CPS | Tier 1 | Region asia-southeast1 | Owner: Team Customer Experience
Pager: `cps-oncall` | Dashboard: `Customer Profile - Golden Signals`

## SLOs
- Availability 99.9 percent (30d), p95 latency 300 ms for GET, 500 ms for updates.

## Alerts

### CPS-5xx-rate-high
1. Check Cloud Run revision health and recent deployments (`gcloud run revisions list`).
2. If a deployment happened in the last 2 hours, compare error rate before/after.
3. Roll back: `gcloud run services update-traffic customer-profile-service --to-revisions=<prev>=100` (requires approval, DSO-PROMO-05).

### CPS-address-sync-failures
Raised when billing/CRM reject address updates relayed via events.
1. Search logs for `address rejected` from billing-adapter.
2. Check whether the address format changed in the latest release (see INC-2041).
3. Mitigation: enable flag `ADDRESS_FORMAT_V1_COMPAT=true` and restart.

### CPS-latency-high
1. Check Customer Domain API latency (dependency).
2. Check DB connections on DS-CPS-PROFILE.

## Dependencies
- Customer Domain API (SVC-CDA) - master data
- Notification Service (SVC-NTF) - profile change notifications
- Address Validation Service (SVC-AVS) - optional, via shared-validation-lib

## Known gaps
- Update endpoint behaviour and failure modes are not documented here yet.
