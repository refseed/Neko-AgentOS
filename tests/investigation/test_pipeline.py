from __future__ import annotations

from types import SimpleNamespace

from agent_os.investigation.extract.extractor import extract_distilled_facts
from agent_os.investigation.query_builder.query_builder import build_retrieval_intent
from agent_os.investigation.recall.hybrid_recall import HybridRecall, RecallCandidate
from agent_os.investigation.rerank.reranker import rerank_candidates


def test_query_builder_creates_multiple_query_forms() -> None:
    intent = build_retrieval_intent("find baseline objective function")
    assert intent.dense_query
    assert intent.sparse_keywords
    assert isinstance(intent.fuzzy_terms, list)


def test_investigation_pipeline_returns_distilled_facts() -> None:
    recall = HybridRecall()
    intent = build_retrieval_intent("flow matching baseline objective")
    documents = [
        ("doc1", "Flow Matching baseline objective uses a transport loss."),
        ("doc2", "Unrelated note."),
    ]
    candidates = recall.search(intent, documents)
    ranked = rerank_candidates(candidates)
    evidence = extract_distilled_facts(ranked)
    assert evidence.enough_evidence is True
    assert evidence.facts


def test_query_builder_and_extractor_can_use_model_json() -> None:
    class FakeGateway:
        def request(self, prompt: str, model_tier: str):
            if "search-query-construction node" in prompt:
                return SimpleNamespace(
                    text='{"intent":"model_intent","dense_query":"dq","sparse_keywords":["a"],"fuzzy_terms":["a"],"exact_terms":[],"filters":{"source_type":"local"}}'
                )
            return SimpleNamespace(text='{"facts":["fact from model"],"source_refs":["doc1"],"enough_evidence":true}')

    intent = build_retrieval_intent("find baseline objective function", model_gateway=FakeGateway(), model_tier="small")
    assert intent.intent == "model_intent"

    candidates = [RecallCandidate(source_id="doc1", text="candidate text", score=1.0)]
    evidence = extract_distilled_facts(candidates, model_gateway=FakeGateway(), model_tier="small")
    assert evidence.facts == ["fact from model"]
