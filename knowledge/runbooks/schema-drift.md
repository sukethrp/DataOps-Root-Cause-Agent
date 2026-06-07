# Runbook: Upstream Schema Drift

**Applies to:** `stg_orders`, `stg_order_items`, any dbt model selecting columns from `raw.*`.

## Symptoms

- dbt build fails with a database error such as:
  `column "<name>" does not exist` or `Invalid identifier '<NAME>'`.
- Failure appears suddenly with no change to the dbt project itself.
- Downstream marts (`fct_revenue_daily`) are empty or stale; the dashboard shows
  no data for the affected date.

## Likely causes (ranked)

1. **Upstream column renamed or dropped** by the Source team without notice
   (most common — see `schema-changelog.md`).
2. Upstream column **type change** incompatible with a downstream cast.
3. A table or schema was relocated/renamed upstream.

## Diagnostics

1. Note the **exact failure time** from the dbt/Airflow log.
2. Open `schema-changelog.md`; look for a **BREAKING** change to the referenced
   `raw.*` table with a timestamp shortly **before** the failure.
3. Confirm the column named in the error matches the *old* name in the changelog
   entry (e.g., error references `amount`, changelog shows `amount → order_amount`).
4. Check `architecture-and-lineage.md` to confirm which downstream models and
   dashboards are impacted.

## Remediation

- **Fast mitigation:** ask the Source team to temporarily restore the old column
  name (a view alias) to unblock the dashboard.
- **Proper fix:** update the dbt staging model to select the new column name and
  alias it back to the contract name, e.g.
  `select order_amount as amount ...` (or migrate the contract).
- Re-run `dbt build --select stg_orders+` then refresh the dashboard.

## Prevention

- Add a **data contract / source freshness + column test** so the rename is caught
  at ingestion rather than at the mart layer.
- Request the Source team adopt a deprecation window for column renames.

**Related:** `schema-changelog.md`, `architecture-and-lineage.md`,
postmortem `2026-05-21-revenue-dashboard-empty.md`.
