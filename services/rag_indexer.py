"""
RAG Indexer Service
====================
Splits KnowledgeDocuments into chunks and (optionally) generates embeddings.

Chunking strategy:
  - Target: 250-350 tokens per chunk (sweet spot for retrieval precision)
  - Split on paragraph boundaries first, then sentences
  - Overlap: none (documents are short, overlap adds noise here)

Embedding:
  - Optional: only if OPENAI_API_KEY is set
  - Model: text-embedding-3-small (cheapest, sufficient for this domain)
  - Falls back to keyword-only search if embeddings unavailable

Called by:
  - Management command: python manage.py index_knowledge_base
  - Signal: auto-reindex when KnowledgeDocument is saved
"""
import logging
import os
import re

from utils.tokens import estimate_tokens

logger = logging.getLogger(__name__)

_TARGET_CHUNK_TOKENS = 300
_MAX_CHUNK_TOKENS = 400


def index_document(document) -> int:
    """
    Chunk and index a single KnowledgeDocument.
    Deletes existing chunks first (full reindex).
    Returns number of chunks created.
    """
    from apps.rag.models import KnowledgeChunk

    KnowledgeChunk.objects.filter(document=document).delete()

    chunks = _split_into_chunks(document.content)
    created = 0

    for i, chunk_text in enumerate(chunks):
        embedding = _get_embedding(chunk_text)
        KnowledgeChunk.objects.create(
            document=document,
            chunk_index=i,
            content=chunk_text,
            embedding=embedding,
            embedding_model="text-embedding-3-small" if embedding else "",
            token_count=estimate_tokens(chunk_text),
        )
        created += 1

    logger.info(
        "Indexed '%s' → %s chunks (category=%s)",
        document.title, created, document.category,
    )
    return created


def index_all_documents(force: bool = False) -> dict:
    """
    Index all active KnowledgeDocuments.
    force=True: reindex even if chunks already exist.
    Returns summary dict.
    """
    from apps.rag.models import KnowledgeDocument, KnowledgeChunk

    docs = KnowledgeDocument.objects.filter(is_active=True)
    total_chunks = 0
    indexed_docs = 0

    for doc in docs:
        has_chunks = KnowledgeChunk.objects.filter(document=doc).exists()
        if has_chunks and not force:
            logger.debug("Skipping '%s' — already indexed", doc.title)
            continue
        total_chunks += index_document(doc)
        indexed_docs += 1

    return {
        "documents_indexed": indexed_docs,
        "chunks_created": total_chunks,
        "embeddings": bool(os.environ.get("OPENAI_API_KEY")),
    }


def _split_into_chunks(text: str) -> list[str]:
    """
    Split document text into chunks targeting _TARGET_CHUNK_TOKENS.

    Strategy:
    1. Split on double newline (paragraphs)
    2. If a paragraph is too large, split on single newline
    3. If still too large, split on sentence boundary
    4. Merge small adjacent chunks to reach target size
    """
    # Clean whitespace
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    paragraphs = text.split("\n\n")

    raw_segments = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if estimate_tokens(para) <= _MAX_CHUNK_TOKENS:
            raw_segments.append(para)
        else:
            # Split large paragraph into sentences
            sentences = re.split(r"(?<=[.!?])\s+", para)
            raw_segments.extend(s.strip() for s in sentences if s.strip())

    # Merge small segments into target-size chunks
    chunks = []
    current = []
    current_tokens = 0

    for seg in raw_segments:
        seg_tokens = estimate_tokens(seg)
        if current_tokens + seg_tokens > _TARGET_CHUNK_TOKENS and current:
            chunks.append("\n\n".join(current))
            current = [seg]
            current_tokens = seg_tokens
        else:
            current.append(seg)
            current_tokens += seg_tokens

    if current:
        chunks.append("\n\n".join(current))

    return [c for c in chunks if c.strip()]


def _get_embedding(text: str) -> list | None:
    """
    Get embedding vector for text.
    Returns None if OpenAI key not configured — graceful degradation.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        import httpx
        response = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"input": text[:512], "model": "text-embedding-3-small"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]
    except Exception as exc:
        logger.debug("Embedding failed (non-critical): %s", exc)
        return None