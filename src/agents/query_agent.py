"""Query Interface Agent.

Provides three primary tools:
- pageindex_navigate: keyword-based traversal over the PageIndex.
- semantic_search: vector-based retrieval over LDUs.
- structured_query: SQL queries against a SQLite fact table.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import List, Sequence, Tuple

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


class QueryAgent:
    """High-level query interface over PageIndex, LDUs, and fact tables."""

    def __init__(self) -> None:
        self.audit_agent = AuditAgent()

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
            return QueryResult(answer="No evidence found.", provenance=ProvenanceChain(records=[]))

        snippets = [hit.content for hit in hits]
        answer = "\n".join(snippets)

        records = []
        for hit in hits:
            records.extend(hit.provenance.records)
        return QueryResult(answer=answer, provenance=ProvenanceChain(records=records))

    def verify_claim(self, claim: str, ldus: Sequence[LDU], min_score: float = 0.12) -> AuditResult:
        """Audit claim against extracted LDUs and return verified/unverifiable verdict."""

        return self.audit_agent.verify_claim(claim=claim, ldus=ldus, min_score=min_score)

