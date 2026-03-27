from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from agent_os.app.config import InvestigationConfig
from agent_os.investigation.extract.extractor import (
    DistilledEvidence,
    extract_distilled_facts,
    review_distilled_evidence,
)
from agent_os.investigation.micro_graph.micro_graph import MicroGraph
from agent_os.investigation.query_builder.query_builder import RetrievalIntent, build_retrieval_intent
from agent_os.investigation.recall.hybrid_recall import HybridRecall, RecallCandidate
from agent_os.investigation.rerank.reranker import rerank_candidates
from agent_os.runtime.graph.engine import GraphEngine, NodeResult
from agent_os.runtime.nodes.base import NodeGateway
from agent_os.runtime.state.models import RunState


@dataclass
class InvestigationRuntimeContext:
    docs: list[tuple[str, str]]
    questions: list[str]
    round_index: int = 0
    current_question: str = ""
    intent: RetrievalIntent | None = None
    ranked_candidates: list[RecallCandidate] = field(default_factory=list)
    evidence: DistilledEvidence = field(default_factory=DistilledEvidence)
    micro_graph: MicroGraph = field(default_factory=MicroGraph)


class InvestigationSubgraphRunner:
    """Run investigation as a sub-graph on the shared GraphEngine."""

    def __init__(
        self,
        *,
        config: InvestigationConfig,
        model_gateway: NodeGateway | None = None,
        hybrid_recall: HybridRecall | None = None,
        load_documents: Callable[[RunState], list[tuple[str, str]]],
    ) -> None:
        self._config = config
        self._model_gateway = model_gateway
        self._hybrid_recall = hybrid_recall or HybridRecall()
        self._load_documents = load_documents

    def run(self, state: RunState) -> DistilledEvidence:
        docs = self._load_documents(state)
        if not docs:
            return DistilledEvidence(facts=[], source_refs=[], enough_evidence=False)

        questions = list(state.investigation.pending_questions) or [state.payload.instruction or state.goal]
        context = InvestigationRuntimeContext(docs=docs, questions=questions)

        sub_engine = GraphEngine(
            handlers={
                "inv_query": lambda sub_state: self._handle_query(sub_state, context),
                "inv_recall": lambda sub_state: self._handle_recall(sub_state, context),
                "inv_extract": lambda sub_state: self._handle_extract(sub_state, context),
                "inv_review": lambda sub_state: self._handle_review(sub_state, context),
                "inv_return": self._handle_return,
            },
            legal_edges={
                "inv_query": {"inv_recall", "inv_return"},
                "inv_recall": {"inv_extract", "inv_query", "inv_return"},
                "inv_extract": {"inv_review"},
                "inv_review": {"inv_query", "inv_return"},
                "inv_return": {"inv_return"},
            },
            increment_budget=False,
        )

        sub_state = state.model_copy(update={"current_node": "inv_query"})
        max_steps = max(4, self._config.max_rounds * 6)
        step_count = 0
        while sub_state.current_node != "inv_return" and step_count < max_steps:
            sub_state = sub_engine.run_one_step(sub_state)
            step_count += 1

        return self._build_output(context)

    def _handle_query(self, state: RunState, context: InvestigationRuntimeContext) -> NodeResult:
        max_rounds = min(len(context.questions), self._config.max_rounds)
        if context.round_index >= max_rounds:
            return NodeResult(next_node="inv_return", state_delta={})

        context.current_question = context.questions[context.round_index]
        context.intent = build_retrieval_intent(
            context.current_question,
            model_gateway=self._model_gateway,
            model_tier=state.routing.model_tier,
        )
        context.ranked_candidates = []
        context.evidence = DistilledEvidence()
        return NodeResult(next_node="inv_recall", state_delta={})

    def _handle_recall(self, _state: RunState, context: InvestigationRuntimeContext) -> NodeResult:
        if context.intent is None or not context.docs:
            return NodeResult(next_node="inv_return", state_delta={})

        candidates = self._hybrid_recall.search(intent=context.intent, documents=context.docs)
        if not candidates:
            context.round_index += 1
            if context.round_index < min(len(context.questions), self._config.max_rounds):
                return NodeResult(next_node="inv_query", state_delta={})
            return NodeResult(next_node="inv_return", state_delta={})

        context.ranked_candidates = rerank_candidates(candidates)
        return NodeResult(next_node="inv_extract", state_delta={})

    def _handle_extract(self, state: RunState, context: InvestigationRuntimeContext) -> NodeResult:
        if not context.ranked_candidates:
            return NodeResult(next_node="inv_return", state_delta={})

        context.evidence = extract_distilled_facts(
            context.ranked_candidates,
            max_facts=self._config.max_facts_per_round,
            model_gateway=self._model_gateway,
            model_tier=state.routing.model_tier,
        )

        for fact, source in zip(context.evidence.facts, context.evidence.source_refs, strict=False):
            context.micro_graph.add_support(context.current_question, fact, source)
        return NodeResult(next_node="inv_review", state_delta={})

    def _handle_review(self, state: RunState, context: InvestigationRuntimeContext) -> NodeResult:
        review = review_distilled_evidence(
            question=context.current_question,
            evidence=context.evidence,
            model_gateway=self._model_gateway,
            model_tier=state.routing.model_tier,
        )
        context.evidence = context.evidence.model_copy(update={"enough_evidence": review.enough_evidence})

        if review.enough_evidence and self._global_evidence_ready(context):
            return NodeResult(next_node="inv_return", state_delta={})

        context.round_index += 1
        if context.round_index >= min(len(context.questions), self._config.max_rounds):
            return NodeResult(next_node="inv_return", state_delta={})
        return NodeResult(next_node="inv_query", state_delta={})

    def _handle_return(self, _state: RunState) -> NodeResult:
        return NodeResult(next_node="inv_return", state_delta={})

    def _global_evidence_ready(self, context: InvestigationRuntimeContext) -> bool:
        unique_sources = list(dict.fromkeys(context.micro_graph.fact_sources.values()))
        return len(context.micro_graph.fact_sources) >= self._config.min_fact_count and len(unique_sources) >= self._config.min_source_count

    def _build_output(self, context: InvestigationRuntimeContext) -> DistilledEvidence:
        facts = list(context.micro_graph.fact_sources.keys())
        source_refs = list(dict.fromkeys(context.micro_graph.fact_sources.values()))
        enough_evidence = len(facts) >= self._config.min_fact_count and len(source_refs) >= self._config.min_source_count
        return DistilledEvidence(
            facts=facts[: self._config.max_facts_per_round],
            source_refs=source_refs[: self._config.max_facts_per_round],
            enough_evidence=enough_evidence,
        )
