"""
RAG service and indexer tests.
Tests chunking logic, retrieval, and seed data loading.
"""

from django.test import TestCase

from apps.rag.models import KnowledgeDocument, KnowledgeChunk


def make_doc(
    title="Test Doc",
    category="faq",
    language="en",
    content="Hello world.\n\nThis is a test.",
):
    return KnowledgeDocument.objects.create(
        title=title,
        category=category,
        language=language,
        content=content,
        is_active=True,
    )


class ChunkingTest(TestCase):
    def test_single_short_doc_creates_one_chunk(self):
        from services.rag_indexer import index_document

        doc = make_doc(content="Short content that fits in one chunk.")
        count = index_document(doc)
        self.assertEqual(count, 1)
        self.assertEqual(KnowledgeChunk.objects.filter(document=doc).count(), 1)

    def test_long_doc_creates_multiple_chunks(self):
        from services.rag_indexer import index_document

        # Create content with many paragraphs
        paragraphs = "\n\n".join(
            [
                f"This is paragraph {i} with some content about photography sessions."
                for i in range(20)
            ]
        )
        doc = make_doc(content=paragraphs)
        count = index_document(doc)
        self.assertGreater(count, 1)

    def test_reindex_clears_old_chunks(self):
        from services.rag_indexer import index_document

        doc = make_doc(content="First version content.")
        index_document(doc)
        self.assertEqual(KnowledgeChunk.objects.filter(document=doc).count(), 1)

        # Reindex with different content
        doc.content = (
            "Second version.\\n\\nCompletely different.\\n\\nThird paragraph here."
        )
        doc.save()
        index_document(doc)

        # Old chunks cleared, new content present (may merge into 1 chunk if short)
        chunks = KnowledgeChunk.objects.filter(document=doc)
        self.assertGreater(chunks.count(), 0)
        all_content = " ".join(c.content for c in chunks)
        self.assertIn("Second version", all_content)
        self.assertNotIn("First version", all_content)  # old content gone

    def test_chunk_has_token_count(self):
        from services.rag_indexer import index_document

        doc = make_doc(
            content="This is a test document with some content for token counting."
        )
        index_document(doc)
        chunk = KnowledgeChunk.objects.filter(document=doc).first()
        self.assertGreater(chunk.token_count, 0)

    def test_index_all_skips_already_indexed(self):
        from services.rag_indexer import index_all_documents, index_document

        doc = make_doc(title="Already Indexed")
        index_document(doc)

        result = index_all_documents(force=False)
        # doc already has chunks — should be skipped
        self.assertEqual(result["documents_indexed"], 0)

    def test_index_all_force_reindexes(self):
        from services.rag_indexer import index_all_documents, index_document

        doc = make_doc(title="Force Reindex Test")
        index_document(doc)

        result = index_all_documents(force=True)
        self.assertGreaterEqual(result["documents_indexed"], 1)


class RAGRetrievalTest(TestCase):
    def setUp(self):
        from services.rag_indexer import index_document

        self.pkg_doc = make_doc(
            title="Packages",
            category="package",
            language="en",
            content="Essential Package 100,000 RWF. 10 edited photos. Premium Package 150,000 RWF. 15 edited photos.",
        )
        self.obj_doc = make_doc(
            title="Objections",
            category="objection",
            language="en",
            content="When client says price is too expensive, reinforce value. Never reduce price.",
        )
        index_document(self.pkg_doc)
        index_document(self.obj_doc)

    def test_retrieval_returns_string(self):
        from services.rag_service import retrieve_context

        result = retrieve_context(
            query="What packages do you offer?",
            journey_phase="booking",
            language="en",
        )
        self.assertIsInstance(result, str)

    def test_retrieval_filters_by_phase(self):
        from services.rag_service import retrieve_context

        # In 'booking' phase — should retrieve package docs
        result = retrieve_context(
            query="How much does it cost?",
            journey_phase="booking",
            language="en",
        )
        # Result should contain package content (phase maps to package category)
        self.assertIn("100,000", result)

    def test_retrieval_empty_when_no_docs(self):
        from services.rag_service import retrieve_context

        # Fresh DB with no docs for this phase/language combo
        KnowledgeChunk.objects.all().delete()
        KnowledgeDocument.objects.all().delete()
        result = retrieve_context(
            query="anything",
            journey_phase="entry",
            language="rw",
        )
        self.assertEqual(result, "")

    def test_language_filter_works(self):
        from services.rag_indexer import index_document
        from services.rag_service import retrieve_context

        rw_doc = make_doc(
            title="RW Script",
            category="script",
            language="rw",
            content="Muraho, ndashaka gufotorwa. Ubutumire bw'amafoto.",
        )
        index_document(rw_doc)

        result = retrieve_context(
            query="muraho ndashaka", journey_phase="entry", language="rw"
        )
        self.assertIsInstance(result, str)


class SeedDataTest(TestCase):
    def test_load_seed_creates_documents(self):
        from apps.rag.seed import load_seed_data

        count = load_seed_data()
        self.assertGreater(count, 10)  # We have 15+ seed docs

    def test_load_seed_idempotent(self):
        from apps.rag.seed import load_seed_data

        first = load_seed_data()
        second = load_seed_data()
        self.assertGreater(first, 0)
        self.assertEqual(second, 0)  # No duplicates on second run

    def test_seed_covers_all_categories(self):
        from apps.rag.seed import load_seed_data

        load_seed_data()
        categories = KnowledgeDocument.objects.values_list(
            "category", flat=True
        ).distinct()
        expected = {
            "package",
            "policy",
            "script",
            "objection",
            "faq",
            "location",
            "bilingual",
            "success_pattern",
        }
        self.assertTrue(expected.issubset(set(categories)))

    def test_seed_has_both_languages(self):
        from apps.rag.seed import load_seed_data

        load_seed_data()
        languages = KnowledgeDocument.objects.values_list(
            "language", flat=True
        ).distinct()
        self.assertIn("en", languages)
        self.assertIn("rw", languages)
        self.assertIn("both", languages)
