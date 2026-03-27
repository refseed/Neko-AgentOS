from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from agent_os.investigation.query_builder.query_builder import RetrievalIntent


@dataclass(frozen=True)
class RecallCandidate:
    source_id: str
    text: str
    score: float


class HybridRecall:
    """Combine sparse, fuzzy, and exact matching for local sources."""

    def search(self, intent: RetrievalIntent, documents: list[tuple[str, str]]) -> list[RecallCandidate]:
        candidates: list[RecallCandidate] = []
        for source_id, text in documents:
            lowered = text.lower()
            sparse_hits = sum(1 for kw in intent.sparse_keywords if kw and kw in lowered)
            exact_hits = sum(1 for term in intent.exact_terms if term and term.lower() in lowered)
            fuzzy_score = 0.0
            if intent.fuzzy_terms:
                fuzzy_score = max(fuzz.partial_ratio(term, lowered) for term in intent.fuzzy_terms) / 100.0
            score = sparse_hits * 1.5 + exact_hits * 2.0 + fuzzy_score
            if score > 0:
                candidates.append(RecallCandidate(source_id=source_id, text=text, score=score))
        return candidates
