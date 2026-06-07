"""Prompt templates and builders for agent reasoning steps."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .retrieval import RetrievalResult
from .triage import TriageResult

if TYPE_CHECKING:
    from .reasoner import Hypothesis

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


VERIFIER_INSTRUCTIONS = """\
You are an impartial judge verifying data pipeline root-cause hypotheses.

Given one hypothesis, its reasoning steps, and the cited grounding passages only, decide
whether the evidence actually supports the root-cause claim.

Rules:
- supported is true only when every key factual claim in the summary is backed by the cited passages.
- confidence is between 0 and 1 (0 = no support, 1 = fully supported). Use values below 0.5 when support is weak or partial.
- supporting_citation_ids must list only ref_id values from the grounding that directly support the claim.
- If the hypothesis cites passages that do not substantiate the claim, set supported to false.
- Do not infer facts beyond the cited grounding text.
- Reasoning steps that overreach beyond the citations should lower confidence or fail verification.
"""


def build_verifier_input(
    hypothesis: Hypothesis,
    grounding: RetrievalResult,
    *,
    triage: TriageResult | None = None,
) -> str:
    """Assemble the user message for a single hypothesis verification call."""
    lines = [
        "## Hypothesis",
        f"rank: {hypothesis.rank}",
        f"summary: {hypothesis.summary}",
        "reasoning_steps:",
    ]
    lines.extend(f"- {step}" for step in hypothesis.reasoning_steps)
    lines.append(f"citation_ids: {hypothesis.citation_ids}")

    if triage is not None:
        lines.extend(
            [
                "",
                "## Triage context",
                f"failure_type: {triage.failure_type.value}",
                f"object_name: {triage.object_name}",
                f"error_text: {triage.error_text}",
            ]
        )

    lines.extend(
        [
            "",
            "## Cited grounding only",
            format_grounding(grounding),
        ]
    )
    return "\n".join(lines)


def filter_grounding_by_citations(
    grounding: RetrievalResult,
    citation_ids: list[str],
) -> RetrievalResult:
    """Return grounding passages and citations limited to the given ref_ids."""
    cited = set(citation_ids)
    return RetrievalResult(
        passages=[passage for passage in grounding.passages if passage.ref_id in cited],
        citations=[citation for citation in grounding.citations if citation.ref_id in cited],
    )
