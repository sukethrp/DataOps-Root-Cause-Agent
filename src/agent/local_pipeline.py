"""Deterministic reasoning steps for local/demo runs without model calls."""

from __future__ import annotations

from .reasoner import Hypothesis, Hypotheses
from .recommend import Recommendation, RecommendationCitation, resolve_citations
from .retrieval import RetrievalResult
from .triage import FailureType, TriageResult
from .verifier import VerifiedHypothesis, VerifiedHypotheses


def reason_heuristic(triage: TriageResult, grounding: RetrievalResult) -> Hypotheses:
    """Build ranked hypotheses from triage and locally retrieved grounding."""
    if triage.failure_type == FailureType.SCHEMA_DRIFT:
        return _schema_drift_hypotheses(triage, grounding)
    if triage.failure_type == FailureType.MISSING_PARTITION:
        return _missing_partition_hypotheses(triage, grounding)
    if triage.failure_type == FailureType.DATA_QUALITY:
        return _data_quality_hypotheses(triage, grounding)
    return Hypotheses(
        hypotheses=[
            Hypothesis(
                rank=1,
                summary=triage.error_text or "Unknown pipeline failure",
                reasoning_steps=["Insufficient structured signal to classify further."],
                citation_ids=_refs_for_docs(grounding)[:2],
            )
        ]
    )


def verify_heuristic(hypotheses: Hypotheses, grounding: RetrievalResult) -> VerifiedHypotheses:
    """Keep hypotheses whose citations resolve to retrieved grounding."""
    valid_ids = {passage.ref_id for passage in grounding.passages} | {
        citation.ref_id for citation in grounding.citations
    }
    survivors: list[VerifiedHypothesis] = []
    for hypothesis in sorted(hypotheses.hypotheses, key=lambda item: item.rank):
        if not hypothesis.citation_ids:
            continue
        supporting = [ref_id for ref_id in hypothesis.citation_ids if ref_id in valid_ids]
        if not supporting:
            continue
        confidence = 0.93 if hypothesis.rank == 1 else max(0.5, 0.9 - (hypothesis.rank - 1) * 0.15)
        survivors.append(
            VerifiedHypothesis(
                rank=hypothesis.rank,
                summary=hypothesis.summary,
                reasoning_steps=hypothesis.reasoning_steps,
                citation_ids=supporting,
                confidence=confidence,
            )
        )
    survivors.sort(key=lambda item: item.confidence, reverse=True)
    ranked = [
        item.model_copy(update={"rank": index}) for index, item in enumerate(survivors, start=1)
    ]
    return VerifiedHypotheses(hypotheses=ranked)


def recommend_heuristic(
    verified: VerifiedHypotheses,
    grounding: RetrievalResult,
    *,
    triage: TriageResult | None = None,
) -> Recommendation:
    """Format a propose-only recommendation from the top verified hypothesis."""
    if not verified.hypotheses:
        msg = "No verified hypotheses available for recommendation"
        raise RuntimeError(msg)

    top = verified.hypotheses[0]
    citations = resolve_citations(top.citation_ids, grounding)

    if triage and triage.failure_type == FailureType.SCHEMA_DRIFT:
        root_cause, fix = _schema_drift_recommendation(triage, citations)
    elif triage and triage.failure_type == FailureType.MISSING_PARTITION:
        root_cause, fix = _missing_partition_recommendation(triage, citations)
    elif triage and triage.failure_type == FailureType.DATA_QUALITY:
        root_cause, fix = _data_quality_recommendation(triage, citations)
    else:
        root_cause = top.summary
        fix = "Review cited runbooks and apply the documented remediation steps."

    return Recommendation(
        root_cause=root_cause,
        recommended_fix=fix,
        confidence=top.confidence,
        citations=citations,
    )


def _schema_drift_hypotheses(triage: TriageResult, grounding: RetrievalResult) -> Hypotheses:
    primary_refs = _refs_for_docs(
        grounding,
        "schema-changelog.md",
        "architecture-and-lineage.md",
        "runbooks/schema-drift.md",
        "2026-05-21-revenue-dashboard-empty.md",
    )
    alt_refs = _refs_for_docs(grounding, "missing-late-partition.md")
    object_name = triage.object_name or "stg_orders"
    column = triage.column or "amount"

    primary = Hypothesis(
        rank=1,
        summary=(
            f"Upstream rename of raw.orders.{column} to order_amount at 2026-06-10 02:14 UTC "
            f"broke {object_name}"
        ),
        reasoning_steps=[
            f"Triage shows {object_name} failed with column {column!r} missing.",
            "schema-changelog.md records a BREAKING rename amount to order_amount at 2026-06-10 02:14 UTC.",
            f"architecture-and-lineage.md shows {object_name} still selects the legacy column name.",
            "runbooks/schema-drift.md matches this failure pattern.",
            "postmortem 2026-05-21-revenue-dashboard-empty.md is a precedent for the same drift pattern.",
        ],
        citation_ids=primary_refs,
    )
    alt = Hypothesis(
        rank=2,
        summary=f"Late or missing partition caused downstream build issues for {object_name}",
        reasoning_steps=[
            "Partition delays can skip or partially load upstream tables.",
            "No missing-partition error appears in the triage signal.",
        ],
        citation_ids=alt_refs,
    )
    return Hypotheses(hypotheses=[primary, alt])


