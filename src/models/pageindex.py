"""PageIndex tree models.

The PageIndex provides a hierarchical navigation structure over a document,
similar to a smart table of contents, optimized for LLM traversal.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PageIndexSection(BaseModel):
    """Single node in the PageIndex tree."""

    id: str = Field(..., description="Stable identifier for the section node.")
    title: str = Field(..., description="Section title text.")
    page_start: int = Field(..., ge=1, description="1-indexed starting page.")
    page_end: int = Field(..., ge=1, description="1-indexed ending page (inclusive).")
    key_entities: List[str] = Field(
        default_factory=list,
        description="Named entities or key phrases associated with this section.",
    )
    summary: Optional[str] = Field(
        None,
        description="Short LLM-generated summary (2–3 sentences) of the section.",
    )
    data_types_present: List[str] = Field(
        default_factory=list,
        description="List of data types present (tables, figures, equations, etc.).",
    )
    children: List["PageIndexSection"] = Field(
        default_factory=list,
        description="Child subsections of this section.",
    )


class PageIndex(BaseModel):
    """Top-level PageIndex representation for a single document."""

    document_id: str = Field(..., description="Identifier of the underlying document.")
    root_sections: List[PageIndexSection] = Field(
        default_factory=list,
        description="Top-level sections forming the root of the navigation tree.",
    )

