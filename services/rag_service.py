"""
RAG Service
============
Retrieves relevant knowledge base chunks before each Claude call.

Strategy:
  - No external vector DB required — uses cosine similarity on stored embeddings
  - Falls back to keyword search if embeddings not yet generated
  - Returns top-K chunks formatted for system prompt injection
  - Category filtering: pulls relevant docs for current journey phase

Embedding model: text-embedding-3-small (cheapest OpenAI embedding)
Note: We use Anthropic for chat but OpenAI for embeddings — cheaper for this use case.
Swap to any embedding model without changing the interface.
"""

import json
import logging
import math
from typing import Optional

from django.db.models import Q

logger = logging.getLogger(__name__)

_TOP_K = 3  # Max chunks returned per query


#  Phase-to-category mapping
# Pulls the right type of knowledge for the current journey phase.

_PHASE_CATEGORIES = {
    "entry": ["script", "bilingual", "faq"],
    "booking": ["package", "policy", "script"],
    "sales_resistance": ["objection", "script", "package"],
    "preparation": ["faq", "location", "script"],
    "delivery": ["faq", "script"],
    "feedback": ["script"],
}


def retrieve_context(
    query: str,
    journey_phase: str,
    language: str = "en",
    top_k: int = _TOP_K,
) -> str:
    """
    Main retrieval function. Returns a formatted string ready for
    injection into the system prompt.

    Args:
        query:          The client's message (used for semantic search)
        journey_phase:  Current phase — filters to relevant doc categories
        language:       'en' or 'rw' — prefers matching language docs
        top_k:          Max chunks to return

    Returns:
        Formatted string, or empty string if nothing retrieved.
    """
    from apps.rag.models import KnowledgeChunk

    categories = _PHASE_CATEGORIES.get(journey_phase, ["faq", "script"])

    # Base queryset: active docs in relevant categories
    qs = KnowledgeChunk.objects.filter(
        document__is_active=True,
        document__category__in=categories,
    ).select_related("document")

    # Language preference: prefer exact match, fall back to "both"
    qs = qs.filter(Q(document__language=language) | Q(document__language="both"))

    if not qs.exists():
        logger.debug(
            "No RAG chunks found for phase=%s lang=%s", journey_phase, language
        )
        return ""

    chunks = list(qs)

    query_embedding = _get_query_embedding(query)
    if query_embedding:
        chunks = _rank_by_similarity(chunks, query_embedding, top_k)
    else:
        # Fallback: keyword relevance
        chunks = _rank_by_keywords(chunks, query, top_k)

    if not chunks:
        return ""

    # Format for system prompt injection
    lines = []
    for chunk in chunks[:top_k]:
        lines.append(f"[{chunk.document.category.upper()}] {chunk.content.strip()}")

    return "\n\n".join(lines)


def get_approved_bonus_options() -> str:
    """
    Return the approved bonus options as formatted text.
    Used when heat engine suggests a bonus offer.
    """
    from apps.rag.models import KnowledgeDocument, DocumentCategory

    docs = KnowledgeDocument.objects.filter(
        category=DocumentCategory.PACKAGE,
        is_active=True,
        title__icontains="bonus",
    )
    if not docs.exists():
        return ""
    return "\n".join(d.content for d in docs)


def _get_query_embedding(text: str) -> Optional[list]:
    """
    Get embedding for query text.
    Returns None if embedding service unavailable — graceful degradation.
    """
    # Only attempt if OpenAI key configured
    import os

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        return None

    try:
        import httpx

        response = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {openai_key}"},
            json={"input": text[:500], "model": "text-embedding-3-small"},
            timeout=5,
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]
    except Exception as exc:
        logger.debug("Embedding call failed (non-critical): %s", exc)
        return None


def _cosine_similarity(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _rank_by_similarity(chunks: list, query_embedding: list, top_k: int) -> list:
    scored = []
    for chunk in chunks:
        if chunk.embedding:
            try:
                emb = (
                    chunk.embedding
                    if isinstance(chunk.embedding, list)
                    else json.loads(chunk.embedding)
                )
                score = _cosine_similarity(query_embedding, emb)
                scored.append((score, chunk))
            except Exception:
                scored.append((0.0, chunk))
        else:
            scored.append((0.0, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def _rank_by_keywords(chunks: list, query: str, top_k: int) -> list:
    """Simple keyword overlap scoring when embeddings unavailable."""
    query_words = set(query.lower().split())
    scored = []
    for chunk in chunks:
        chunk_words = set(chunk.content.lower().split())
        overlap = len(query_words & chunk_words)
        scored.append((overlap, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]
