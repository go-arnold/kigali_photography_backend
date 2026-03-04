"""
RAG Models
==========
KnowledgeDocument — source documents (packages, policies, scripts, etc.)
KnowledgeChunk    — searchable chunks with embeddings (pgvector)
ConversationSummary — compressed context for long conversations (token saver)

Token optimization:
- We store embeddings in pgvector and retrieve only top-K chunks
- ConversationSummary replaces old messages beyond the sliding window
  keeping context without re-sending full history to Claude every turn
"""

from django.db import models
from django.utils import timezone


class DocumentCategory(models.TextChoices):
    PACKAGE = "package", "Package & Pricing"
    POLICY = "policy", "Booking Policy"
    SCRIPT = "script", "Response Script"
    OBJECTION = "objection", "Objection Handling"
    FAQ = "faq", "FAQ"
    LOCATION = "location", "Studio Location & Hours"
    BILINGUAL = "bilingual", "Bilingual Phrases"
    SUCCESS_PATTERN = "success_pattern", "Success Pattern"


class KnowledgeDocument(models.Model):
    """
    A source document in the knowledge base.
    Humans manage these via the admin panel.
    """

    title = models.CharField(max_length=200)
    category = models.CharField(
        max_length=30, choices=DocumentCategory.choices, db_index=True
    )
    content = models.TextField()
    language = models.CharField(max_length=5, default="en", help_text="en | rw | both")
    is_active = models.BooleanField(default=True)
    version = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "title"]

    def __str__(self):
        return f"[{self.category}] {self.title}"


class KnowledgeChunk(models.Model):
    """
    A searchable chunk of a KnowledgeDocument.
    Chunks are ~200-400 tokens each for optimal retrieval.

    Note: pgvector extension must be enabled in Postgres.
    Embedding is stored as a simple JSON list of floats for portability.
    Swap to pgvector VectorField when ready for production scale.
    """

    document = models.ForeignKey(
        KnowledgeDocument, on_delete=models.CASCADE, related_name="chunks"
    )
    chunk_index = models.PositiveSmallIntegerField(help_text="Order within document")
    content = models.TextField()

    # Embedding stored as JSON array — swap to pgvector in production
    # from pgvector.django import VectorField
    # embedding = VectorField(dimensions=1536)
    embedding = models.JSONField(
        null=True,
        blank=True,
        help_text="Float list from embedding model (text-embedding-3-small)",
    )
    embedding_model = models.CharField(max_length=60, blank=True)
    token_count = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document", "chunk_index"]
        unique_together = [("document", "chunk_index")]

    def __str__(self):
        return f"{self.document.title} chunk {self.chunk_index}"


class ConversationSummary(models.Model):
    """
    Compressed summary of older messages in a conversation.

    Token optimization strategy:
    When a conversation exceeds 10 messages, older messages are summarized
    into this model. Claude only receives:
      1. This summary (instead of 10+ old messages)
      2. Last 5 messages (full)
      3. RAG context (3 chunks)

    This can reduce input tokens by 60-70% in long conversations.
    """

    from apps.conversations.models import Conversation

    conversation = models.OneToOneField(
        "conversations.Conversation", on_delete=models.CASCADE, related_name="summary"
    )
    summary_text = models.TextField()
    messages_summarized = models.PositiveSmallIntegerField(
        help_text="Number of messages compressed into this summary"
    )
    tokens_saved = models.PositiveIntegerField(
        default=0, help_text="Estimated tokens saved by summarization"
    )
    last_updated = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Summary for {self.conversation} ({self.messages_summarized} msgs)"
