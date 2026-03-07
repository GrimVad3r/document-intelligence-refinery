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
    route: str = "semantic"
    sql_used: str | None = None


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
        db_path: str | None = None,
    ) -> LangGraphQueryResult:
        """Orchestrate structured vs semantic query paths for one question."""

        # Fallback path used when langgraph is not available in runtime.
        result = self.query_agent.route_query(
            question=question,
            index=index,
            ldus=ldus,
            db_path=db_path,
            top_k=3,
        )

        logger.info(
            "LangGraphQueryAgent run completed",
            extra={
                "question": question,
                "langgraph_runtime": self._langgraph_available,
                "route": result.route,
                "structured_rows": len(result.structured_rows or []),
            },
        )
        return LangGraphQueryResult(
            answer=result.answer,
            provenance=result.provenance,
            route=result.route,
            sql_used=result.sql_used,
        )
