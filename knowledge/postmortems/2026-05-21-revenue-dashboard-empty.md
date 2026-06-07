# Postmortem: Revenue Dashboard Empty (2026-05-21)

- **Date:** 2026-05-21
- **Severity:** SEV-2 (revenue dashboard unavailable ~3 hours)
- **Affected:** `stg_orders` → `fct_revenue_daily` → "Revenue Daily" dashboard

## Summary

At 02:11 UTC the `revenue_daily` dbt build failed with
`column "total" does not exist`. The "Revenue Daily" dashboard showed no data for
the day. The freshness SLA (04:00 UTC) was breached.

## Root cause

The Source team renamed `raw.orders.total` to `amount` at **02:09 UTC** (see
`schema-changelog.md`) without notifying Data Engineering. The dbt staging model
`stg_orders` still selected `total`, so the build failed.

## Resolution

Updated `stg_orders` to select `amount` (aliased to the contract name) and re-ran
`dbt build --select stg_orders+`. Dashboard recovered by 05:14 UTC.

## Lessons / follow-ups

- Schema renames upstream remain the top cause of staging failures.
- Action item (still open): add a source column contract test to catch renames at
  ingestion. The same class of failure can recur on any `raw.orders` column rename.

**Related:** `runbooks/schema-drift.md`, `schema-changelog.md`.
