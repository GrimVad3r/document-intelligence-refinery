"""Query Interface Agent.

Provides three primary tools:
- pageindex_navigate: keyword-based traversal over the PageIndex.
- semantic_search: vector-based retrieval over LDUs.
- structured_query: SQL queries against a SQLite fact table.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
from sklearn.metrics.pairwise import cosine_similarity  # type: ignore[import-untyped]

from .audit_agent import AuditAgent, AuditResult
from ..models.ldu import LDU
from ..models.pageindex import PageIndex, PageIndexSection
from ..models.provenance import ProvenanceChain
from ..utils.errors import QueryError
from ..utils.logging import get_logger


logger = get_logger(__name__)


def _flatten_sections(sections: Sequence[PageIndexSection]) -> List[PageIndexSection]:
    out: List[PageIndexSection] = []
    for section in sections:
        out.append(section)
        out.extend(_flatten_sections(section.children))
    return out


@dataclass
class QueryResult:
    """Answer text paired with a provenance chain."""

    answer: str
    provenance: ProvenanceChain
    route: str = "semantic"
    sql_used: str | None = None
    structured_rows: List[Tuple] | None = None
    metadata: Dict[str, Any] | None = None


@dataclass
class StructuredQueryPlan:
    """SQL plan inferred from a user question."""

    sql: str
    params: Tuple[object, ...]
    rationale: str


class QueryAgent:
    """High-level query interface over PageIndex, LDUs, and fact tables."""

    def __init__(self) -> None:
        self.audit_agent = AuditAgent()

    @staticmethod
    def _looks_structured_query(question: str) -> bool:
        q = question.lower()
        patterns = (
            "how many",
            "count",
            "total",
            "sum",
            "average",
            "avg",
            "maximum",
            "minimum",
            "top ",
            "sql",
            "table",
            "database",
            "value",
            "metric",
        )
        return any(p in q for p in patterns)

    @staticmethod
    def _infer_structured_plan(question: str) -> StructuredQueryPlan:
        q = question.lower().strip()
        if "how many" in q or "count" in q:
            return StructuredQueryPlan(
                sql="SELECT COUNT(*) FROM extracted_facts",
                params=(),
                rationale="count request",
            )

        metric_match = re.search(r"\b(revenue|profit|asset|liability|expense|income|margin)\b", q)
        if metric_match:
            metric = metric_match.group(1)
            return StructuredQueryPlan(
                sql=(
                    "SELECT column_header, value_text, page_number "
                    "FROM extracted_facts "
                    "WHERE LOWER(COALESCE(column_header, '')) LIKE ? "
                    "   OR LOWER(value_text) LIKE ? "
                    "LIMIT 20"
                ),
                params=(f"%{metric}%", f"%{metric}%"),
                rationale=f"metric lookup for '{metric}'",
            )

        return StructuredQueryPlan(
            sql=(
                "SELECT column_header, value_text, page_number "
                "FROM extracted_facts "
                "LIMIT 20"
            ),
            params=(),
            rationale="generic structured fallback",
        )

    @staticmethod
    def _provenance_from_rows(rows: Sequence[Tuple], ldus: Sequence[LDU]) -> ProvenanceChain:
        """Build provenance by mapping SQL row page numbers back to LDUs."""

        page_numbers: set[int] = set()
        for row in rows:
            if len(row) >= 3 and isinstance(row[2], int):
                page_numbers.add(row[2])
        records = []
        for ldu in ldus:
            if ldu.page_refs and ldu.page_refs[0] in page_numbers:
                records.extend(ldu.provenance.records)
        return ProvenanceChain(records=records)

    @staticmethod
    def _format_structured_rows(rows: Sequence[Tuple], max_rows: int = 5) -> str:
        if not rows:
            return "No structured records found."
        preview = list(rows[:max_rows])
        lines = [str(r) for r in preview]
        if len(rows) > max_rows:
            lines.append(f"... ({len(rows) - max_rows} more rows)")
        return "\n".join(lines)

    def pageindex_navigate(self, topic: str, index: PageIndex, top_k: int = 3) -> List[PageIndexSection]:
        """Return the most relevant sections for a topic using TF-IDF similarity."""

        sections = _flatten_sections(index.root_sections)
        corpus = [s.title + " " + (s.summary or "") for s in sections]
        if not corpus:
            return []

        vectorizer = TfidfVectorizer()
        matrix = vectorizer.fit_transform(corpus + [topic])
        sims = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
        ranked = sorted(range(len(sections)), key=lambda i: sims[i], reverse=True)
        return [sections[i] for i in ranked[:top_k]]

    def semantic_search(self, query: str, ldus: Sequence[LDU], top_k: int = 5) -> List[LDU]:
        """Return the most relevant LDUs for a free-text query."""

        if not ldus:
            return []
        corpus = [ldu.content for ldu in ldus]
        vectorizer = TfidfVectorizer()
        matrix = vectorizer.fit_transform(corpus + [query])
        sims = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
        ranked = sorted(range(len(ldus)), key=lambda i: sims[i], reverse=True)
        return [ldus[i] for i in ranked[:top_k]]

    def structured_query(self, db_path: str, sql: str, params: Tuple[object, ...] | None = None) -> List[Tuple]:
        """Execute a SQL query against a SQLite fact table and return rows."""

        if not db_path:
            raise QueryError("Database path is required for structured_query.")
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.exception("structured_query failed", db_path=db_path, sql=sql)
            raise QueryError("structured_query execution failed") from exc
        return rows

    def answer_with_provenance(self, question: str, ldus: Sequence[LDU], top_k: int = 3) -> QueryResult:
        """Return a short answer draft with provenance from best-matching LDUs."""

        hits = self.semantic_search(query=question, ldus=ldus, top_k=top_k)
        if not hits:
            return QueryResult(
                answer="No evidence found.",
                provenance=ProvenanceChain(records=[]),
                route="semantic",
                metadata={"hit_count": 0},
            )

        snippets = [hit.content for hit in hits]
        answer = "\n".join(snippets)

        records = []
        for hit in hits:
            records.extend(hit.provenance.records)
        return QueryResult(
            answer=answer,
            provenance=ProvenanceChain(records=records),
            route="semantic",
            metadata={"hit_count": len(hits)},
        )

    def route_query(
        self,
        question: str,
        index: PageIndex,
        ldus: Sequence[LDU],
        db_path: str | None = None,
        top_k: int = 3,
    ) -> QueryResult:
        """Route query between structured SQL path and semantic retrieval."""

        sections = self.pageindex_navigate(topic=question, index=index, top_k=top_k)
        section_hint = sections[0].title if sections else "unknown"

        if db_path and self._looks_structured_query(question):
            plan = self._infer_structured_plan(question)
            try:
                rows = self.structured_query(db_path=db_path, sql=plan.sql, params=plan.params)
            except QueryError:
                logger.warning(
                    "Structured route failed, falling back to semantic",
                    extra={"question": question, "sql": plan.sql},
                )
            else:
                if rows:
                    prov = self._provenance_from_rows(rows, ldus)
                    answer = f"[Structured:{section_hint}]\n{self._format_structured_rows(rows)}"
                    return QueryResult(
                        answer=answer,
                        provenance=prov,
                        route="structured",
                        sql_used=plan.sql,
                        structured_rows=list(rows),
                        metadata={"rationale": plan.rationale, "section_hint": section_hint},
                    )

        semantic_result = self.answer_with_provenance(question=question, ldus=ldus, top_k=top_k)
        semantic_result.metadata = {
            **(semantic_result.metadata or {}),
            "section_hint": section_hint,
        }
        return semantic_result

    def verify_claim(self, claim: str, ldus: Sequence[LDU], min_score: float = 0.12) -> AuditResult:
        """Audit claim against extracted LDUs and return verified/unverifiable verdict."""

        return self.audit_agent.verify_claim(claim=claim, ldus=ldus, min_score=min_score)

