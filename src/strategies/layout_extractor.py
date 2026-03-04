"""Layout-aware extraction strategy.

This implementation prefers Docling when available, but is written so the
system degrades gracefully if Docling is not installed by raising a clear
configuration error.
"""

from __future__ import annotations

from typing import List, Tuple

from ..models.document_profile import DocumentProfile
from ..models.extracted_document import ExtractedDocument, Table, TableCell, TextBlock
from ..utils.errors import ConfigError, ExtractionError
from ..utils.logging import get_logger
from .base import BaseExtractor


logger = get_logger(__name__)


class LayoutExtractor(BaseExtractor):
    """Medium-cost layout-aware extraction strategy."""

    def extract(self, document_path: str, profile: DocumentProfile) -> Tuple[ExtractedDocument, float]:
        try:
            from docling.document_converter import DocumentConverter  # type: ignore[import-untyped]
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(
                "LayoutExtractor requires the 'docling' package. "
                "Install it via 'pip install docling'."
            ) from exc

        try:
            converter = DocumentConverter()
            doc = converter.convert(document_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("LayoutExtractor failed during conversion", document_path=document_path)
            raise ExtractionError(f"LayoutExtractor failed for {document_path}") from exc

        # Normalize DoclingDocument into ExtractedDocument
        text_blocks: List[TextBlock] = []
        tables: List[Table] = []
        figures = []

        num_pages = max(1, len(getattr(doc, "pages", []) or [None]))

        # Use Docling's markdown export as a high-fidelity text representation.
        markdown_text: str = doc.export_to_markdown()
        text_blocks.append(
            TextBlock(
                id="docling-markdown-0",
                text=markdown_text,
                page_number=1,
                bbox=None,
                reading_order=0,
            )
        )

        # Attempt to adapt Docling table structures when available.
        doc_tables = getattr(doc, "tables", []) or []
        table_id = 0
        for t in doc_tables:
            # Best-effort extraction of headers and rows
            headers: List[str] = []
            rows: List[List[str]] = []

            try:
                if hasattr(t, "to_markdown"):
                    # Fallback: parse markdown table into headers and rows
                    md = t.to_markdown()
                    lines = [ln.strip() for ln in md.splitlines() if ln.strip()]
                    if lines:
                        headers = [h.strip() for h in lines[0].split("|") if h.strip()]
                        for ln in lines[2:]:
                            cols = [c.strip() for c in ln.split("|")]
                            rows.append(cols)
                elif hasattr(t, "cells"):
                    # Generic cell-based API
                    headers = [str(h) for h in getattr(t, "header", [])]
                    for row in getattr(t, "cells", []):
                        rows.append([str(c) for c in row])
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to adapt Docling table", extra={"error": repr(exc)})
                continue

            cells: List[TableCell] = []
            for r_idx, row in enumerate(rows):
                for c_idx, value in enumerate(row):
                    text = value.strip()
                    if not text:
                        continue
                    cells.append(
                        TableCell(
                            row_index=r_idx,
                            col_index=c_idx,
                            text=text,
                            bbox=None,
                        )
                    )

            page_number = int(getattr(t, "page_no", 1))
            tables.append(
                Table(
                    id=f"docling-table-{table_id}",
                    page_number=page_number,
                    caption=getattr(t, "caption", None),
                    headers=headers,
                    cells=cells,
                )
            )
            table_id += 1

        confidence_score = 0.9 if tables or markdown_text else 0.8

        logger.info(
            "LayoutExtractor completed",
            extra={
                "document_path": document_path,
                "num_pages": num_pages,
                "confidence_score": confidence_score,
            },
        )

        extracted = ExtractedDocument(
            document_id=profile.doc_id,
            num_pages=num_pages,
            text_blocks=text_blocks,
            tables=tables,
            figures=figures,
            metadata={},
        )

        return extracted, confidence_score

