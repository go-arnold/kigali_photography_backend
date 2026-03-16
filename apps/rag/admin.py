"""
RAG Admin — Knowledge base management for studio staff.
Staff can add, edit, and reindex documents without touching code.
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import KnowledgeDocument, KnowledgeChunk, ConversationSummary


class KnowledgeChunkInline(admin.TabularInline):
    model = KnowledgeChunk
    extra = 0
    readonly_fields = (
        "chunk_index",
        "content",
        "token_count",
        "embedding_model",
        "has_embedding",
    )
    fields = readonly_fields
    can_delete = False
    max_num = 0

    @admin.display(description="Embedding?", boolean=True)
    def has_embedding(self, obj):
        return bool(obj.embedding)


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "language",
        "is_active",
        "chunk_count",
        "version",
        "updated_at",
    )
    list_filter = ("category", "language", "is_active")
    search_fields = ("title", "content")
    readonly_fields = ("created_at", "updated_at", "chunk_count")
    inlines = [KnowledgeChunkInline]
    actions = ["activate", "deactivate", "reindex"]

    fieldsets = (
        (
            "Document",
            {"fields": ("title", "category", "language", "is_active", "version")},
        ),
        ("Content", {"fields": ("content",)}),
        (
            "Meta",
            {
                "fields": ("created_at", "updated_at", "chunk_count"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Chunks")
    def chunk_count(self, obj):
        count = obj.chunks.count()
        color = "green" if count > 0 else "red"
        return format_html('<span style="color:{}">{}</span>', color, count)

    @admin.action(description="✓ Activate selected documents")
    def activate(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"Activated {queryset.count()} documents.")

    @admin.action(description="✗ Deactivate selected documents")
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"Deactivated {queryset.count()} documents.")

    @admin.action(description="🔄 Reindex selected documents")
    def reindex(self, request, queryset):
        from services.rag_indexer import index_document

        total = 0
        for doc in queryset:
            total += index_document(doc)
        self.message_user(
            request,
            f"Reindexed {queryset.count()} documents → {total} chunks created.",
        )


@admin.register(ConversationSummary)
class ConversationSummaryAdmin(admin.ModelAdmin):
    list_display = (
        "conversation",
        "messages_summarized",
        "tokens_saved",
        "last_updated",
    )
    readonly_fields = (
        "conversation",
        "summary_text",
        "messages_summarized",
        "tokens_saved",
        "last_updated",
        "created_at",
    )
    search_fields = ("conversation__client__name", "conversation__client__wa_number")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
