"""Root-cause hypothesis generation grounded on Foundry IQ retrieval."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .config import Settings
from .prompts import REASONER_INSTRUCTIONS, build_reasoner_input, build_retrieval_query
from .retrieval import RetrievalClient
from .triage import TriageResult


class Hypothesis(BaseModel):
    """A ranked root-cause candidate with cited reasoning."""

    rank: int = Field(ge=1, description="Likelihood rank; 1 is most likely.")
    summary: str = Field(min_length=1, description="One-sentence root cause claim.")
    reasoning_steps: list[str] = Field(
        min_length=1,
        description="Explicit step-by-step reasoning supporting the summary.",
    )
    citation_ids: list[str] = Field(
        description="ref_id values from grounding that support this hypothesis.",
    )


class Hypotheses(BaseModel):
    """Ranked list of root-cause hypotheses."""

    hypotheses: list[Hypothesis] = Field(min_length=1)


class ReasonerError(RuntimeError):
    """Raised when hypothesis generation fails."""


def reason(
    triage: TriageResult,
    *,
    settings: Settings | None = None,
    retrieval_client: RetrievalClient | None = None,
) -> Hypotheses:
    """Ground on the knowledge base and produce ranked, cited root-cause hypotheses."""
    active_settings = settings or Settings.from_env()
    owns_client = retrieval_client is None
    client = retrieval_client or RetrievalClient(active_settings)

    try:
        grounding = client.retrieve(build_retrieval_query(triage))
        openai_client = client.project_client.get_openai_client()
        response = openai_client.responses.parse(
            model=active_settings.model_name,
            instructions=REASONER_INSTRUCTIONS,
            input=build_reasoner_input(triage, grounding),
            text_format=Hypotheses,
        )
    finally:
        if owns_client:
            client.close()

    result = response.output_parsed
    if result is None:
        msg = "Model did not return structured hypothesis output"
        raise ReasonerError(msg)
    return _sort_hypotheses(result)


def _sort_hypotheses(hypotheses: Hypotheses) -> Hypotheses:
    ranked = sorted(hypotheses.hypotheses, key=lambda item: item.rank)
    return Hypotheses(hypotheses=ranked)
