"""Tests for PageIndex serialization and query routing orchestration."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.agents.indexer import PAGEINDEX_SCHEMA_VERSION, PageIndexBuilder
from src.agents.query_agent import QueryAgent
from src.models.extracted_document import ExtractedDocument, TextBlock
from src.models.ldu import LDU, LDUType
from src.models.pageindex import PageIndex, PageIndexSection
from src.models.provenance import BoundingBox, ProvenanceChain, ProvenanceRecord


def _sample_extracted_document() -> ExtractedDocument:
    return ExtractedDocument(
        document_id="doc-idx",
        num_pages=2,
        text_blocks=[
            TextBlock(
                id="tb-1",
                text="Revenue increased in Q3. Outlook remains positive.",
                page_number=1,
                bbox=BoundingBox(page_number=1, x0=10, y0=10, x1=200, y1=30),
                reading_order=0,
            ),
            TextBlock(
                id="tb-2",
                text="Risk disclosures and governance details are on page 2.",
                page_number=2,
                bbox=BoundingBox(page_number=2, x0=10, y0=10, x1=250, y1=30),
                reading_order=1,
            ),
        ],
        tables=[],
        figures=[],
        metadata={},
    )


def _sample_index() -> PageIndex:
    return PageIndex(
        document_id="doc-q",
        root_sections=[
            PageIndexSection(
                id="root",
                title="Document",
                page_start=1,
                page_end=3,
                key_entities=[],
                summary="Summary section",
                data_types_present=["tables"],
                children=[],
            )
        ],
    )


def _sample_ldu(page: int, content: str, ldu_id: str) -> LDU:
    prov = ProvenanceChain(
        records=[
            ProvenanceRecord(
                document_id="doc-q",
                page_number=page,
                bbox=BoundingBox(page_number=page, x0=0, y0=0, x1=10, y1=10),
                content_hash=f"hash-{ldu_id}",
                description="sample",
            )
        ]
    )
    return LDU(
        id=ldu_id,
        content=content,
        ldu_type=LDUType.PARAGRAPH,
        page_refs=[page],
        parent_section_id="section-root",
        token_count=len(content.split()),
        content_hash=f"hash-{ldu_id}",
        provenance=prov,
    )


def test_pageindex_persist_load_roundtrip(tmp_path: Path) -> None:
    builder = PageIndexBuilder()
    idx = builder.build(_sample_extracted_document())
    out = builder.persist(idx, output_dir=str(tmp_path))
    loaded = builder.load(out)

    assert loaded.document_id == idx.document_id
    assert len(loaded.root_sections) == len(idx.root_sections)
    assert loaded.root_sections[0].page_end == idx.root_sections[0].page_end

    payload = json.loads(Path(out).read_text(encoding="utf-8"))
    assert payload["schema_version"] == PAGEINDEX_SCHEMA_VERSION
    assert "page_index" in payload


def test_pageindex_load_supports_legacy_plain_json(tmp_path: Path) -> None:
    legacy = _sample_index()
    path = tmp_path / "legacy_pageindex.json"
    path.write_text(json.dumps(legacy.model_dump(mode="json")), encoding="utf-8")

    loaded = PageIndexBuilder().load(str(path))
    assert loaded.document_id == legacy.document_id
    assert loaded.root_sections[0].title == "Document"


def test_query_route_prefers_structured_when_db_and_question_match(tmp_path: Path) -> None:
    db = tmp_path / "facts.db"
    conn = sqlite3.connect(str(db))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE extracted_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL,
            table_id TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            row_index INTEGER NOT NULL,
            col_index INTEGER NOT NULL,
            column_header TEXT,
            value_text TEXT NOT NULL
        )
        """
    )
    cur.executemany(
        """
        INSERT INTO extracted_facts (
            document_id, table_id, page_number,
            row_index, col_index, column_header, value_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("doc-q", "t-1", 2, 0, 0, "revenue", "4.2B"),
            ("doc-q", "t-1", 2, 0, 1, "profit", "1.3B"),
        ],
    )
    conn.commit()
    conn.close()

    ldus = [
        _sample_ldu(page=2, content="Revenue reached 4.2B in Q3.", ldu_id="ldu-1"),
        _sample_ldu(page=3, content="Other context from page 3.", ldu_id="ldu-2"),
    ]
    result = QueryAgent().route_query(
        question="Show revenue values from the database table",
        index=_sample_index(),
        ldus=ldus,
        db_path=str(db),
    )

    assert result.route == "structured"
    assert result.sql_used is not None
    assert result.structured_rows is not None
    assert len(result.structured_rows) > 0
    assert result.provenance.records


def test_query_route_falls_back_to_semantic() -> None:
    ldus = [
        _sample_ldu(page=1, content="The company improved solvency in 2025.", ldu_id="ldu-1"),
    ]
    result = QueryAgent().route_query(
        question="Summarize solvency improvements",
        index=_sample_index(),
        ldus=ldus,
        db_path=None,
    )
    assert result.route == "semantic"
    assert "solvency" in result.answer.lower()
    assert result.provenance.records

