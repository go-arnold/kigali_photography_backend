"""
Management command: index (or reindex) all knowledge base documents.

Usage:
  python manage.py index_knowledge_base           # index new/unindexed docs
  python manage.py index_knowledge_base --force   # reindex everything
  python manage.py index_knowledge_base --seed    # load seed data first, then index
"""

from django.core.management.base import BaseCommand
from services.rag_indexer import index_all_documents


class Command(BaseCommand):
    help = "Index knowledge base documents into searchable chunks"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Reindex all documents, even if already chunked",
        )
        parser.add_argument(
            "--seed",
            action="store_true",
            help="Load seed knowledge base data before indexing",
        )

    def handle(self, *args, **options):
        if options["seed"]:
            self.stdout.write("Loading seed knowledge base...")
            from apps.rag.seed import load_seed_data

            count = load_seed_data()
            self.stdout.write(self.style.SUCCESS(f"  Loaded {count} documents"))

        self.stdout.write("Indexing knowledge base...")
        result = index_all_documents(force=options["force"])

        self.stdout.write(
            self.style.SUCCESS(
                f"  ✓ {result['documents_indexed']} documents → {result['chunks_created']} chunks"
                f" | embeddings={'ON' if result['embeddings'] else 'OFF (keyword fallback)'}"
            )
        )
