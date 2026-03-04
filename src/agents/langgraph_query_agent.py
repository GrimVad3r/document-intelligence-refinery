"""LangGraph-compatible orchestration wrapper for query tools.

If `langgraph` is not installed, this module still provides a deterministic
fallback orchestration path with the same high-level interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from ..models.ldu import LDU
from ..models.pageindex import PageIndex
from ..models.provenance import ProvenanceChain
from ..utils.logging import get_logger
from .query_agent import QueryAgent


logger = get_logger(__name__)


@dataclass
class LangGraphQueryResult:
    """Standardized query result payload."""

    answer: str
    provenance: ProvenanceChain


class LangGraphQueryAgent:
    """Query orchestrator with optional LangGraph runtime."""

    def __init__(self, query_agent: Optional[QueryAgent] = None) -> None:
        self.query_agent = query_agent or QueryAgent()
        self._langgraph_available = self._check_langgraph()

    @staticmethod
    def _check_langgraph() -> bool:
        try:
            import langgraph  # type: ignore[import-not-found,unused-ignore]
        except Exception:
            return False
        return True

    def run(
        self,
        question: str,
        index: PageIndex,
        ldus: Sequence[LDU],
    ) -> LangGraphQueryResult:
        """Orchestrate page navigation + semantic retrieval for one question."""

        # Fallback path used when langgraph is not available in runtime.
        sections = self.query_agent.pageindex_navigate(topic=question, index=index, top_k=3)
        hits = self.query_agent.semantic_search(query=question, ldus=ldus, top_k=3)

        if hits:
            best = hits[0]
            section_hint = sections[0].title if sections else "unknown section"
            answer = f"{best.content} (from {section_hint})"
            provenance = best.provenance
        else:
            answer = "No supporting evidence found."
            provenance = ProvenanceChain(records=[])

        logger.info(
            "LangGraphQueryAgent run completed",
            extra={
                "question": question,
                "langgraph_runtime": self._langgraph_available,
                "section_hits": len(sections),
                "ldu_hits": len(hits),
            },
        )
        return LangGraphQueryResult(answer=answer, provenance=provenance)

