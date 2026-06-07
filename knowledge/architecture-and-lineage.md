# Pipeline Architecture & Lineage — ShopCo Revenue Analytics

> This document describes the `revenue_daily` data pipeline. It is the primary
> lineage reference for the DataOps Root-Cause Agent. The agent grounds on this
> file to map a failing object back to its upstream dependencies and owners.

## Platform

- **Warehouse / lakehouse:** Delta tables on a lakehouse. (Implementation is
  portable across Snowflake and Microsoft Fabric — schema and lineage below are
  the same in both.)
- **Transformation:** dbt (project `shopco_analytics`).
- **Orchestration:** Apache Airflow, DAG `revenue_daily`.
- **Ingestion:** managed connector from the production OLTP database into `raw.*`.
- **Consumption:** Power BI dashboard **"Revenue Daily"**.

## Schedule (all times UTC)

| Step | Object | Time | Owner |
|------|--------|------|-------|
| 1. Ingest | `raw.orders`, `raw.order_items`, `raw.customers` | 02:00 | OLTP / Source team |
| 2. dbt build (staging) | `stg_orders`, `stg_order_items` | 02:10 | Data Engineering |
| 3. dbt build (marts) | `fct_revenue_daily`, `dim_customer` | 02:20 | Data Engineering |
| 4. DQ tests | dbt tests on all models | 02:35 | Data Engineering |
| 5. Dashboard refresh | "Revenue Daily" (Power BI) | 03:00 | Analytics |

**Freshness SLA:** `fct_revenue_daily` must be successfully refreshed by **04:00 UTC** daily.

## Lineage (dependency graph)

```
raw.orders ───────────┐
                       ├──► stg_orders ──────────┐
raw.order_items ──┐    │                          ├──► fct_revenue_daily ──► "Revenue Daily" dashboard
                  ├────┴──► stg_order_items ──────┘
raw.customers ────┴───────► dim_customer
```

## Object reference

| Object | Type | Depends on | Notes |
|--------|------|-----------|-------|
| `raw.orders` | Source table | OLTP `orders` | Columns: `order_id`, `customer_id`, `order_amount`, `currency`, `created_at`, `status`. **Owned by the Source team; schema changes are NOT coordinated with Data Engineering.** |
| `raw.order_items` | Source table | OLTP `order_items` | Line items per order. |
| `raw.customers` | Source table | OLTP `customers` | Customer dimension source. |
| `stg_orders` | dbt staging model | `raw.orders` | Renames/casts order columns. Selects `order_amount`. |
| `stg_order_items` | dbt staging model | `raw.order_items` | One row per line item. |
| `fct_revenue_daily` | dbt mart (fact) | `stg_orders`, `stg_order_items` | Daily revenue grain. Feeds the dashboard. |
| `dim_customer` | dbt mart (dim) | `raw.customers` | Customer attributes. |

## Ownership & contacts

- **Data Engineering** (owns `stg_*`, `fct_*`, `dim_*`, Airflow DAG): `data-eng@shopco.example`
- **Source / OLTP team** (owns `raw.*` and the upstream schema): `oltp@shopco.example`
- **Analytics** (owns the dashboard): `analytics@shopco.example`

## Known fragility

- The Source team ships schema changes to the OLTP database **without notifying
  Data Engineering**. Column renames and type changes upstream are the single
  most common cause of `stg_*` build failures. See runbook: `schema-drift.md`.
- Upstream daily exports occasionally land late, causing missing date partitions.
  See runbook: `missing-late-partition.md`.
