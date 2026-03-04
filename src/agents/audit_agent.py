"""Audit mode for claim verification with provenance-backed evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
from sklearn.metrics.pairwise import cosine_similarity  # type: ignore[import-untyped]

from ..models.ldu import LDU
from ..models.provenance import ProvenanceChain
from ..utils.logging import get_logger


logger = get_logger(__name__)


@dataclass
class AuditResult:
    """Claim verification result."""

    claim: str
    verdict: str
    score: float
    provenance: ProvenanceChain
    supporting_ldu_ids: List[str]


class AuditAgent:
    """Verify claims against LDUs and return provenance or unverifiable verdicts."""

    def verify_claim(
        self,
        claim: str,
        ldus: Sequence[LDU],
        min_score: float = 0.12,
        top_k: int = 3,
    ) -> AuditResult:
        if not claim.strip() or not ldus:
            return AuditResult(
                claim=claim,
                verdict="unverifiable",
                score=0.0,
                provenance=ProvenanceChain(records=[]),
                supporting_ldu_ids=[],
            )

        corpus = [ldu.content for ldu in ldus]
        vectorizer = TfidfVectorizer()
        matrix = vectorizer.fit_transform(corpus + [claim])
        sims = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
        ranked = sorted(range(len(ldus)), key=lambda i: sims[i], reverse=True)
        top_indices = ranked[:top_k]

        top_score = float(sims[top_indices[0]]) if top_indices else 0.0
        matched = [ldus[i] for i in top_indices if sims[i] >= min_score]

        if not matched:
            logger.info(
                "Audit claim unverifiable",
                extra={"claim": claim, "top_score": top_score, "threshold": min_score},
            )
            return AuditResult(
                claim=claim,
                verdict="unverifiable",
                score=top_score,
                provenance=ProvenanceChain(records=[]),
                supporting_ldu_ids=[],
            )

        records = []
        ldu_ids: List[str] = []
        for ldu in matched:
            ldu_ids.append(ldu.id)
            records.extend(ldu.provenance.records)

        logger.info(
            "Audit claim verified",
            extra={"claim": claim, "top_score": top_score, "citations": len(records)},
        )
        return AuditResult(
            claim=claim,
            verdict="verified",
            score=top_score,
            provenance=ProvenanceChain(records=records),
            supporting_ldu_ids=ldu_ids,
        )

