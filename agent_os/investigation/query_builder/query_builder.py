from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_os.runtime.nodes.base import BaseLLMNode, NodeEnvelopeMixin, NodeGateway


class RetrievalIntent(BaseModel):
    """Describe what the investigation step is trying to find."""

    model_config = ConfigDict(extra="forbid")

    intent: str
    dense_query: str
    sparse_keywords: list[str] = Field(default_factory=list)
    fuzzy_terms: list[str] = Field(default_factory=list)
    exact_terms: list[str] = Field(default_factory=list)
    filters: dict[str, object] = Field(default_factory=dict)


class SearchIntentInput(BaseModel):
    """Protocol input for search intent builder node."""

    model_config = ConfigDict(extra="forbid")

    goal: str


class SearchIntentOutput(NodeEnvelopeMixin):
    """Protocol output for search intent builder node."""

    node_name: str = "search_intent_builder"
    intent: str
    dense_query: str
    sparse_keywords: list[str] = Field(default_factory=list)
    fuzzy_terms: list[str] = Field(default_factory=list)
    exact_terms: list[str] = Field(default_factory=list)
    filters: dict[str, object] = Field(default_factory=dict)


class SearchIntentNode(BaseLLMNode[SearchIntentInput, SearchIntentOutput]):
    """Model-driven search intent construction node."""

    @property
    def output_model(self) -> type[SearchIntentOutput]:
        return SearchIntentOutput

    def _fallback_intent(self, goal: str) -> RetrievalIntent:
        words = [word.strip(".,:;!?").lower() for word in goal.split() if word.strip()]
        keywords = list(dict.fromkeys(words[:8]))
        return RetrievalIntent(
            intent="goal_grounding",
            dense_query=goal,
            sparse_keywords=keywords,
            fuzzy_terms=keywords[:4],
            exact_terms=[word for word in words if "_" in word or "-" in word],
            filters={"source_type": "local"},
        )

    def fallback(self, node_input: SearchIntentInput) -> SearchIntentOutput:
        fallback = self._fallback_intent(node_input.goal)
        return SearchIntentOutput(
            protocol_version="node-io/v1",
            node_name="search_intent_builder",
            confidence=0.7,
            notes=["fallback_heuristic"],
            intent=fallback.intent,
            dense_query=fallback.dense_query,
            sparse_keywords=fallback.sparse_keywords,
            fuzzy_terms=fallback.fuzzy_terms,
            exact_terms=fallback.exact_terms,
            filters=fallback.filters,
        )

    def build_prompt(self, node_input: SearchIntentInput) -> str:
        return (
            "You are the search-query-construction node.\n"
            "Build a retrieval intent for investigation.\n"
            "Protocol:\n"
            "- Return strict JSON only.\n"
            "- Required keys: protocol_version, node_name, confidence, notes, intent, dense_query, sparse_keywords, fuzzy_terms, exact_terms, filters.\n"
            "- protocol_version must be 'node-io/v1'.\n"
            "- node_name must be 'search_intent_builder'.\n"
            f"goal: {node_input.goal}\n"
        )


def build_retrieval_intent(
    goal: str,
    model_gateway: NodeGateway | None = None,
    model_tier: str = "small",
) -> RetrievalIntent:
    node = SearchIntentNode(node_name="search_intent_builder", model_gateway=model_gateway)
    output = node.run(
        SearchIntentInput(goal=goal),
        model_tier=model_tier,
    )
    return RetrievalIntent(
        intent=output.intent,
        dense_query=output.dense_query,
        sparse_keywords=list(output.sparse_keywords),
        fuzzy_terms=list(output.fuzzy_terms),
        exact_terms=list(output.exact_terms),
        filters=dict(output.filters),
    )
