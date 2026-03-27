from __future__ import annotations

from agent_os.investigation.recall.hybrid_recall import RecallCandidate


def rerank_candidates(candidates: list[RecallCandidate], top_k: int = 5) -> list[RecallCandidate]:
    """Sort candidates by score and keep top_k entries."""

    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
    return ranked[:top_k]