def _missing_partition_hypotheses(triage: TriageResult, grounding: RetrievalResult) -> Hypotheses:
    refs = _refs_for_docs(
        grounding,
        "missing-late-partition.md",
        "architecture-and-lineage.md",
        "source-freshness-sla.md",
    )
    partition = triage.partition_date or "2026-06-11"
    return Hypotheses(
        hypotheses=[
            Hypothesis(
                rank=1,
                summary=(
                    f"Upstream daily export for date={partition} landed late, "
                    "so the expected partition was missing at extract time"
                ),
                reasoning_steps=[
                    f"Airflow extract_orders failed with PartitionNotFoundError for date={partition}.",
                    "Trace notes upstream nightly export still running after its normal completion window.",
                    "runbooks/missing-late-partition.md covers late upstream delivery causing missing partitions.",
                    "architecture-and-lineage.md places raw.orders ingest ahead of dbt staging.",
                ],
                citation_ids=refs,
            )
        ]
    )


def _data_quality_hypotheses(triage: TriageResult, grounding: RetrievalResult) -> Hypotheses:
    refs = _refs_for_docs(
        grounding,
        "schema-changelog.md",
        "data-quality-null-spike.md",
        "2026-05-28-orders-null-spike.md",
        "architecture-and-lineage.md",
    )
    column = triage.column or "order_amount"
    return Hypotheses(
        hypotheses=[
            Hypothesis(
                rank=1,
                summary=(
                    f"Source deploy began emitting NULL {column} values (data regression), "
                    "raising null_rate on fct_revenue_daily"
                ),
                reasoning_steps=[
                    "DQ alert shows build succeeded but null_rate exceeded threshold.",
                    f"schema-changelog.md documents a 2026-05-28 NULL regression on raw.orders.{column}.",
                    "runbooks/data-quality-null-spike.md describes this failure mode.",
                    "postmortem 2026-05-28-orders-null-spike.md matches the same regression pattern.",
                ],
                citation_ids=refs,
            )
        ]
    )


def _schema_drift_recommendation(
    triage: TriageResult,
    citations: list[RecommendationCitation],
) -> tuple[str, str]:
    object_name = triage.object_name or "stg_orders"
    column = triage.column or "amount"
    cite_text = _format_inline_citations(citations)
    root_cause = (
        f'The dbt model {object_name} failed with column "{column}" does not exist. '
        "The upstream Source team renamed raw.orders.amount to order_amount at "
        f"2026-06-10 02:14 UTC {cite_text}. "
        f"{object_name} still selects {column} while upstream now exposes order_amount."
    )
    fix = (
        f"Update {object_name} to select order_amount as {column}, then run "
        f"`dbt build --select {object_name}+` and refresh the Revenue Daily dashboard. "
        "Proposal only; do not execute automatically."
    )
    return root_cause, fix


def _missing_partition_recommendation(
    triage: TriageResult,
    citations: list[RecommendationCitation],
) -> tuple[str, str]:
    partition = triage.partition_date or "2026-06-11"
    cite_text = _format_inline_citations(citations)
    root_cause = (
        f"extract_orders failed because partition date={partition} was not present when the DAG ran. "
        f"The upstream oltp_orders_export landed late {cite_text}."
    )
    fix = (
        f"Confirm upstream export for date={partition} completed, backfill raw.orders for that partition, "
        "then rerun extract_orders and downstream dbt tasks. Proposal only; do not execute automatically."
    )
    return root_cause, fix


def _data_quality_recommendation(
    triage: TriageResult,
    citations: list[RecommendationCitation],
) -> tuple[str, str]:
    column = triage.column or "order_amount"
    cite_text = _format_inline_citations(citations)
    root_cause = (
        f"Build succeeded but {triage.object_name or 'fct_revenue_daily'}.{column} null_rate spiked. "
        f"A source-side data regression is emitting NULL {column} values {cite_text}."
    )
    fix = (
        "Coordinate with the Source team on the recent deploy, validate raw.orders null rates, "
        "backfill affected partitions after upstream fix, and rerun dbt tests on fct_revenue_daily. "
        "Proposal only; do not execute automatically."
    )
    return root_cause, fix


def _refs_for_docs(grounding: RetrievalResult, *doc_substrings: str) -> list[str]:
    refs: list[str] = []
    for citation in grounding.citations:
        if not citation.doc_key:
            continue
        if any(substring in citation.doc_key for substring in doc_substrings):
            refs.append(citation.ref_id)
    if refs:
        return refs
    return [citation.ref_id for citation in grounding.citations[:4]]


def _format_inline_citations(citations: list[RecommendationCitation]) -> str:
    keys = [f"[{cite.doc_key}]" for cite in citations if cite.doc_key]
    if not keys:
        return ""
    return " ".join(keys)
