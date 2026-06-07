"""LLM-as-judge verification of cited root-cause hypotheses."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .config import Settings
from .prompts import (
    VERIFIER_INSTRUCTIONS,
    build_verifier_input,
    filter_grounding_by_citations,
)
from .reasoner import Hypothesis, Hypotheses
from .retrieval import RetrievalClient, RetrievalResult
from .triage import TriageResult


class VerificationJudgment(BaseModel):
    """Structured output from a single hypothesis judge call."""

    supported: bool = Field(description="True when cited evidence supports the root-cause claim.")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Strength of support from cited evidence.",
    )
    supporting_citation_ids: list[str] = Field(
        description="ref_id values from the cited grounding that directly support the claim.",
    )
    rationale: str = Field(
        min_length=1,
        description="Brief explanation of the verification decision.",
    )


class VerifiedHypothesis(BaseModel):
    """A hypothesis that passed citation-backed verification."""

    rank: int = Field(ge=1, description="Rank among surviving hypotheses by confidence.")
    summary: str = Field(min_length=1)
    reasoning_steps: list[str] = Field(min_length=1)
    citation_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class VerifiedHypotheses(BaseModel):
    """Ranked, scored hypotheses that survived verification."""

    hypotheses: list[VerifiedHypothesis] = Field(default_factory=list)


class VerifierError(RuntimeError):
    """Raised when verification fails."""


def verify(
    hypotheses: Hypotheses,
    grounding: RetrievalResult,
    *,
    triage: TriageResult | None = None,
    settings: Settings | None = None,
    retrieval_client: RetrievalClient | None = None,
) -> VerifiedHypotheses:
    """Verify each hypothesis against its cited evidence; drop unsupported claims."""
    active_settings = settings or Settings.from_env()
    owns_client = retrieval_client is None
    client = retrieval_client or RetrievalClient(active_settings)

    try:
        openai_client = client.project_client.get_openai_client()
        survivors: list[VerifiedHypothesis] = []

        for hypothesis in sorted(hypotheses.hypotheses, key=lambda item: item.rank):
            verified = _verify_one(
                hypothesis,
                grounding,
                triage=triage,
                openai_client=openai_client,
                model_name=active_settings.model_name,
            )
            if verified is not None:
                survivors.append(verified)

        survivors.sort(key=lambda item: item.confidence, reverse=True)
        ranked = [
            item.model_copy(update={"rank": index})
            for index, item in enumerate(survivors, start=1)
        ]
        return VerifiedHypotheses(hypotheses=ranked)
    finally:
        if owns_client:
            client.close()


def _verify_one(
    hypothesis: Hypothesis,
    grounding: RetrievalResult,
    *,
    triage: TriageResult | None,
    openai_client: object,
    model_name: str,
) -> VerifiedHypothesis | None:
    if not hypothesis.citation_ids:
        return None

    cited_grounding = filter_grounding_by_citations(grounding, hypothesis.citation_ids)
    if not cited_grounding.passages and not cited_grounding.citations:
        return None

    valid_ids = _valid_citation_ids(grounding)
    if not any(ref_id in valid_ids for ref_id in hypothesis.citation_ids):
        return None

    response = openai_client.responses.parse(
        model=model_name,
        instructions=VERIFIER_INSTRUCTIONS,
        input=build_verifier_input(hypothesis, cited_grounding, triage=triage),
        text_format=VerificationJudgment,
    )

    judgment = response.output_parsed
    if judgment is None:
        msg = f"Model did not return verification output for hypothesis rank {hypothesis.rank}"
        raise VerifierError(msg)

    if not judgment.supported:
        return None

    supporting_ids = [
        ref_id
        for ref_id in judgment.supporting_citation_ids
        if ref_id in valid_ids and ref_id in set(hypothesis.citation_ids)
    ]
    if not supporting_ids:
        return None

    confidence = max(0.0, min(1.0, judgment.confidence))
    if confidence <= 0.0:
        return None

    return VerifiedHypothesis(
        rank=hypothesis.rank,
        summary=hypothesis.summary,
        reasoning_steps=hypothesis.reasoning_steps,
        citation_ids=supporting_ids,
        confidence=confidence,
    )


def _valid_citation_ids(grounding: RetrievalResult) -> set[str]:
    ids = {passage.ref_id for passage in grounding.passages if passage.ref_id}
    ids.update(citation.ref_id for citation in grounding.citations if citation.ref_id)
    return ids
