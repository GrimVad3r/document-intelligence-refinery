"""Document profiling models for the Document Intelligence Refinery.

This module defines the `DocumentProfile` Pydantic model, which captures
triage-time characteristics of an input document and governs downstream
extraction strategy selection.

The design follows the Week 3 challenge brief and is intended to be stable
for use across agents, strategies, and persisted profile artifacts.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OriginType(str, Enum):
    """High-level origin category of a document."""

    NATIVE_DIGITAL = "native_digital"
    SCANNED_IMAGE = "scanned_image"
    MIXED = "mixed"
    FORM_FILLABLE = "form_fillable"


class LayoutComplexity(str, Enum):
    """Layout structure complexity categories."""

    SINGLE_COLUMN = "single_column"
    MULTI_COLUMN = "multi_column"
    TABLE_HEAVY = "table_heavy"
    FIGURE_HEAVY = "figure_heavy"
    MIXED = "mixed"


class EstimatedExtractionCost(str, Enum):
    """Expected extraction cost tier."""

    FAST_TEXT_SUFFICIENT = "fast_text_sufficient"
    NEEDS_LAYOUT_MODEL = "needs_layout_model"
    NEEDS_VISION_MODEL = "needs_vision_model"


class DomainHint(str, Enum):
    """Domain hints used to specialize prompts and downstream handling."""

    FINANCIAL = "financial"
    LEGAL = "legal"
    TECHNICAL = "technical"
    MEDICAL = "medical"
    GENERAL = "general"


class LanguageProfile(BaseModel):
    """Detected language and confidence information."""

    code: str = Field(..., description="BCP-47 or ISO 639-1 language code (e.g. 'en').")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model-estimated confidence score in [0, 1].",
    )


class HeuristicSignals(BaseModel):
    """Raw heuristic signals used to derive the profile.

    Persisting these values alongside the high-level profile enables
    reproducibility and downstream analysis of failure modes.
    """

    avg_chars_per_page: float = Field(
        ...,
        ge=0.0,
        description="Average character count per page from fast text extraction.",
    )
    avg_char_density: float = Field(
        ...,
        ge=0.0,
        description="Average characters per unit page area (chars / (w*h) in points).",
    )
    avg_image_area_ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Average fraction of page area occupied by images.",
    )
    table_like_region_ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Heuristic estimate of table-heavy content on a 0–1 scale.",
    )
    multi_column_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Heuristic confidence that the document uses multiple columns.",
    )


class DocumentProfile(BaseModel):
    """Top-level document triage profile.

    This schema is serialized to `.refinery/profiles/{doc_id}.json` and is
    the authoritative record of how a document should be processed by the
    extraction pipeline.
    """

    doc_id: str = Field(
        ...,
        description="Stable identifier for the document (filename without extension, UUID, etc.).",
    )
    source_path: Optional[str] = Field(
        None,
        description="Filesystem path or URI from which the document was loaded.",
    )

    origin_type: OriginType = Field(
        ...,
        description="Inferred origin type, used to decide OCR vs. text-based strategies.",
    )
    layout_complexity: LayoutComplexity = Field(
        ...,
        description="Inferred layout complexity, used to select layout-aware strategies.",
    )
    language: LanguageProfile = Field(
        ...,
        description="Detected primary document language and confidence.",
    )
    domain_hint: DomainHint = Field(
        DomainHint.GENERAL,
        description="Domain hint for prompt specialization and pipeline routing.",
    )
    estimated_extraction_cost: EstimatedExtractionCost = Field(
        ...,
        description="Estimated cost tier guiding strategy selection.",
    )

    heuristic_signals: HeuristicSignals = Field(
        ...,
        description="Underlying heuristic measurements that informed the classification.",
    )

    class Config:
        frozen = True

