# Upstream Schema Changelog: `raw.*`

> Chronological log of schema changes to source tables. The agent grounds on
> this file to correlate a failure timestamp with a recent breaking change.
> Times are UTC. Entries marked **BREAKING** are not backward-compatible.

| Date / time | Object | Change | Type | Notified DE? |
|-------------|--------|--------|------|--------------|
| 2026-06-10 02:14 | `raw.orders` | Column `amount` renamed to `order_amount` | **BREAKING** | No |
| 2026-06-09 14:02 | `raw.customers` | Added nullable column `loyalty_tier` | Additive (safe) | No |
| 2026-06-07 09:30 | `raw.order_items` | Column `qty` widened `INT → BIGINT` | Compatible | No |
| 2026-05-28 01:50 | `raw.orders` | Source deploy: `order_amount` began emitting NULLs for ~34% of rows (regression) | **BREAKING (data)** | No |
| 2026-05-21 02:09 | `raw.orders` | Column `total` renamed to `amount` | **BREAKING** | No |
| 2026-05-15 11:20 | `raw.customers` | Added column `region` | Additive (safe) | No |

## Notes

- The **2026-06-10 02:14** rename (`amount → order_amount`) landed *after* ingestion
  at 02:00 but *before* the staging build at 02:10 on some runs, and the staging
  model `stg_orders` still selects the old column name `amount`.
- The **2026-05-28** entry is a *data* regression (not a structural change): the
  column still exists but began producing NULLs. This is the root cause referenced
  by postmortem `2026-05-28-orders-null-spike.md`.
- The **2026-05-21** rename is structurally identical to the 2026-06-10 incident and
  is a strong precedent; see postmortem `2026-05-21-revenue-dashboard-empty.md`.
