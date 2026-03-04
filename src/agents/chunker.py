"""Semantic chunking engine producing Logical Document Units (LDUs)."""

from __future__ import annotations

import hashlib
from typing import List

from ..models.extracted_document import ExtractedDocument
from ..models.ldu import LDU, LDUType
from ..models.provenance import ProvenanceChain, ProvenanceRecord
from ..utils.errors import ChunkingError
from ..utils.logging import get_logger


logger = get_logger(__name__)


def _hash_content(content: str) -> str:
    """Return a stable hash for content, used in provenance."""

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ChunkValidator:
    """Validator enforcing core chunking invariants."""

    @staticmethod
    def validate(ldus: List[LDU]) -> None:
        for ldu in ldus:
            if not ldu.content.strip():
                raise ChunkingError(f"Empty content detected in LDU {ldu.id}")


class ChunkingEngine:
    """Convert an `ExtractedDocument` into a list of LDUs."""

    def chunk(self, document: ExtractedDocument) -> List[LDU]:
        ldus: List[LDU] = []
        ldu_id = 0

        # Paragraph-like LDUs from text blocks.
        for block in document.text_blocks:
            content = block.text.strip()
            if not content:
                continue
            content_hash = _hash_content(content)
            provenance = ProvenanceChain(
                records=[
                    ProvenanceRecord(
                        document_id=document.document_id,
                        page_number=block.page_number,
                        bbox=block.bbox,
                        content_hash=content_hash,
                        description="Text block",
                    )
                ]
            )
            ldus.append(
                LDU(
                    id=f"ldu-{ldu_id}",
                    content=content,
                    ldu_type=LDUType.PARAGRAPH,
                    page_refs=[block.page_number],
                    parent_section_id=None,
                    token_count=len(content.split()),
                    content_hash=content_hash,
                    provenance=provenance,
                )
            )
            ldu_id += 1

        # Table LDUs: keep each table as a single unit to avoid splitting header from cells.
        for table in document.tables:
            rows: List[str] = []
            if table.headers:
                rows.append(" | ".join(table.headers))
            by_row: dict[int, dict[int, str]] = {}
            for cell in table.cells:
                row = by_row.setdefault(cell.row_index, {})
                row[cell.col_index] = cell.text
            for r_idx in sorted(by_row):
                max_col = max(by_row[r_idx].keys(), default=-1)
                cols = [by_row[r_idx].get(c_idx, "") for c_idx in range(max_col + 1)]
                rows.append(" | ".join(cols))
            content = "\n".join(rows).strip()
            if not content:
                continue
            content_hash = _hash_content(content)
            provenance = ProvenanceChain(
                records=[
                    ProvenanceRecord(
                        document_id=document.document_id,
                        page_number=table.page_number,
                        bbox=None,
                        content_hash=content_hash,
                        description="Table",
                    )
                ]
            )
            ldus.append(
                LDU(
                    id=f"ldu-{ldu_id}",
                    content=content,
                    ldu_type=LDUType.TABLE,
                    page_refs=[table.page_number],
                    parent_section_id=None,
                    token_count=len(content.split()),
                    content_hash=content_hash,
                    provenance=provenance,
                )
            )
            ldu_id += 1

        ChunkValidator.validate(ldus)

        logger.info(
            "Chunking completed",
            extra={
                "document_id": document.document_id,
                "ldu_count": len(ldus),
            },
        )

        return ldus

