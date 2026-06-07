# Runbook: Source Freshness / SLA Breach

**Applies to:** `fct_revenue_daily` freshness SLA (refresh by 04:00 UTC).

## Symptoms

- `fct_revenue_daily` `max(created_at)` / load timestamp is older than expected.
- Freshness monitor reports the SLA window (04:00 UTC) breached or about to breach.
- Dashboard "Revenue Daily" shows yesterday's data after 04:00 UTC.

## Likely causes (ranked)

1. An **upstream delay** cascaded (late partition — see `missing-late-partition.md`).
2. A **build failure** earlier in the DAG blocked the mart refresh (e.g., schema
   drift — see `schema-drift.md`).
3. Resource contention / long-running build pushed completion past the SLA.

## Diagnostics

1. Determine whether the DAG **failed** (look for an upstream error) or merely **ran
   late** (all green but slow).
2. If failed, branch to the matching runbook (`schema-drift.md` or
   `missing-late-partition.md`) — freshness breach is usually a *symptom*, not the
   root cause.
3. Confirm the impacted SLA and consumers in `architecture-and-lineage.md`.

## Remediation

- Resolve the underlying failure first (schema or partition), then re-run
  `dbt build` and refresh the dashboard.
- Notify Analytics of revised availability.

## Prevention

- Alert on freshness **before** the 04:00 UTC deadline.
- Track DAG runtime trend to catch creeping slowness early.

**Related:** `missing-late-partition.md`, `schema-drift.md`, `architecture-and-lineage.md`.
