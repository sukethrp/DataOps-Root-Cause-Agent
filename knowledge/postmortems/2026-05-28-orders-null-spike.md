# Postmortem: Order Amount Null Spike (2026-05-28)

- **Date:** 2026-05-28
- **Severity:** SEV-2 (revenue understated on dashboard)
- **Affected:** `raw.orders.order_amount` → `fct_revenue_daily` → "Revenue Daily"

## Summary

The 02:35 UTC DQ tests flagged a null-rate spike: `fct_revenue_daily.order_amount`
was ~34% NULL versus a <1% baseline. The pipeline ran "green" structurally, but
reported daily revenue was implausibly low.

## Root cause

A source deploy at **01:50 UTC** (see `schema-changelog.md`, BREAKING (data) entry)
caused the OLTP system to emit NULL `order_amount` for roughly a third of new orders.
The column still existed, so no structural error occurred — only the values were bad.

## Resolution

Failed the build on the `not_null` threshold to quarantine the bad data (prevented
publishing to the dashboard), notified the Source team, and re-ran after the upstream
fix landed.

## Lessons / follow-ups

- Structural success != data correctness. Value-level regressions need DQ thresholds,
  not just `not_null` pass/fail.
- Added `accepted_range` + null-rate monitor on revenue columns.

**Related:** `runbooks/data-quality-null-spike.md`, `schema-changelog.md`.
