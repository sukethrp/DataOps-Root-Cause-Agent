"""Prompt templates and builders for agent reasoning steps."""

from __future__ import annotations

from .retrieval import RetrievalResult
from .triage import TriageResult

REASONER_INSTRUCTIONS = """\
You are a data pipeline root-cause analyst for ShopCo revenue analytics.

Given triage metadata and grounded knowledge-base passages, produce a ranked list of root-cause
hypotheses. Use only facts supported by the grounding passages.

Rules:
- Rank hypotheses from most to least likely (rank 1 = top candidate).
- Each hypothesis must include explicit step-by-step reasoning (one step per list item).
- Each hypothesis must list citation_ids: the ref_id values from grounding that support it.
- Do not cite ref_ids that are not present in the grounding block.
- Do not invent schema changes, timestamps, or owners absent from grounding.
- Prefer hypotheses that match the triage failure_type and align with runbooks or postmortems when cited.
- Include at least one hypothesis; include alternatives when grounding supports them.
"""


def build_retrieval_query(triage: TriageResult) -> str:
    """Build a Foundry IQ query from triage fields."""
    parts = [f"failure type: {triage.failure_type.value}"]

    if triage.object_name:
        parts.append(f"object: {triage.object_name}")
    if triage.error_text:
        parts.append(f"error: {triage.error_text}")
    if triage.column:
        parts.append(f"column: {triage.column}")
    if triage.partition_date:
        parts.append(f"partition date: {triage.partition_date}")
    if triage.timestamp:
        parts.append(f"timestamp: {triage.timestamp}")

    parts.append(
        "Retrieve lineage, schema changelog, matching runbook, and similar past postmortems."
    )
    return ". ".join(parts)


def format_grounding(grounding: RetrievalResult) -> str:
    """Serialize retrieval passages and citations for the reasoner prompt."""
    lines: list[str] = []
    citation_by_id = {citation.ref_id: citation for citation in grounding.citations}
    seen_ids: set[str] = set()

    for passage in grounding.passages:
        seen_ids.add(passage.ref_id)
        citation = citation_by_id.get(passage.ref_id)
        header = f"[ref_id:{passage.ref_id}]"
        if passage.title:
            header += f" title={passage.title!r}"
        if citation and citation.doc_key:
            header += f" doc_key={citation.doc_key!r}"
        lines.extend([header, passage.content, ""])

    for citation in grounding.citations:
        if citation.ref_id in seen_ids:
            continue
        lines.append(f"[ref_id:{citation.ref_id}] doc_key={citation.doc_key!r} (metadata only)")

    if not lines:
        return "(no grounding passages returned)"
    return "\n".join(lines).strip()


def build_reasoner_input(triage: TriageResult, grounding: RetrievalResult) -> str:
    """Assemble the user message for root-cause hypothesis generation."""
    triage_lines = [
        f"failure_type: {triage.failure_type.value}",
        f"object_name: {triage.object_name}",
        f"error_text: {triage.error_text}",
        f"timestamp: {triage.timestamp}",
        f"column: {triage.column}",
        f"partition_date: {triage.partition_date}",
    ]

    return (
        "## Triage\n"
        + "\n".join(triage_lines)
        + "\n\n## Grounding (cite using ref_id)\n"
        + format_grounding(grounding)
    )
