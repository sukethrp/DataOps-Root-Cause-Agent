"""Tests for hypothesis verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from agent.config import Settings
from agent.reasoner import Hypothesis, Hypotheses
from agent.retrieval import Citation, Passage, RetrievalResult
from agent.verifier import VerificationJudgment, verify


@dataclass
class _FakeParseResponse:
    output_parsed: VerificationJudgment | None


class _FakeResponses:
    def __init__(self, judgments: dict[str, VerificationJudgment]) -> None:
        self._judgments = judgments

    def parse(self, **kwargs: Any) -> _FakeParseResponse:
        prompt = str(kwargs.get("input", "")).lower()
        if "late partition caused downstream" in prompt:
            judgment = self._judgments["unsupported"]
        else:
            judgment = self._judgments["supported"]
        return _FakeParseResponse(output_parsed=judgment)


class _FakeOpenAIClient:
    def __init__(self, judgments: dict[str, VerificationJudgment]) -> None:
        self.responses = _FakeResponses(judgments)


class _FakeProjectClient:
    def __init__(self, judgments: dict[str, VerificationJudgment]) -> None:
        self._client = _FakeOpenAIClient(judgments)

    def get_openai_client(self) -> _FakeOpenAIClient:
        return self._client

    def close(self) -> None:
        return None


class _FakeRetrievalClient:
    def __init__(self, judgments: dict[str, VerificationJudgment]) -> None:
        self.project_client = _FakeProjectClient(judgments)

    def close(self) -> None:
        return None


def _test_settings() -> Settings:
    return Settings(
        project_endpoint="https://example.services.ai.azure.com/api/projects/demo",
        search_endpoint="https://demo.search.windows.net",
        knowledge_base_name="demo-kb",
        kb_mcp_endpoint="https://demo.search.windows.net/knowledgebases/demo-kb/mcp?api-version=2026-05-01-preview",
        model_name="gpt-4.1",
    )


def test_verifier_drops_unsupported_hypothesis() -> None:
    grounding = RetrievalResult(
        passages=[
            Passage(
                ref_id="0",
                title="schema-changelog.md",
                content="2026-06-10 02:14 raw.orders amount renamed to order_amount",
            )
        ],
        citations=[Citation(ref_id="0", doc_key="schema-changelog.md", source_type="local")],
    )
    hypotheses = Hypotheses(
        hypotheses=[
            Hypothesis(
                rank=1,
                summary="Upstream column rename broke stg_orders",
                reasoning_steps=[
                    "Error references missing column amount.",
                    "Changelog shows amount renamed to order_amount at 02:14 UTC.",
                ],
                citation_ids=["0"],
            ),
            Hypothesis(
                rank=2,
                summary="Late partition caused downstream build issues",
                reasoning_steps=[
                    "Partition delays can leave upstream tables empty.",
                    "No missing-partition signal appears in triage.",
                ],
                citation_ids=["0"],
            ),
        ]
    )
    judgments = {
        "supported": VerificationJudgment(
            supported=True,
            confidence=0.91,
            supporting_citation_ids=["0"],
            rationale="Changelog entry supports the rename claim.",
        ),
        "unsupported": VerificationJudgment(
            supported=False,
            confidence=0.15,
            supporting_citation_ids=[],
            rationale="Cited changelog does not mention a missing partition.",
        ),
    }
    client = _FakeRetrievalClient(judgments)

    verified = verify(
        hypotheses,
        grounding,
        settings=_test_settings(),
        retrieval_client=client,  # type: ignore[arg-type]
    )

    assert len(verified.hypotheses) == 1
    assert verified.hypotheses[0].rank == 1
    assert verified.hypotheses[0].summary == "Upstream column rename broke stg_orders"
    assert verified.hypotheses[0].citation_ids == ["0"]
    assert verified.hypotheses[0].confidence == pytest.approx(0.91)
