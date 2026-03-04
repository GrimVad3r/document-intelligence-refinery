"""Extraction router and orchestration agent.

This module implements the multi-strategy extraction router with a
confidence-gated escalation guard and a persistent extraction ledger.
"""

from __future__ import annotations

import json
import os
import time
from typing import Tuple

import yaml  # type: ignore[import-untyped]

from ..models.document_profile import DocumentProfile, EstimatedExtractionCost
from ..models.extracted_document import ExtractedDocument
from ..strategies.fast_text_extractor import FastTextExtractor
from ..strategies.layout_extractor import LayoutExtractor
from ..strategies.vision_extractor import VisionExtractor
from ..utils.errors import ConfigError, ExtractionError
from ..utils.logging import get_logger


logger = get_logger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RUBRIC_PATH = os.path.join(PROJECT_ROOT, "rubric", "extraction_rules.yaml")
LEDGER_PATH = os.path.join(PROJECT_ROOT, ".refinery", "extraction_ledger.jsonl")


def _load_escalation_threshold() -> float:
    """Load the confidence threshold that triggers strategy escalation."""

    if not os.path.exists(RUBRIC_PATH):
        raise ConfigError(f"Missing extraction rules at {RUBRIC_PATH}")
    with open(RUBRIC_PATH, "r", encoding="utf-8") as f:
        rules = yaml.safe_load(f) or {}
    return float(rules.get("escalation", {}).get("confidence_threshold", 0.7))


class ExtractionRouter:
    """Strategy router that enforces the escalation guard."""

    def __init__(self) -> None:
        self.fast_text = FastTextExtractor()
        self.layout = LayoutExtractor()
        self.vision = VisionExtractor()
        self.escalation_threshold = _load_escalation_threshold()

    def extract(self, document_path: str, profile: DocumentProfile) -> ExtractedDocument:
        """Dispatch to the appropriate extractor and escalate if confidence is low."""

        start_time = time.time()
        strategy_name = ""
        confidence = 0.0
        cost_estimate = 0.0

        try:
            if profile.estimated_extraction_cost == EstimatedExtractionCost.FAST_TEXT_SUFFICIENT:
                strategy_name = "fast_text"
                extracted, confidence = self.fast_text.extract(document_path, profile)
                if confidence < self.escalation_threshold:
                    logger.info(
                        "FastTextExtractor confidence below threshold, escalating to layout extractor",
                        extra={
                            "doc_id": profile.doc_id,
                            "confidence": confidence,
                            "threshold": self.escalation_threshold,
                        },
                    )
                    strategy_name = "layout"
                    extracted, confidence = self.layout.extract(document_path, profile)

            elif profile.estimated_extraction_cost == EstimatedExtractionCost.NEEDS_LAYOUT_MODEL:
                strategy_name = "layout"
                extracted, confidence = self.layout.extract(document_path, profile)
                if confidence < self.escalation_threshold:
                    logger.info(
                        "LayoutExtractor confidence below threshold, escalating to vision extractor",
                        extra={
                            "doc_id": profile.doc_id,
                            "confidence": confidence,
                            "threshold": self.escalation_threshold,
                        },
                    )
                    strategy_name = "vision"
                    extracted, confidence = self.vision.extract(document_path, profile)
                    cost_estimate = self.vision.last_cost_estimate

            else:
                strategy_name = "vision"
                extracted, confidence = self.vision.extract(document_path, profile)
                cost_estimate = self.vision.last_cost_estimate

        except (ConfigError, ExtractionError):
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("ExtractionRouter encountered an unexpected error", doc_id=profile.doc_id)
            raise ExtractionError("Unexpected error in ExtractionRouter") from exc

        duration = time.time() - start_time
        self._write_ledger_entry(
            profile=profile,
            strategy=strategy_name,
            confidence=confidence,
            cost_estimate=cost_estimate,
            duration_sec=duration,
        )

        logger.info(
            "ExtractionRouter completed",
            extra={
                "doc_id": profile.doc_id,
                "strategy": strategy_name,
                "confidence": confidence,
                "cost_estimate_usd": cost_estimate,
                "duration_sec": duration,
            },
        )

        return extracted

    def _write_ledger_entry(
        self,
        profile: DocumentProfile,
        strategy: str,
        confidence: float,
        cost_estimate: float,
        duration_sec: float,
    ) -> None:
        """Append a JSON line entry to the extraction ledger."""

        os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
        entry = {
            "doc_id": profile.doc_id,
            "strategy_used": strategy,
            "origin_type": profile.origin_type.value,
            "layout_complexity": profile.layout_complexity.value,
            "estimated_extraction_cost": profile.estimated_extraction_cost.value,
            "confidence_score": confidence,
            "cost_estimate_usd": cost_estimate,
            "processing_time_sec": duration_sec,
        }
        with open(LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

