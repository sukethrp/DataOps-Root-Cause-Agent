# Demo Script (2–3 minutes)

Goal: show the agent reasoning in clear steps, grounding with citations, and
proposing (not executing) a fix. Use **Incident 1** — it traces end-to-end cleanly.

## 0:00 – 0:20 — The hook (the pain)

> "At 02:16 this morning the revenue pipeline broke and the exec dashboard went
> blank. Normally an on-call engineer spends 30–45 minutes tracing *why*. Watch my
> agent do the diagnosis in seconds — and show its work."

Show `incidents/incident-01-dbt-failure.log` on screen briefly.

## 0:20 – 0:45 — Triage

Paste the failing log into the agent. Narrate as it classifies:
> "It recognizes a dbt build failure on `stg_orders`, `column amount does not exist`,
> and flags this as a possible schema-drift event."

## 0:45 – 1:30 — Ground (Foundry IQ) + reason

Show the agent retrieving and **citing**:
> "Using Foundry IQ it pulls the lineage, the schema changelog, the schema-drift
> runbook, and a similar past incident — every fact cited. It then reasons:
> the column `amount` was renamed to `order_amount` at 02:14, two minutes before the
> failure, by the upstream team — and `stg_orders` still selects the old name."

Point at the citations on screen.

## 1:30 – 2:00 — Verify (the anti-hallucination core)

> "Before it commits, a verifier sub-agent checks each claim against the retrieved
> evidence and drops anything unsupported. Here it rejected a plausible-but-ungrounded
> 'late partition' hypothesis because no missing-partition evidence was found."

Show one hypothesis being kept (cited) and one being discarded (no support).

## 2:00 – 2:30 — Recommend + safety

> "It outputs the root cause with a 0.93 confidence score and a concrete fix —
> update the model to select `order_amount`. Critically, it **proposes** the fix;
> it never touches production. And it emits a full audit log of its reasoning trace,
> so the change is reviewable."

Show the final cited answer + the audit log.

## 2:30 – end — Close

> "Grounded, cited, verified, and safe by design — a reasoning agent for data-ops,
> built on Microsoft Foundry with Foundry IQ at its core."

## Recording tips

- Screen-record at 1080p; keep it under 3 minutes.
- Pre-load the corpus so retrieval is instant on camera.
- Have the keep/discard verifier moment visible — that beat sells Reliability and IQ.
- End on the cited final answer frozen on screen.
