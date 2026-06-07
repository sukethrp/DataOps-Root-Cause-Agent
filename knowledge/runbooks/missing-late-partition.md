# Runbook: Missing or Late Source Partition

**Applies to:** ingestion tasks (`extract_orders`, etc.) and any model that reads a
date-partitioned source.

## Symptoms

- Airflow task fails or times out during the ingest step.
- Error mentions a **missing partition**, `FileNotFoundError` for a `date=YYYY-MM-DD`
  path, a source **connection timeout**, or zero rows ingested for the latest date.
- `fct_revenue_daily` is **stale** (last successful refresh is from a prior day);
  freshness SLA (04:00 UTC) is at risk or breached.

## Likely causes (ranked)

1. **Upstream daily export landed late or not at all** (most common: the source
   system's nightly job runs long).
2. Source-system connectivity / credential expiry causing a timeout.
3. Partition path convention changed upstream.

## Diagnostics

1. From the Airflow log, identify the **task** and the **target partition date**.
2. Check whether the upstream export for that date has landed (object store /
   source export location).
3. Confirm via `architecture-and-lineage.md` that the stale partition is what feeds
   `fct_revenue_daily` and the dashboard.
4. Distinguish from schema drift: here the column/structure is fine; the **data for
   the date is absent or delayed**, not a column error.

## Remediation

- If the export is merely **late**: wait for it to land, then re-run the ingest task
  and `dbt build --select stg_orders+`.
- If **absent**: trigger the upstream export/backfill for the date, then re-run
  ingestion and the downstream build.
- Communicate SLA risk to Analytics if the 04:00 UTC freshness deadline is at risk.

## Prevention

- Add a **source freshness check** (dbt `source freshness`) that alerts before the
  SLA window, not after.
- Add a sensor in Airflow that waits for the upstream export with a bounded timeout.

**Related:** `source-freshness-sla.md`, `architecture-and-lineage.md`.
