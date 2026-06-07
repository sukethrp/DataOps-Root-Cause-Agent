"""Foundry IQ retrieval over the knowledge base MCP endpoint."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from pydantic import BaseModel, Field

from .config import Settings

SEARCH_TOKEN_SCOPE = "https://search.azure.com/.default"
MCP_TOOL_NAME = "knowledge_base_retrieve"


class Passage(BaseModel):
    """Extractive grounding chunk from the knowledge base response."""

    ref_id: str
    content: str
    title: str | None = None
    terms: str | None = None


class Citation(BaseModel):
    """Reference metadata for a retrieved document."""

    ref_id: str
    doc_key: str | None = None
    source_type: str | None = None
    activity_source: int | None = None
    source_data: dict[str, Any] | None = None


class RetrievalResult(BaseModel):
    """Extractive passages and their citation metadata."""

    passages: list[Passage] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class RetrievalError(RuntimeError):
    """Raised when Foundry IQ retrieval fails."""


class RetrievalClient:
    """Thin client for Foundry project access and KB MCP retrieval."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings.from_env()
        self._credential = DefaultAzureCredential()
        self._project_client = AIProjectClient(
            endpoint=self._settings.project_endpoint,
            credential=self._credential,
        )

    @property
    def project_client(self) -> AIProjectClient:
        return self._project_client

    def close(self) -> None:
        self._project_client.close()
        self._credential.close()

    def __enter__(self) -> RetrievalClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def retrieve(self, query: str) -> RetrievalResult:
        """Query the knowledge base via MCP and return extractive passages with citations."""
        query = query.strip()
        if not query:
            msg = "Query must not be empty"
            raise ValueError(msg)

        token = self._credential.get_token(SEARCH_TOKEN_SCOPE).token
        payload = _call_mcp_tool(
            endpoint=self._settings.kb_mcp_endpoint,
            token=token,
            tool_name=MCP_TOOL_NAME,
            arguments={"queries": [query]},
        )
        return _parse_retrieval_payload(payload)


def _call_mcp_tool(
    *,
    endpoint: str,
    token: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request) as response:
            raw_text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        msg = f"MCP request failed with HTTP {exc.code}: {detail}"
        raise RetrievalError(msg) from exc
    except urllib.error.URLError as exc:
        msg = f"MCP request failed: {exc.reason}"
        raise RetrievalError(msg) from exc

    envelope = _parse_mcp_envelope(raw_text)
    if "error" in envelope:
        msg = f"MCP tool call failed: {envelope['error']}"
        raise RetrievalError(msg)

    return _unwrap_mcp_result(envelope.get("result", {}))


def _parse_mcp_envelope(raw_text: str) -> dict[str, Any]:
    if raw_text.lstrip().startswith("{"):
        payload = json.loads(raw_text)
        if isinstance(payload, dict):
            return payload
        msg = "MCP response must be a JSON object"
        raise RetrievalError(msg)

    for line in raw_text.splitlines():
        if line.startswith("data: "):
            payload = json.loads(line[len("data: ") :])
            if isinstance(payload, dict):
                return payload

    msg = "MCP response did not contain a JSON or SSE data payload"
    raise RetrievalError(msg)


def _unwrap_mcp_result(result: dict[str, Any]) -> dict[str, Any]:
    if "response" in result or "references" in result:
        return result

    for block in result.get("content", []):
        if block.get("type") != "text":
            continue
        text = block.get("text", "")
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    msg = "MCP tool result did not include retrieval response content"
    raise RetrievalError(msg)


def _parse_retrieval_payload(payload: dict[str, Any]) -> RetrievalResult:
    citations = [_parse_citation(ref) for ref in payload.get("references", [])]
    passages = _parse_passages(payload.get("response", []))
    return RetrievalResult(passages=passages, citations=citations)


def _parse_citation(reference: dict[str, Any]) -> Citation:
    source_data = reference.get("sourceData", reference.get("source_data"))
    if source_data is not None and not isinstance(source_data, dict):
        source_data = None

    return Citation(
        ref_id=str(reference.get("id", "")),
        doc_key=reference.get("docKey", reference.get("doc_key")),
        source_type=reference.get("type"),
        activity_source=reference.get("activitySource", reference.get("activity_source")),
        source_data=source_data,
    )


def _parse_passages(response_messages: list[dict[str, Any]]) -> list[Passage]:
    passages: list[Passage] = []

    for message in response_messages:
        for content in message.get("content", []):
            if content.get("type") != "text":
                continue
            text = content.get("text", "")
            if not text:
                continue

            try:
                chunks = json.loads(text)
            except json.JSONDecodeError:
                passages.append(Passage(ref_id="", content=text))
                continue

            if not isinstance(chunks, list):
                continue

            for chunk in chunks:
                if not isinstance(chunk, dict):
                    continue
                passages.append(
                    Passage(
                        ref_id=str(chunk.get("ref_id", "")),
                        title=chunk.get("title"),
                        terms=chunk.get("terms"),
                        content=str(chunk.get("content", "")),
                    )
                )

    return passages
