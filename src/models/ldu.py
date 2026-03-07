"""Logical Document Unit (LDU) models.

LDUs are the atomic, semantically coherent chunks emitted by the semantic
chunking engine. They preserve structural context and provenance suitable for
RAG and downstream querying.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .provenance import ProvenanceChain


class LDUType(str, Enum):
    """Types of logical document units."""

    PARAGRAPH = "paragraph"
    TABLE = "table"
    TABLE_CELL = "table_cell"
    FIGURE = "figure"
    LIST = "list"
    LIST_ITEM = "list_item"
    HEADER = "header"
    FOOTNOTE = "footnote"
    OTHER = "other"


class LDU(BaseModel):
    """Logical Document Unit with rich metadata and provenance."""

    id: str = Field(..., description="Stable identifier for this LDU.")
    content: str = Field(..., description="Human-readable text content for this unit.")
    ldu_type: LDUType = Field(..., description="Semantic type of this LDU.")
    page_refs: List[int] = Field(
        default_factory=list,
        description="List of page numbers this LDU spans (1-indexed).",
    )
    parent_section_id: Optional[str] = Field(
        None,
        description="Identifier of the PageIndex section that owns this LDU, if any.",
    )
    token_count: int = Field(
        ...,
        ge=0,
        description="Estimated token count, used for RAG budget and chunking.",
    )
    content_hash: str = Field(
        ...,
        description="Stable hash of canonicalized content for provenance integrity.",
    )
    provenance: ProvenanceChain = Field(
        default_factory=ProvenanceChain,
        description="Provenance chain describing where this content came from.",
    )
    related_ldu_ids: List[str] = Field(
        default_factory=list,
        description="Resolved cross-reference links to other LDUs (tables, figures, etc.).",
    )
    metadata: Dict[str, str] = Field(
        default_factory=dict,
        description="Additional structural metadata (section title, caption, table labels, etc.).",
    )

