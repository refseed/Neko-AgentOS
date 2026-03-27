from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_os.investigation.recall.hybrid_recall import RecallCandidate
from agent_os.runtime.nodes.base import BaseLLMNode, NodeEnvelopeMixin, NodeGateway


class DistilledEvidence(BaseModel):
    """Compact evidence package returned to main graph."""

    model_config = ConfigDict(extra="forbid")

    facts: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    enough_evidence: bool = False


class DistillInput(BaseModel):
    """Protocol input for result distillation node."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[RecallCandidate]
    max_facts: int = 3


class DistillOutput(NodeEnvelopeMixin):
    """Protocol output for result distillation node."""

    node_name: str = "result_distiller"
    facts: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    enough_evidence: bool = False


class EvidenceReview(BaseModel):
    """Review verdict for distilled investigation evidence."""

    model_config = ConfigDict(extra="forbid")

    enough_evidence: bool
    issues: list[str] = Field(default_factory=list)


class EvidenceReviewInput(BaseModel):
    """Protocol input for investigation review node."""

    model_config = ConfigDict(extra="forbid")

    question: str
    evidence: DistilledEvidence


class EvidenceReviewOutput(NodeEnvelopeMixin):
    """Protocol output for investigation review node."""

    node_name: str = "investigation_review"
    enough_evidence: bool
    issues: list[str] = Field(default_factory=list)


class ResultDistillNode(BaseLLMNode[DistillInput, DistillOutput]):
    """Model-driven result distillation node."""

    @property
    def output_model(self) -> type[DistillOutput]:
        return DistillOutput

    def _fallback(self, node_input: DistillInput) -> DistilledEvidence:
        facts: list[str] = []
        refs: list[str] = []
        for candidate in node_input.candidates[: node_input.max_facts]:
            line = candidate.text.strip().splitlines()[0][:220]
            if line:
                facts.append(line)
                refs.append(candidate.source_id)
        return DistilledEvidence(facts=facts, source_refs=refs, enough_evidence=len(facts) >= 1)

    def fallback(self, node_input: DistillInput) -> DistillOutput:
        fallback = self._fallback(node_input)
        return DistillOutput(
            protocol_version="node-io/v1",
            node_name="result_distiller",
            confidence=0.72,
            notes=["fallback_extractor"],
            facts=fallback.facts,
            source_refs=fallback.source_refs,
            enough_evidence=fallback.enough_evidence,
        )

    def build_prompt(self, node_input: DistillInput) -> str:
        candidate_text = "\n".join(
            f"- source={item.source_id} score={item.score:.3f} text={item.text[:300].replace(chr(10), ' ')}"
            for item in node_input.candidates[: max(1, node_input.max_facts * 3)]
        )
        return (
            "You are the result-distillation node in investigation.\n"
            "Select minimal grounded facts and sources.\n"
            "Protocol:\n"
            "- Return strict JSON only.\n"
            "- Required keys: protocol_version, node_name, confidence, notes, facts, source_refs, enough_evidence.\n"
            "- protocol_version must be 'node-io/v1'.\n"
            "- node_name must be 'result_distiller'.\n"
            f"max_facts={node_input.max_facts}\n"
            f"candidates:\n{candidate_text}\n"
        )


class InvestigationReviewNode(BaseLLMNode[EvidenceReviewInput, EvidenceReviewOutput]):
    """Model-driven review/reflection node for investigation evidence."""

    @property
    def output_model(self) -> type[EvidenceReviewOutput]:
        return EvidenceReviewOutput

    def fallback(self, node_input: EvidenceReviewInput) -> EvidenceReviewOutput:
        return EvidenceReviewOutput(
            protocol_version="node-io/v1",
            node_name="investigation_review",
            confidence=0.7,
            notes=["fallback_evidence_review"],
            enough_evidence=node_input.evidence.enough_evidence,
            issues=[],
        )

    def build_prompt(self, node_input: EvidenceReviewInput) -> str:
        facts_text = "\n".join(f"- {fact}" for fact in node_input.evidence.facts) or "- none"
        refs_text = "\n".join(f"- {ref}" for ref in node_input.evidence.source_refs) or "- none"
        return (
            "You are the investigation review/reflection node.\n"
            "Judge whether evidence is sufficient for the question.\n"
            "Protocol:\n"
            "- Return strict JSON only.\n"
            "- Required keys: protocol_version, node_name, confidence, notes, enough_evidence, issues.\n"
            "- protocol_version must be 'node-io/v1'.\n"
            "- node_name must be 'investigation_review'.\n"
            f"question: {node_input.question}\n"
            f"facts:\n{facts_text}\n"
            f"source_refs:\n{refs_text}\n"
        )


def extract_distilled_facts(
    candidates: list[RecallCandidate],
    max_facts: int = 3,
    model_gateway: NodeGateway | None = None,
    model_tier: str = "small",
) -> DistilledEvidence:
    node = ResultDistillNode(node_name="result_distiller", model_gateway=model_gateway)
    output = node.run(
        DistillInput(candidates=candidates, max_facts=max_facts),
        model_tier=model_tier,
    )
    return DistilledEvidence(
        facts=list(output.facts),
        source_refs=list(output.source_refs),
        enough_evidence=output.enough_evidence,
    )


def review_distilled_evidence(
    question: str,
    evidence: DistilledEvidence,
    model_gateway: NodeGateway | None = None,
    model_tier: str = "small",
) -> EvidenceReview:
    node = InvestigationReviewNode(node_name="investigation_review", model_gateway=model_gateway)
    output = node.run(
        EvidenceReviewInput(question=question, evidence=evidence),
        model_tier=model_tier,
    )
    return EvidenceReview(enough_evidence=output.enough_evidence, issues=list(output.issues))
