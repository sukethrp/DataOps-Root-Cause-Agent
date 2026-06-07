# DataOps Root-Cause Agent

A reasoning agent that diagnoses **data-pipeline failures** (schema drift, missing
partitions, and data-quality regressions) by **grounding on runbooks, lineage, and
past incidents via Foundry IQ**, then returning a **cited root cause and fix** with a
**confidence score** and an **audit log** of its reasoning.

- **Hackathon:** Agents League @ Microsoft AI Skills Fest 2026
- **Track:** 🧠 Reasoning Agents (built on Microsoft Foundry)
- **Required IQ layer:** **Foundry IQ** for permission-aware, *cited* retrieval over
  the knowledge corpus.

## The problem

When a data pipeline breaks at 02:00, on-call engineers waste the most time on the
*diagnosis*, not the fix: tracing a cryptic error through lineage, schema history, and
half-remembered past incidents. This agent does that triage in seconds, with citations
on every claim, so a human can approve the fix with confidence.

## How it works (the reasoning loop)

1. **Triage:** ingest the incident signal (a dbt/Airflow log or a DQ alert) and
   classify the failure type.
2. **Ground (Foundry IQ):** retrieve the relevant lineage, schema changelog entries,
   the matching runbook, and similar past postmortems. Every retrieved fact is **cited**.
3. **Hypothesize:** produce a ranked list of candidate root causes with explicit,
   step-by-step reasoning.
4. **Verify:** a **verifier sub-agent** (LLM-as-judge pattern) tests each hypothesis
   against the retrieved evidence and **drops any claim not supported by a citation**.
5. **Recommend:** output the confirmed root cause + a concrete, cited fix.
6. **Safety:** the agent **proposes, never executes**; it emits a **confidence score**
   and a full **audit log** of the reasoning trace.

## Grounded corpus (what Foundry IQ indexes)

Point Foundry IQ at the **`knowledge/`** folder:

```
knowledge/
  architecture-and-lineage.md      # pipeline DAG, tables, owners, schedules, SLAs
  schema-changelog.md              # timestamped upstream schema changes (breaking flagged)
  runbooks/
    schema-drift.md
    missing-late-partition.md
    data-quality-null-spike.md
    source-freshness-sla.md
  postmortems/
    2026-05-21-revenue-dashboard-empty.md
    2026-05-28-orders-null-spike.md
```

The **`incidents/`** folder holds three ready-to-diagnose inputs (the agent's test
cases); **`demo/`** holds the demo walkthrough.

## Try it

Run the agent against each incident:

| Incident | Input | Expected root cause |
|----------|-------|--------------------|
| 1 (demo) | `incidents/incident-01-dbt-failure.log` | Upstream rename `orders.amount → order_amount` at 02:14 broke `stg_orders` |
| 2 | `incidents/incident-02-airflow-traceback.txt` | Upstream daily export for `date=2026-06-11` landed late → missing partition |
| 3 | `incidents/incident-03-dq-alert.json` | Source deploy began emitting NULL `order_amount` (data regression) |

### Expected output for Incident 1

> **Root cause (confidence 0.93):** The dbt model `stg_orders` failed with
> `column "amount" does not exist`. The upstream Source team renamed
> `raw.orders.amount` → `order_amount` at 2026-06-10 02:14 UTC
> [schema-changelog.md], while `stg_orders` still selects `amount`
> [architecture-and-lineage.md]. This matches the schema-drift pattern
> [runbooks/schema-drift.md] and precedent SEV-2 on 2026-05-21
> [postmortems/2026-05-21-revenue-dashboard-empty.md].
>
> **Recommended fix:** update `stg_orders` to `select order_amount as amount`,
> then `dbt build --select stg_orders+` and refresh "Revenue Daily".
> **Action type:** proposal only, not executed.

## Architecture (Microsoft stack)

- **Microsoft Foundry:** agent runtime and orchestration of the reasoning loop.
- **Foundry IQ:** retrieval over `knowledge/` with citations.
- (Optional stretch) **Fabric IQ:** reason over the warehouse schema semantics
  directly, on top of the document grounding.

## How this maps to the judging rubric

- **Reasoning & multi-step thinking (20%):** explicit triage → ground → hypothesize →
  verify → recommend chain.
- **Reliability & safety (20%):** propose-only, confidence scoring, audit log, and a
  verifier that suppresses unsupported claims.
- **Accuracy & relevance (20%):** every conclusion is tied to a cited source.
- **Creativity & originality (15%):** pipeline incident diagnosis is a concrete use
  case for a cited reasoning loop.
- **UX & presentation (15%):** cited output and a short demo.
- **Community vote (10%):** share progress in the Agents League Discord.

## License

MIT (sample/synthetic data; no confidential information).
