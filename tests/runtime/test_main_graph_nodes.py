from __future__ import annotations

from pathlib import Path

import pytest

from agent_os.cognition.clarification.question_node import ClarificationQuestionError
from agent_os.investigation.extract.extractor import DistilledEvidence
from agent_os.memory.disk.semantic_disk import SemanticDisk
from agent_os.models.providers.litellm_provider import EmptyModelResponseError
from agent_os.runtime.graph.blueprint_loader import build_blueprint_graph
from agent_os.runtime.nodes.main_graph_nodes import (
    BlueprintRuntimeNode,
    InvestigationRuntimeNode,
    StrategistRuntimeNode,
)
from agent_os.runtime.routing.capability_router import CapabilityRouter
from agent_os.runtime.state.models import BlueprintState, InvestigationState, PayloadState, RunState, UncertaintyState
from agent_os.tools.capability_loader.loader import CapabilityLoader
from agent_os.tools.registry.registry import ToolRegistry, ToolSpec


class _TraceStub:
    def log(self, *_args, **_kwargs) -> None:
        return None


def test_blueprint_runtime_node_breaks_on_missing_transition_mapping() -> None:
    graph = build_blueprint_graph()
    node = BlueprintRuntimeNode(
        trace_logger=_TraceStub(),
        record_event=lambda _run_id, _event_type, _details: "cache:bp",
        append_cache_ref=lambda state, _cache_ref: state.memory,
        blueprint_graph=graph,
    )

    state = RunState(
        run_id="run_bp",
        task_id="task_bp",
        goal="demo",
        current_node="blueprint",
        blueprint=BlueprintState(
            enabled=True,
            active_node="idea_summary",
            stage_status="approved",
            subgraph_template="reason_reflect_loop",
            allowed_exits=["writing_plan", "literature_scan"],
        ),
        payload=PayloadState(stage_result="unknown_result"),
    )

    result = node.handle(state)
    assert result.next_node == "break"
    uncertainty = result.state_delta["uncertainty"]
    assert uncertainty.type == "conflicting_evidence"
    assert "blueprint_transition_missing" in uncertainty.blocked_by


def test_strategist_runtime_node_constrains_allowed_targets_by_template() -> None:
    graph = build_blueprint_graph()

    class _MetaRouterStub:
        def __init__(self) -> None:
            self.allowed_targets: set[str] = set()

        def route(self, state: RunState, allowed_targets: set[str] | None = None):
            self.allowed_targets = set(allowed_targets or set())
            from agent_os.cognition.strategist.strategist import RoutingDecision

            return RoutingDecision(
                next_node="reasoning",
                confidence=0.9,
                tool_profile="reasoning_readonly",
                model_tier="small",
            )

    meta_router = _MetaRouterStub()
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="read_local_text",
            description="read",
            permission_level="readonly",
            handler=lambda _ctx, _payload: {"content": ""},
        )
    )

    node = StrategistRuntimeNode(
        trace_logger=_TraceStub(),
        record_event=lambda _run_id, _event_type, _details: "cache:st",
        append_cache_ref=lambda state, _cache_ref: state.memory,
        meta_router=meta_router,  # type: ignore[arg-type]
        mount_memory_context=lambda state, mounts: [],
        capability_router=CapabilityRouter(),
        capability_loader=CapabilityLoader(registry=registry),
        legal_targets_getter=lambda _source: {"reasoning", "reflection", "investigation", "finish"},
        template_target_filter=lambda state, targets: graph.constrain_runtime_targets(
            state.blueprint.subgraph_template,
            targets,
        ),
    )

    state = RunState(
        run_id="run_st",
        task_id="task_st",
        goal="demo",
        current_node="strategist",
        blueprint=BlueprintState(
            enabled=True,
            active_node="writing_plan",
            subgraph_template="compose_outline",
            allowed_exits=["done", "idea_summary"],
        ),
    )

    result = node.handle(state)
    assert result.next_node == "reasoning"
    assert meta_router.allowed_targets == {"reasoning", "reflection"}


def test_investigation_runtime_node_propagates_clarification_error(tmp_path: Path) -> None:
    """When the model persistently returns empty text, the error must propagate
    (no silent fallback) so the user is informed of the issue."""

    class _GatewayStub:
        def request(self, prompt, model_tier="small"):
            raise EmptyModelResponseError(
                "Model returned empty text after all retries | model=test | tier=small"
            )

    node = InvestigationRuntimeNode(
        trace_logger=_TraceStub(),
        record_event=lambda _run_id, _event_type, _details: "cache:inv",
        append_cache_ref=lambda state, _cache_ref: state.memory,
        investigate=lambda _state: DistilledEvidence(facts=[], source_refs=[], enough_evidence=False),
        semantic_disk=SemanticDisk(root_dir=tmp_path / "disk"),
        model_gateway=_GatewayStub(),
        clarification_max_parse_retries=0,
    )

    state = RunState(
        run_id="run_inv",
        task_id="task_inv",
        goal="我需要洗车，洗车店离家100米",
        current_node="investigation",
        investigation=InvestigationState(active=True, pending_questions=[], enough_evidence=False),
        uncertainty=UncertaintyState(status="none", type=None),
    )

    with pytest.raises(ClarificationQuestionError, match="model request failed"):
        node.handle(state)
