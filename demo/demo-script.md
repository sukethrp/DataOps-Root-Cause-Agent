# Demo Script (2 to 3 minutes)

Goal: show the agent reasoning in clear steps, grounding with citations, and
proposing (not executing) a fix. Use **Incident 1**; it traces end-to-end cleanly.

## 0:00 to 0:20: The hook (the pain)

> "At 02:16 this morning the revenue pipeline broke and the exec dashboard went
> blank. Normally an on-call engineer spends 30 to 45 minutes tracing *why*. Watch my
> agent run the diagnosis in seconds and cite every source."

Show `incidents/incident-01-dbt-failure.log` on screen briefly.

## 0:20 to 0:45: Triage

Paste the failing log into the agent. Narrate as it classifies:
> "It recognizes a dbt build failure on `stg_orders`, `column amount does not exist`,
> and flags this as a possible schema-drift event."

## 0:45 to 1:30: Ground (Foundry IQ) + reason

Show the agent retrieving and **citing**:
> "Using Foundry IQ it pulls the lineage, the schema changelog, the schema-drift
> runbook, and a similar past incident, each with a citation. It then reasons:
> the column `amount` was renamed to `order_amount` at 02:14, two minutes before the
> failure, by the upstream team, and `stg_orders` still selects the old name."

Point at the citations on screen.

## 1:30 to 2:00: Verify (verifier sub-agent)

> "Before it commits, a verifier sub-agent checks each claim against the retrieved
> evidence and drops anything unsupported. Here it rejected a late-partition hypothesis
> because no missing-partition evidence was found."

Show one hypothesis being kept (cited) and one being discarded (no support).

## 2:00 to 2:30: Recommend + safety

> "It outputs the root cause with a 0.93 confidence score and a concrete fix:
> update the model to select `order_amount`. It **proposes** the fix; it never
> touches production. It also emits a full audit log of the reasoning trace, so the
> change is reviewable."

Show the final cited answer + the audit log.

## 2:30 to end: Close

> "Every step is cited, the verifier filters unsupported claims, and the fix stays
> a proposal. That is the loop: Foundry for orchestration, Foundry IQ for retrieval."

## Recording tips

- Screen-record at 1080p; keep it under 3 minutes.
- Pre-load the corpus so retrieval is instant on camera.
- Have the keep/discard verifier moment visible; that moment maps to Reliability and IQ.
- End on the cited final answer frozen on screen.
