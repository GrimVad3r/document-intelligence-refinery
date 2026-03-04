"""CLI entrypoint for the Document Intelligence Refinery."""

from __future__ import annotations

import argparse
import os

from .agents.chunker import ChunkingEngine
from .agents.extractor import ExtractionRouter
from .agents.indexer import PageIndexBuilder
from .agents.query_agent import QueryAgent
from .agents.triage import triage_document
from .utils.logging import get_logger


logger = get_logger(__name__)


def run_pipeline(document_path: str, doc_id: str) -> None:
    """Run triage → extraction → chunking → indexing for a single document."""

    profile = triage_document(doc_id=doc_id, document_path=document_path)
    router = ExtractionRouter()
    extracted = router.extract(document_path=document_path, profile=profile)

    chunker = ChunkingEngine()
    ldus = chunker.chunk(extracted)

    index_builder = PageIndexBuilder()
    page_index = index_builder.build(extracted)

    logger.info(
        "Pipeline run completed",
        extra={
            "doc_id": doc_id,
            "ldu_count": len(ldus),
            "pages": extracted.num_pages,
            "root_sections": len(page_index.root_sections),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Document Intelligence Refinery pipeline.")
    parser.add_argument("document", help="Path to the input PDF document.")
    parser.add_argument(
        "--doc-id",
        help="Stable identifier for the document (defaults to filename without extension).",
    )
    args = parser.parse_args()

    document_path = os.path.abspath(args.document)
    doc_id = args.doc_id or os.path.splitext(os.path.basename(document_path))[0]

    run_pipeline(document_path=document_path, doc_id=doc_id)


if __name__ == "__main__":
    main()

