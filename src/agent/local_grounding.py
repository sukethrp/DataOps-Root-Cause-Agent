"""Offline grounding over the local knowledge/ corpus."""

from __future__ import annotations

import re
from pathlib import Path

from .retrieval import Citation, Passage, RetrievalResult

DEFAULT_KNOWLEDGE_ROOT = Path("knowledge")
_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def retrieve_local(
    query: str,
    *,
    knowledge_root: Path | str = DEFAULT_KNOWLEDGE_ROOT,
    max_passages: int = 8,
) -> RetrievalResult:
    """Keyword retrieval over markdown files when Foundry IQ is unavailable."""
    root = Path(knowledge_root)
    if not root.is_dir():
        msg = f"Knowledge root not found: {root}"
        raise FileNotFoundError(msg)

    query_tokens = _tokenize(query)
    scored: list[tuple[float, Path, str]] = []

    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        score = _score_text(text, query_tokens)
        if score > 0:
            scored.append((score, path, text))

    scored.sort(key=lambda item: item[0], reverse=True)
    passages: list[Passage] = []
    citations: list[Citation] = []

    for index, (_score, path, text) in enumerate(scored[:max_passages]):
        ref_id = str(index)
        doc_key = str(path.relative_to(root))
        excerpt = _best_excerpt(text, query_tokens)
        passages.append(
            Passage(
                ref_id=ref_id,
                title=doc_key,
                content=excerpt,
            )
        )
        citations.append(
            Citation(
                ref_id=ref_id,
                doc_key=doc_key,
                source_type="local",
            )
        )

    return RetrievalResult(passages=passages, citations=citations)


def _tokenize(text: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(text.lower()) if len(token) > 2}


def _score_text(text: str, query_tokens: set[str]) -> float:
    if not query_tokens:
        return 0.0
    body_tokens = _tokenize(text)
    overlap = query_tokens & body_tokens
    return float(len(overlap))


def _best_excerpt(text: str, query_tokens: set[str], *, max_chars: int = 900) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return text[:max_chars]

    best = paragraphs[0]
    best_score = -1.0
    for paragraph in paragraphs:
        score = _score_text(paragraph, query_tokens)
        if score > best_score:
            best_score = score
            best = paragraph

    if len(best) <= max_chars:
        return best
    return best[: max_chars - 3] + "..."
