from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MicroGraph:
    """In-memory claim-to-fact graph for current investigation."""

    claim_to_facts: dict[str, list[str]] = field(default_factory=dict)
    fact_sources: dict[str, str] = field(default_factory=dict)

    def add_support(self, claim: str, fact: str, source_ref: str) -> None:
        self.claim_to_facts.setdefault(claim, []).append(fact)
        self.fact_sources[fact] = source_ref

    def is_claim_supported(self, claim: str) -> bool:
        return bool(self.claim_to_facts.get(claim))
