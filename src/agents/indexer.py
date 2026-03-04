"""PageIndex tree builder."""

from __future__ import annotations

from typing import List

from ..models.extracted_document import ExtractedDocument
from ..models.pageindex import PageIndex, PageIndexSection
from ..utils.errors import IndexingError
from ..utils.logging import get_logger


logger = get_logger(__name__)


class PageIndexBuilder:
    """Construct a hierarchical PageIndex from an ExtractedDocument."""

    def build(self, document: ExtractedDocument) -> PageIndex:
        if document.num_pages < 1:
            raise IndexingError("Cannot build PageIndex for document with zero pages.")

        text_concat = " ".join(block.text for block in document.text_blocks)
        summary = self._summarize(text_concat)

        root = PageIndexSection(
            id=f"{document.document_id}-root",
            title="Document",
            page_start=1,
            page_end=document.num_pages,
            key_entities=[],
            summary=summary,
            data_types_present=["tables"] if document.tables else [],
            children=[],
        )

        page_index = PageIndex(document_id=document.document_id, root_sections=[root])

        logger.info(
            "PageIndex built",
            extra={
                "document_id": document.document_id,
                "sections": 1,
            },
        )

        return page_index

    @staticmethod
    def _summarize(text: str, max_sentences: int = 3) -> str:
        if not text:
            return ""
        sentences: List[str] = []
        for part in text.split("."):
            candidate = part.strip()
            if candidate:
                sentences.append(candidate)
            if len(sentences) >= max_sentences:
                break
        return ". ".join(sentences) + (". " if sentences else "")

