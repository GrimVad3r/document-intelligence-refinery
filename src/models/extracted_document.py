"""Normalized extracted document representation.

All extraction strategies (fast text, layout-aware, vision-augmented) must
normalize their outputs into this schema so that downstream components
(chunking engine, PageIndex builder, query agent) can operate consistently.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .provenance import BoundingBox


class TextBlock(BaseModel):
    """Block of text with spatial metadata and reading order information."""

    id: str = Field(..., description="Stable identifier of the text block.")
    text: str = Field(..., description="The raw text content.")
    page_number: int = Field(..., ge=1, description="Page number of this block (1-indexed).")
    bbox: Optional[BoundingBox] = Field(
        None,
        description="Bounding box of this block on the page, if available.",
    )
    reading_order: int = Field(
        ...,
        ge=0,
        description="Monotonic ordering index for reading sequence within the document.",
    )


class TableCell(BaseModel):
    """Single table cell with coordinates and text value."""

    row_index: int = Field(..., ge=0)
    col_index: int = Field(..., ge=0)
    text: str = Field(..., description="Cell text value.")
    bbox: Optional[BoundingBox] = Field(
        None,
        description="Bounding box covering this cell, if available.",
    )


class Table(BaseModel):
    """Structured table representation."""

    id: str = Field(..., description="Stable identifier of the table.")
    page_number: int = Field(..., ge=1, description="Page number containing the table.")
    caption: Optional[str] = Field(None, description="Optional table caption.")
    headers: List[str] = Field(
        default_factory=list,
        description="Header labels for columns, if detected.",
    )
    cells: List[TableCell] = Field(
        default_factory=list,
        description="Flattened list of table cells; (row_index, col_index) define structure.",
    )


class Figure(BaseModel):
    """Figure representation with caption and bounding box."""

    id: str = Field(..., description="Stable identifier of the figure.")
    page_number: int = Field(..., ge=1)
    caption: Optional[str] = Field(None, description="Figure caption text, if any.")
    bbox: Optional[BoundingBox] = Field(
        None,
        description="Bounding box roughly covering the figure image.",
    )


class ExtractedDocument(BaseModel):
    """Unified extracted representation for a document."""

    document_id: str = Field(..., description="Identifier of the source document.")
    num_pages: int = Field(..., ge=1, description="Total page count.")
    text_blocks: List[TextBlock] = Field(
        default_factory=list,
        description="All detected text blocks with spatial metadata.",
    )
    tables: List[Table] = Field(
        default_factory=list,
        description="All tables detected in the document.",
    )
    figures: List[Figure] = Field(
        default_factory=list,
        description="All figures detected in the document.",
    )

    metadata: Dict[str, str] = Field(
        default_factory=dict,
        description="Optional arbitrary metadata (title, author, etc.).",
    )

