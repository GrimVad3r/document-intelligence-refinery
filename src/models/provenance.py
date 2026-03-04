"""Provenance and spatial indexing models for extracted content.

These models ensure every extracted fact can be traced back to its exact
location in the source document, enabling robust auditability.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Axis-aligned bounding box on a PDF page, in PDF coordinate space.

    Coordinates follow the common pdfplumber convention:
    - origin at bottom-left of the page
    - units in PDF points (1/72 inch)
    - (x0, y0) is lower-left; (x1, y1) is upper-right
    """

    page_number: int = Field(..., ge=1, description="1-indexed page number.")
    x0: float = Field(..., description="Left x-coordinate in PDF points.")
    y0: float = Field(..., description="Bottom y-coordinate in PDF points.")
    x1: float = Field(..., description="Right x-coordinate in PDF points.")
    y1: float = Field(..., description="Top y-coordinate in PDF points.")

    def as_tuple(self) -> Tuple[int, float, float, float, float]:
        """Return a simple tuple representation useful for hashing and logs."""

        return (self.page_number, self.x0, self.y0, self.x1, self.y1)


class ProvenanceRecord(BaseModel):
    """Single provenance citation for a content fragment."""

    document_id: str = Field(..., description="Stable identifier of the source document.")
    page_number: int = Field(..., ge=1, description="1-indexed page number.")
    bbox: Optional[BoundingBox] = Field(
        None,
        description="Optional bounding box specifying the spatial region containing the content.",
    )
    content_hash: str = Field(
        ...,
        description="Stable hash of the canonicalized content, used for verification.",
    )
    description: Optional[str] = Field(
        None,
        description="Optional human-readable description of what this citation refers to.",
    )


class ProvenanceChain(BaseModel):
    """Chain of provenance records supporting an answer or fact."""

    records: List[ProvenanceRecord] = Field(
        default_factory=list,
        description="Ordered list of provenance records used to support an answer.",
    )

    def add_record(self, record: ProvenanceRecord) -> None:
        """Append a record to the chain."""

        self.records.append(record)

