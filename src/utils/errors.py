"""Custom exception hierarchy for the Document Intelligence Refinery."""

from __future__ import annotations


class RefineryError(Exception):
    """Base class for all custom errors in the refinery."""


class ConfigError(RefineryError):
    """Configuration-related problems (missing files, invalid values, etc.)."""


class TriageError(RefineryError):
    """Errors arising during document triage and profiling."""


class ExtractionError(RefineryError):
    """Errors occurring in any extraction strategy or router."""


class ChunkingError(RefineryError):
    """Errors emitted by the semantic chunking engine."""


class IndexingError(RefineryError):
    """Errors during PageIndex construction or navigation."""


class QueryError(RefineryError):
    """Errors surfaced by the query agent or its tools."""

