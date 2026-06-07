# Runbook: Data-Quality Null Spike

**Applies to:** dbt tests and DQ monitors on `stg_*` and `fct_*` columns.

## Symptoms

- A DQ monitor or dbt `not_null` test fires: the **null rate** for a column
  (e.g., `fct_revenue_daily.order_amount`) jumps far above its baseline/threshold.
- The pipeline may still "succeed" structurally: rows load, but values are wrong.
- Revenue totals on the dashboard drop or look implausible.

## Likely causes (ranked)

1. **Upstream source regression**: a source deploy began emitting NULLs for a column
   that was previously populated (most common; see `schema-changelog.md` for
   data-level breaking changes).
2. A join in staging started dropping/!matching keys, producing NULLs after the join.
3. A type cast silently failing to NULL (e.g., bad string → numeric cast).

## Diagnostics

1. Note the **column**, the **observed null rate**, the **threshold**, and the **date**.
2. Check `schema-changelog.md` for a recent **BREAKING (data)** entry on the upstream
   column around that date.
3. Profile the column upstream vs. downstream to locate where NULLs are introduced
   (source vs. a staging join/cast).
4. Confirm blast radius via `architecture-and-lineage.md`.

## Remediation

- **Quarantine**: stop the bad data from reaching the dashboard (fail the build on
  the `not_null`/threshold test rather than publishing).
- Notify the **Source team** (`oltp@shopco.example`) to fix the upstream regression.
- If the issue is a downstream join/cast, fix the model and re-run.

## Prevention

- Enforce `not_null` + `accepted_range` tests on revenue-critical columns.
- Add a freshness + volume + null-rate monitor with alerting upstream of the dashboard.

**Related:** `schema-changelog.md`, postmortem `2026-05-28-orders-null-spike.md`.
