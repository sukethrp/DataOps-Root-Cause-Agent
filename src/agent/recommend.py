"""Final root-cause recommendation (propose-only)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .config import Settings
from .prompts import RECOMMEND_INSTRUCTIONS, build_recommend_input, filter_grounding_by_citations
from .retrieval import Citation, Passage, RetrievalClient, RetrievalResult
from .triage import TriageResult
from .verifier import VerifiedHypothesis, VerifiedHypotheses

PROPOSE_ONLY_ACTION: Literal["proposal"] = "proposal"


class RecommendationCitation(BaseModel):
    """Resolved citation included in the final result."""

    ref_id: str
    doc_key: str | None = None
    source_type: str | None = None
    content: str | None = None


class RecommendationDraft(BaseModel):
    """Structured model output for the recommendation narrative."""

    root_cause: str = Field(min_length=1)
    recommended_fix: str = Field(min_length=1)


class Recommendation(BaseModel):
    """Final diagnosis and fix proposal. Never executed by the agent."""

    root_cause: str
    recommended_fix: str
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[RecommendationCitation]
    action_type: Literal["proposal"] = PROPOSE_ONLY_ACTION


class RecommendError(RuntimeError):
    """Raised when recommendation generation fails."""


def recommend(
    verified: VerifiedHypotheses,
    grounding: RetrievalResult,
    *,
    triage: TriageResult | None = None,
    settings: Settings | None = None,
    retrieval_client: RetrievalClient | None = None,
) -> Recommendation:
    """Build a propose-only recommendation from the top verified hypothesis."""
    if not verified.hypotheses:
        msg = "No verified hypotheses available for recommendation"
        raise RecommendError(msg)

    top = verified.hypotheses[0]
    active_settings = settings or Settings.from_env()
    owns_client = retrieval_client is None
    client = retrieval_client or RetrievalClient(active_settings)

    try:
        openai_client = client.project_client.get_openai_client()
        response = openai_client.responses.parse(
            model=active_settings.model_name,
            instructions=RECOMMEND_INSTRUCTIONS,
            input=build_recommend_input(top, grounding, triage=triage),
            text_format=RecommendationDraft,
        )
    finally:
        if owns_client:
            client.close()

    draft = response.output_parsed
    if draft is None:
        msg = "Model did not return structured recommendation output"
        raise RecommendError(msg)

    citations = resolve_citations(top.citation_ids, grounding)
    return Recommendation(
        root_cause=draft.root_cause,
        recommended_fix=draft.recommended_fix,
        confidence=top.confidence,
        citations=citations,
        action_type=PROPOSE_ONLY_ACTION,
    )


def resolve_citations(
    citation_ids: list[str],
    grounding: RetrievalResult,
) -> list[RecommendationCitation]:
    """Map ref_ids to doc keys and passage text from retrieval grounding."""
    cited = filter_grounding_by_citations(grounding, citation_ids)
    passage_by_id = {passage.ref_id: passage for passage in cited.passages}
    citation_by_id = {item.ref_id: item for item in cited.citations}

    resolved: list[RecommendationCitation] = []
    for ref_id in citation_ids:
        passage: Passage | None = passage_by_id.get(ref_id)
        meta: Citation | None = citation_by_id.get(ref_id)
        resolved.append(
            RecommendationCitation(
                ref_id=ref_id,
                doc_key=meta.doc_key if meta else None,
                source_type=meta.source_type if meta else None,
                content=passage.content if passage else None,
            )
        )
    return resolved
