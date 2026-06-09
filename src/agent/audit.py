"""Persist full agent reasoning traces under runs/."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .recommend import Recommendation
from .reasoner import Hypothesis, Hypotheses
from .retrieval import RetrievalResult
from .triage import TriageResult
from .verifier import VerifiedHypothesis, VerifiedHypotheses

DEFAULT_RUNS_DIR = Path("runs")


class RetrievedCitationRecord(BaseModel):
    """Citation returned by Foundry IQ retrieval."""

    ref_id: str
    doc_key: str | None = None
    source_type: str | None = None
    content: str | None = None


class DroppedHypothesisRecord(BaseModel):
    """Hypothesis removed during verification."""

    rank: int
    summary: str
    citation_ids: list[str] = Field(default_factory=list)
    reason: str = "failed_verification"


class AuditRecord(BaseModel):
    """Full reasoning trace for one agent run."""

    run_id: str
    recorded_at: str
    input_raw: str
    triage: TriageResult
    retrieval_query: str
    retrieved_citations: list[RetrievedCitationRecord]
    hypotheses_generated: list[Hypothesis]
    hypotheses_kept: list[VerifiedHypothesis]
    hypotheses_dropped: list[DroppedHypothesisRecord]
    recommendation: Recommendation | None = None
    confidence: float | None = None


class AuditTrace(BaseModel):
    """Inputs required to build and persist an audit record."""

    input_raw: str
    triage: TriageResult
    retrieval_query: str
    grounding: RetrievalResult
    hypotheses: Hypotheses
    verified: VerifiedHypotheses
    recommendation: Recommendation | None = None
    run_id: str | None = None


def record_audit(
    trace: AuditTrace,
    *,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> Path:
    """Write the full reasoning trace as JSON under runs/."""
    run_id = trace.run_id or _new_run_id()
    dropped = [
        DroppedHypothesisRecord(
            rank=item.rank,
            summary=item.summary,
            citation_ids=list(item.citation_ids),
            reason=item.reason,
        )
        for item in trace.verified.dropped
    ]

    record = AuditRecord(
        run_id=run_id,
        recorded_at=datetime.now(UTC).isoformat(),
        input_raw=trace.input_raw,
        triage=trace.triage,
        retrieval_query=trace.retrieval_query,
        retrieved_citations=_serialize_retrieved(trace.grounding),
        hypotheses_generated=list(trace.hypotheses.hypotheses),
        hypotheses_kept=list(trace.verified.hypotheses),
        hypotheses_dropped=dropped,
        recommendation=trace.recommendation,
        confidence=_top_confidence(trace.verified, trace.recommendation),
    )

    output_dir = Path(runs_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{run_id}.json"
    output_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return output_path


def _new_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _serialize_retrieved(grounding: RetrievalResult) -> list[RetrievedCitationRecord]:
    passage_by_id = {passage.ref_id: passage for passage in grounding.passages}
    records: list[RetrievedCitationRecord] = []

    seen: set[str] = set()
    for citation in grounding.citations:
        seen.add(citation.ref_id)
        passage = passage_by_id.get(citation.ref_id)
        records.append(
            RetrievedCitationRecord(
                ref_id=citation.ref_id,
                doc_key=citation.doc_key,
                source_type=citation.source_type,
                content=passage.content if passage else None,
            )
        )

    for passage in grounding.passages:
        if passage.ref_id in seen:
            continue
        records.append(
            RetrievedCitationRecord(
                ref_id=passage.ref_id,
                content=passage.content,
            )
        )

    return records


def _top_confidence(
    verified: VerifiedHypotheses,
    recommendation: Recommendation | None,
) -> float | None:
    if recommendation is not None:
        return recommendation.confidence
    if verified.hypotheses:
        return verified.hypotheses[0].confidence
    return None
