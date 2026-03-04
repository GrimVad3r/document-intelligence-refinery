"""Tests for data-layer ingestion and audit utilities."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.agents.audit_agent import AuditAgent
from src.data.fact_table import FactTableExtractor
from src.data.vector_store import LocalVectorStore
from src.models.extracted_document import ExtractedDocument, Table, TableCell, TextBlock
from src.models.ldu import LDU, LDUType
from src.models.provenance import BoundingBox, ProvenanceChain, ProvenanceRecord


def _sample_document() -> ExtractedDocument:
    return ExtractedDocument(
        document_id="doc-1",
        num_pages=1,
        text_blocks=[
            TextBlock(
                id="b-1",
                text="Revenue for Q3 was 4.2B birr.",
                page_number=1,
                bbox=BoundingBox(page_number=1, x0=0, y0=0, x1=10, y1=10),
                reading_order=0,
            )
        ],
        tables=[
            Table(
                id="t-1",
                page_number=1,
                caption=None,
                headers=["metric", "value"],
                cells=[
                    TableCell(row_index=0, col_index=0, text="revenue", bbox=None),
                    TableCell(row_index=0, col_index=1, text="4.2B", bbox=None),
                ],
            )
        ],
        figures=[],
        metadata={},
    )


def _sample_ldu() -> LDU:
    prov = ProvenanceChain(
        records=[
            ProvenanceRecord(
                document_id="doc-1",
                page_number=1,
                bbox=BoundingBox(page_number=1, x0=0, y0=0, x1=10, y1=10),
                content_hash="abc",
                description="sample",
            )
        ]
    )
    return LDU(
        id="ldu-1",
        content="Revenue for Q3 was 4.2B birr.",
        ldu_type=LDUType.PARAGRAPH,
        page_refs=[1],
        parent_section_id=None,
        token_count=6,
        content_hash="abc",
        provenance=prov,
    )


def test_fact_table_ingestion_writes_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "facts.db"
    inserted = FactTableExtractor().ingest(_sample_document(), str(db_path))
    assert inserted == 2

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM extracted_facts")
    count = cur.fetchone()[0]
    conn.close()
    assert count == 2


def test_vector_store_and_audit_agent() -> None:
    ldu = _sample_ldu()
    store = LocalVectorStore()
    store.build([ldu])
    hits = store.search("Q3 revenue", top_k=1)
    assert len(hits) == 1
    assert hits[0].ldu.id == "ldu-1"

    audit = AuditAgent().verify_claim("Revenue for Q3 was 4.2B", [ldu])
    assert audit.verdict == "verified"
    assert audit.provenance.records

