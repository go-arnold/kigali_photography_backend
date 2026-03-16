"""
Auto-reindex KnowledgeDocument when saved via admin.
Keeps chunks in sync without manual management command runs.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="rag.KnowledgeDocument")
def reindex_on_save(sender, instance, created, **kwargs):
    """Reindex document chunks whenever content is saved."""
    try:
        from services.rag_indexer import index_document
        count = index_document(instance)
        logger.info(
            "Auto-reindexed '%s' → %s chunks", instance.title, count
        )
    except Exception as exc:
        logger.error("Auto-reindex failed for '%s': %s", instance.title, exc)
