"""Lightweight vector ingestion for LDUs.

This module provides a local, dependency-light vector index and artifact writer
that can be used before adopting a production backend (FAISS/Chroma).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Sequence

from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
from sklearn.metrics.pairwise import cosine_similarity  # type: ignore[import-untyped]

from ..models.ldu import LDU
from ..utils.errors import QueryError
from ..utils.logging import get_logger


logger = get_logger(__name__)


@dataclass
class VectorHit:
    """Top-k vector retrieval result."""

    ldu: LDU
    score: float


class LocalVectorStore:
    """In-memory TF-IDF vector index over LDUs with optional artifact persistence."""

    def __init__(self) -> None:
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix = None
        self._ldus: List[LDU] = []

    def build(self, ldus: Sequence[LDU]) -> None:
        """Build an in-memory index for a set of LDUs."""

        self._ldus = list(ldus)
        if not self._ldus:
            self._vectorizer = None
            self._matrix = None
            return

        corpus = [ldu.content for ldu in self._ldus]
        self._vectorizer = TfidfVectorizer()
        self._matrix = self._vectorizer.fit_transform(corpus)

    def search(self, query: str, top_k: int = 5) -> List[VectorHit]:
        """Run top-k semantic search over indexed LDUs."""

        if not query.strip():
            raise QueryError("Query must not be empty.")
        if not self._ldus or self._vectorizer is None or self._matrix is None:
            return []

        query_vec = self._vectorizer.transform([query])
        sims = cosine_similarity(query_vec, self._matrix).flatten()
        ranked = sorted(range(len(self._ldus)), key=lambda i: sims[i], reverse=True)
        return [VectorHit(ldu=self._ldus[i], score=float(sims[i])) for i in ranked[:top_k]]

    def persist_manifest(
        self,
        document_id: str,
        output_dir: str,
        ldus: Sequence[LDU],
    ) -> str:
        """Persist a retrieval-ready JSONL manifest for downstream vector backends."""

        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f"{document_id}.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for ldu in ldus:
                row = {
                    "document_id": document_id,
                    "ldu_id": ldu.id,
                    "ldu_type": ldu.ldu_type.value,
                    "content": ldu.content,
                    "content_hash": ldu.content_hash,
                    "page_refs": ldu.page_refs,
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        logger.info(
            "Vector manifest written",
            extra={"document_id": document_id, "path": out_path, "rows": len(ldus)},
        )
        return out_path

