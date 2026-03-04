"""Base interfaces for extraction strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, Tuple

from ..models.document_profile import DocumentProfile
from ..models.extracted_document import ExtractedDocument


class ExtractionResult(Protocol):
    """Protocol representing the result of an extraction strategy."""

    extracted_document: ExtractedDocument
    confidence_score: float


class BaseExtractor(ABC):
    """Abstract extractor with a common interface."""

    @abstractmethod
    def extract(self, document_path: str, profile: DocumentProfile) -> Tuple[ExtractedDocument, float]:
        """Run extraction and return (ExtractedDocument, confidence_score in [0,1])."""

