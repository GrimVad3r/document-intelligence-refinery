"""Document triage agent.

This agent inspects a document using fast heuristics and produces a
`DocumentProfile` that governs downstream extraction strategy selection.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Tuple

import pdfplumber  # type: ignore[import-untyped]
import yaml  # type: ignore[import-untyped]

from ..models.document_profile import (
    DocumentProfile,
    DomainHint,
    EstimatedExtractionCost,
    HeuristicSignals,
    LanguageProfile,
    LayoutComplexity,
    OriginType,
)
from ..utils.errors import ConfigError, TriageError
from ..utils.logging import get_logger


logger = get_logger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RUBRIC_PATH = os.path.join(PROJECT_ROOT, "rubric", "extraction_rules.yaml")
PROFILES_DIR = os.path.join(PROJECT_ROOT, ".refinery", "profiles")


@dataclass
class TriageThresholds:
    """Configuration thresholds controlling triage classification."""

    fast_text_min_avg_chars_per_page: float
    fast_text_min_char_density: float
    fast_text_max_image_area_ratio: float
    multi_column_threshold: float
    table_heavy_threshold: float


def _load_thresholds() -> TriageThresholds:
    """Load triage thresholds from the rubric configuration."""

    if not os.path.exists(RUBRIC_PATH):
        raise ConfigError(f"Missing extraction rules at {RUBRIC_PATH}")

    with open(RUBRIC_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    triage = config.get("triage", {})
    thresholds = TriageThresholds(
        fast_text_min_avg_chars_per_page=float(triage.get("fast_text_min_avg_chars_per_page", 150)),
        fast_text_min_char_density=float(triage.get("fast_text_min_char_density", 0.0015)),
        fast_text_max_image_area_ratio=float(triage.get("fast_text_max_image_area_ratio", 0.4)),
        multi_column_threshold=float(triage.get("multi_column_threshold", 0.6)),
        table_heavy_threshold=float(triage.get("table_heavy_threshold", 0.4)),
    )
    return thresholds


def _detect_origin_type(
    avg_chars_per_page: float,
    char_density: float,
    image_area_ratio: float,
) -> OriginType:
    """Infer origin type from character and image statistics."""

    if avg_chars_per_page < 30 and image_area_ratio > 0.6:
        return OriginType.SCANNED_IMAGE
    if image_area_ratio > 0.4:
        return OriginType.MIXED
    return OriginType.NATIVE_DIGITAL


def _detect_layout_complexity(
    multi_column_conf: float,
    table_ratio: float,
) -> LayoutComplexity:
    """Infer layout complexity from table and multi-column signals."""

    if table_ratio > 0.6:
        return LayoutComplexity.TABLE_HEAVY
    if multi_column_conf > 0.7:
        return LayoutComplexity.MULTI_COLUMN
    if 0.3 < table_ratio <= 0.6:
        return LayoutComplexity.MIXED
    return LayoutComplexity.SINGLE_COLUMN


def _estimate_cost(origin_type: OriginType, layout: LayoutComplexity) -> EstimatedExtractionCost:
    """Map origin and layout to an extraction cost tier."""

    if origin_type == OriginType.SCANNED_IMAGE:
        return EstimatedExtractionCost.NEEDS_VISION_MODEL
    if layout in (LayoutComplexity.MULTI_COLUMN, LayoutComplexity.TABLE_HEAVY, LayoutComplexity.MIXED):
        return EstimatedExtractionCost.NEEDS_LAYOUT_MODEL
    return EstimatedExtractionCost.FAST_TEXT_SUFFICIENT


def _detect_language(text_sample: str) -> Tuple[str, float]:
    """Detect primary language using lightweight character heuristics.

    This implementation is intentionally simple and dependency-free. It can be
    replaced by a more sophisticated classifier without changing call sites.
    """

    if not text_sample:
        return "unknown", 0.0

    ascii_chars = sum(1 for ch in text_sample if ord(ch) < 128)
    ascii_ratio = ascii_chars / max(len(text_sample), 1)

    if ascii_ratio > 0.98:
        return "en", 0.9

    if ascii_ratio > 0.9:
        return "en", 0.6

    return "unknown", 0.5


def _detect_domain_hint(text_sample: str) -> DomainHint:
    """Assign a coarse domain label based on keyword heuristics."""

    lowered = text_sample.lower()
    if any(k in lowered for k in ("balance sheet", "income statement", "fiscal", "asset", "liability")):
        return DomainHint.FINANCIAL
    if any(k in lowered for k in ("plaintiff", "defendant", "hereby", "statute", "regulation")):
        return DomainHint.LEGAL
    if any(k in lowered for k in ("algorithm", "throughput", "latency", "architecture", "protocol")):
        return DomainHint.TECHNICAL
    if any(k in lowered for k in ("clinical", "patient", "diagnosis", "treatment", "symptom")):
        return DomainHint.MEDICAL
    return DomainHint.GENERAL


def triage_document(doc_id: str, document_path: str) -> DocumentProfile:
    """Run triage on a document and persist the resulting `DocumentProfile`."""

    thresholds = _load_thresholds()

    if not os.path.exists(document_path):
        raise TriageError(f"Document path does not exist: {document_path}")

    try:
        with pdfplumber.open(document_path) as pdf:
            total_chars = 0
            total_area = 0.0
            total_image_area = 0.0
            table_like_region_ratio = 0.0

            sample_text_parts: list[str] = []

            for page in pdf.pages:
                width = float(page.width or 0.0)
                height = float(page.height or 0.0)
                page_area = width * height if width and height else 0.0
                total_area += page_area

                text = page.extract_text() or ""
                total_chars += len(text)
                if text.strip():
                    sample_text_parts.append(text[:1000])

                for image in page.images or []:
                    x0 = float(image.get("x0", 0.0))
                    y0 = float(image.get("y0", 0.0))
                    x1 = float(image.get("x1", 0.0))
                    y1 = float(image.get("y1", 0.0))
                    total_image_area += max(0.0, (x1 - x0) * (y1 - y0))

                # Approximate table presence using tab characters and common delimiters.
                if text.count("|") > 5 or text.count("\t") > 5:
                    table_like_region_ratio += 1.0

            if not pdf.pages:
                raise TriageError("No pages found in document during triage.")

            num_pages = len(pdf.pages)

    except TriageError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Triage failed while reading PDF", document_path=document_path)
        raise TriageError(f"Triage failed for document {document_path}") from exc

    avg_chars_per_page = total_chars / max(num_pages, 1)
    char_density = (total_chars / total_area) if total_area > 0 else 0.0
    image_area_ratio = (total_image_area / total_area) if total_area > 0 else 0.0
    table_like_ratio = table_like_region_ratio / max(num_pages, 1)

    # Multi-column confidence heuristic.
    multi_column_confidence = 0.0
    if char_density > thresholds.fast_text_min_char_density:
        multi_column_confidence = 0.3
    if char_density > thresholds.fast_text_min_char_density * 1.5:
        multi_column_confidence = 0.1

    origin_type = _detect_origin_type(avg_chars_per_page, char_density, image_area_ratio)
    layout_complexity = _detect_layout_complexity(multi_column_confidence, table_like_ratio)
    estimated_cost = _estimate_cost(origin_type, layout_complexity)

    sample_text = "\n".join(sample_text_parts)[:2000]
    lang_code, lang_conf = _detect_language(sample_text)
    domain_hint = _detect_domain_hint(sample_text)

    heuristic_signals = HeuristicSignals(
        avg_chars_per_page=avg_chars_per_page,
        avg_char_density=char_density,
        avg_image_area_ratio=image_area_ratio,
        table_like_region_ratio=table_like_ratio,
        multi_column_confidence=multi_column_confidence,
    )

    profile = DocumentProfile(
        doc_id=doc_id,
        source_path=document_path,
        origin_type=origin_type,
        layout_complexity=layout_complexity,
        language=LanguageProfile(code=lang_code, confidence=lang_conf),
        domain_hint=domain_hint,
        estimated_extraction_cost=estimated_cost,
        heuristic_signals=heuristic_signals,
    )

    os.makedirs(PROFILES_DIR, exist_ok=True)
    profile_path = os.path.join(PROFILES_DIR, f"{doc_id}.json")
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

    logger.info(
        "Triage completed",
        extra={
            "doc_id": doc_id,
            "document_path": document_path,
            "origin_type": origin_type.value,
            "layout_complexity": layout_complexity.value,
            "estimated_cost": estimated_cost.value,
            "avg_chars_per_page": avg_chars_per_page,
            "char_density": char_density,
            "image_area_ratio": image_area_ratio,
            "table_like_ratio": table_like_ratio,
        },
    )

    return profile

