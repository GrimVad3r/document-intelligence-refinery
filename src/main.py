"""CLI entrypoint for the Document Intelligence Refinery."""

from __future__ import annotations

import argparse
import os

from .agents.chunker import ChunkingEngine
from .agents.extractor import ExtractionRouter
from .agents.indexer import PageIndexBuilder
from .agents.triage import triage_document
from .data.fact_table import FactTableExtractor
from .data.vector_store import LocalVectorStore
from .utils.logging import get_logger


logger = get_logger(__name__)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run_pipeline(document_path: str, doc_id: str, sqlite_path: str | None = None) -> None:
    """Run triage -> extraction -> chunking -> indexing for a single document."""

    profile = triage_document(doc_id=doc_id, document_path=document_path)
    router = ExtractionRouter()
    extracted = router.extract(document_path=document_path, profile=profile)

    chunker = ChunkingEngine()
    ldus = chunker.chunk(extracted)

    index_builder = PageIndexBuilder()
    page_index = index_builder.build(extracted)
    pageindex_path = index_builder.persist(page_index)

    vector_store = LocalVectorStore()
    vector_store.build(ldus)
    vector_manifest_path = vector_store.persist_manifest(
        document_id=doc_id,
        output_dir=os.path.join(PROJECT_ROOT, ".refinery", "vectorstore"),
        ldus=ldus,
    )

    fact_rows_inserted = 0
    if sqlite_path:
        fact_rows_inserted = FactTableExtractor().ingest(extracted, sqlite_path)

    logger.info(
        "Pipeline run completed",
        extra={
            "doc_id": doc_id,
            "ldu_count": len(ldus),
            "pages": extracted.num_pages,
            "root_sections": len(page_index.root_sections),
            "pageindex_path": pageindex_path,
            "vector_manifest_path": vector_manifest_path,
            "fact_rows_inserted": fact_rows_inserted,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Document Intelligence Refinery pipeline.")
    parser.add_argument("document", help="Path to the input PDF document.")
    parser.add_argument(
        "--doc-id",
        help="Stable identifier for the document (defaults to filename without extension).",
    )
    parser.add_argument(
        "--sqlite-path",
        help="Optional SQLite path for fact-table ingestion.",
    )
    args = parser.parse_args()

    document_path = os.path.abspath(args.document)
    doc_id = args.doc_id or os.path.splitext(os.path.basename(document_path))[0]
    sqlite_path = os.path.abspath(args.sqlite_path) if args.sqlite_path else None

    run_pipeline(document_path=document_path, doc_id=doc_id, sqlite_path=sqlite_path)


if __name__ == "__main__":
    main()
