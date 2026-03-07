"""Tests for semantic chunking constitution rules."""

from __future__ import annotations

from src.agents.chunker import ChunkingEngine, _split_list_items_by_token_budget
from src.models.extracted_document import ExtractedDocument, Figure, Table, TableCell, TextBlock
from src.models.provenance import BoundingBox


def _doc_with_rules() -> ExtractedDocument:
    return ExtractedDocument(
        document_id="rules-doc",
        num_pages=1,
        text_blocks=[
            TextBlock(
                id="tb-0",
                text="1. Executive Summary",
                page_number=1,
                bbox=BoundingBox(page_number=1, x0=10, y0=10, x1=150, y1=30),
                reading_order=0,
            ),
            TextBlock(
                id="tb-1",
                text="1) Revenue increased in Q3.",
                page_number=1,
                bbox=BoundingBox(page_number=1, x0=10, y0=40, x1=220, y1=55),
                reading_order=1,
            ),
            TextBlock(
                id="tb-2",
                text="2) Operating margin improved.",
                page_number=1,
                bbox=BoundingBox(page_number=1, x0=10, y0=58, x1=230, y1=73),
                reading_order=2,
            ),
            TextBlock(
                id="tb-3",
                text="See Table 1 and Figure 1 for supporting evidence.",
                page_number=1,
                bbox=BoundingBox(page_number=1, x0=10, y0=80, x1=300, y1=95),
                reading_order=3,
            ),
        ],
        tables=[
            Table(
                id="table-src-1",
                page_number=1,
                caption="Table 1: Quarterly Metrics",
                headers=["Metric", "Value"],
                cells=[
                    TableCell(row_index=0, col_index=0, text="Revenue", bbox=None),
                    TableCell(row_index=0, col_index=1, text="4.2B", bbox=None),
                ],
            )
        ],
        figures=[
            Figure(
                id="fig-src-1",
                page_number=1,
                caption="Figure 1: Revenue trend",
                bbox=BoundingBox(page_number=1, x0=320, y0=100, x1=500, y1=260),
            )
        ],
        metadata={},
    )


def test_chunker_enforces_semantic_rules() -> None:
    ldus = ChunkingEngine().chunk(_doc_with_rules())

    assert ldus

    list_ldu = next(ldu for ldu in ldus if ldu.ldu_type.value == "list")
    assert "1) Revenue increased in Q3." in list_ldu.content
    assert "2) Operating margin improved." in list_ldu.content

    table_ldu = next(ldu for ldu in ldus if ldu.ldu_type.value == "table")
    assert table_ldu.metadata.get("has_header") == "true"
    assert table_ldu.content.splitlines()[0] == "Metric | Value"

    figure_ldu = next(ldu for ldu in ldus if ldu.ldu_type.value == "figure")
    assert figure_ldu.metadata.get("caption") == "Figure 1: Revenue trend"

    paragraph_ref = next(ldu for ldu in ldus if "See Table 1 and Figure 1" in ldu.content)
    assert table_ldu.id in paragraph_ref.related_ldu_ids
    assert figure_ldu.id in paragraph_ref.related_ldu_ids

    has_header_ldu = any(ldu.ldu_type.value == "header" for ldu in ldus)
    if has_header_ldu:
        for ldu in ldus:
            if ldu.ldu_type.value != "header":
                assert ldu.parent_section_id is not None


def test_numbered_list_split_respects_token_budget() -> None:
    items = [
        "1) this is item one with several tokens",
        "2) this is item two with several tokens",
        "3) this is item three with several tokens",
    ]
    chunks = _split_list_items_by_token_budget(items, max_tokens=8)
    assert len(chunks) >= 2
    assert all(chunk.strip() for chunk in chunks)

