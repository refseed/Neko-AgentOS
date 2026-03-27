from __future__ import annotations

from logging import Logger
from typing import Callable, Iterable

from agent_os.app.config import ReflectionConfig
from agent_os.cognition.memory_router.memory_router import MemoryMount
from agent_os.cognition.prompt_builder.builder import build_reflection_prompt
from agent_os.cognition.reasoning.reasoning_node import ReasoningNode, ReasoningResult
from agent_os.cognition.reflection.reflection_node import ReflectionInput, ReflectionNode
from agent_os.investigation.extract.extractor import DistilledEvidence
from agent_os.memory.compression.compressor import compress_text
from agent_os.memory.disk.semantic_disk import SemanticDisk
from agent_os.memory.ram.working_ram import WorkingRam
from agent_os.models.gateway.client import ModelGatewayClient
from agent_os.observability.tracing.trace_logger import TraceLogger
from agent_os.runtime.checkpoint.repository import CheckpointRepository
from agent_os.runtime.epistemic_guard.guard import EpistemicGuard
from agent_os.runtime.graph.engine import NodeResult
from agent_os.runtime.routing.capability_router import CapabilityRouter
from agent_os.runtime.routing.meta_router import MetaRouter
from agent_os.runtime.state.blueprint_models import BlueprintGraph
from agent_os.runtime.state.models import BreakState, MemoryRefs, RunState, UncertaintyState
from agent_os.tools.capability_loader.loader import CapabilityLoader


class InteractionRuntimeNode:
    def __init__(
        self,
        *,
        trace_logger: TraceLogger,
        record_event: Callable[[str, str, dict[str, object]], str],
        append_cache_ref: Callable[[RunState, str], MemoryRefs],
    ) -> None:
        self._trace_logger = trace_logger
        self._record_event = record_event
        self._append_cache_ref = append_cache_ref

    def handle(self, state: RunState) -> NodeResult:
        self._trace_logger.log(state.audit.trace_id, "node_start", "interaction")
        cache_ref = self._record_event(state.run_id, "interaction", {"node": "interaction"})
        delta = {
            "status": "running",
            "memory": self._append_cache_ref(state, cache_ref),
            "uncertainty": UncertaintyState(status="none", type=None, question_for_user=None, blocked_by=[]),
            "break_state": BreakState(),
        }
        return NodeResult(next_node="strategist", state_delta=delta)


class StrategistRuntimeNode:
    def __init__(
        self,
        *,
        trace_logger: TraceLogger,
        record_event: Callable[[str, str, dict[str, object]], str],
        append_cache_ref: Callable[[RunState, str], MemoryRefs],
        meta_router: MetaRouter,
        mount_memory_context: Callable[[RunState, list[MemoryMount]], list[str]],
        capability_router: CapabilityRouter,
        capability_loader: CapabilityLoader,
        legal_targets_getter: Callable[[str], set[str]],
    ) -> None:
        self._trace_logger = trace_logger
        self._record_event = record_event
        self._append_cache_ref = append_cache_ref
        self._meta_router = meta_router
        self._mount_memory_context = mount_memory_context
        self._capability_router = capability_router
        self._capability_loader = capability_loader
        self._legal_targets_getter = legal_targets_getter

    def handle(self, state: RunState) -> NodeResult:
        self._trace_logger.log(state.audit.trace_id, "node_start", "strategist")
        cache_ref = self._record_event(
            state.run_id,
            "strategist",
            {"stage": state.blueprint.active_node, "stage_status": state.blueprint.stage_status},
        )
        allowed_targets = self._legal_targets_getter(state.current_node)
        routing_decision = self._meta_router.route(state=state, allowed_targets=allowed_targets)
        mounted_memory = self._mount_memory_context(state=state, mounts=routing_decision.memory_mounts)
        capability_route = self._capability_router.route(state=state, next_node=routing_decision.next_node)
        capability = self._capability_loader.load(
            node_type=capability_route.node_type,
            permission_level=capability_route.permission_level,
        )

        uncertainty = state.uncertainty
        if routing_decision.next_node == "break" and uncertainty.status != "blocked":
            reason = routing_decision.guardrail_flags[0] if routing_decision.guardrail_flags else "low_confidence_routing"
            uncertainty_type = "budget_exceeded" if "max_" in reason else "low_confidence_routing"
            uncertainty = UncertaintyState(
                status="blocked",
                type=uncertainty_type,
                question_for_user="Should I continue with relaxed limits or stop here for manual review?",
                blocked_by=[reason],
            )

        delta = {
            "memory": self._append_cache_ref(state, cache_ref),
            "routing": state.routing.model_copy(
                update={
                    "confidence": routing_decision.confidence,
                    "candidate_nodes": [routing_decision.next_node],
                    "deterministic": routing_decision.confidence >= 0.95,
                    "tool_profile": routing_decision.tool_profile,
                    "model_tier": routing_decision.model_tier,
                    "guardrail_flags": routing_decision.guardrail_flags,
                }
            ),
            "payload": state.payload.model_copy(update={"memory_context": mounted_memory}),
            "capabilities": state.capabilities.model_copy(
                update={
                    "loaded_tools": [tool.name for tool in capability.loaded],
                    "withheld_tools": [tool.name for tool in capability.withheld],
                    "load_reason": capability_route.reason,
                }
            ),
            "uncertainty": uncertainty,
        }
        return NodeResult(next_node=routing_decision.next_node, state_delta=delta)


class BlueprintRuntimeNode:
    def __init__(
        self,
        *,
        trace_logger: TraceLogger,
        record_event: Callable[[str, str, dict[str, object]], str],
        append_cache_ref: Callable[[RunState, str], MemoryRefs],
        blueprint_graph: BlueprintGraph,
    ) -> None:
        self._trace_logger = trace_logger
        self._record_event = record_event
        self._append_cache_ref = append_cache_ref
        self._blueprint_graph = blueprint_graph

    def handle(self, state: RunState) -> NodeResult:
        self._trace_logger.log(state.audit.trace_id, "node_start", "blueprint")
        cache_ref = self._record_event(
            state.run_id,
            "blueprint",
            {"active_node": state.blueprint.active_node, "stage_status": state.blueprint.stage_status},
        )
        blueprint = state.blueprint
        payload = state.payload
        next_node = "strategist"
        uncertainty = state.uncertainty

        current_stage = self._blueprint_graph.nodes.get(blueprint.active_node)
        if current_stage is None:
            uncertainty = UncertaintyState(
                status="blocked",
                type="conflicting_evidence",
                question_for_user=f"Blueprint stage '{blueprint.active_node}' not found. Please choose a valid stage.",
                blocked_by=["blueprint_stage_missing"],
            )
            return NodeResult(
                next_node="break",
                state_delta={
                    "memory": self._append_cache_ref(state, cache_ref),
                    "uncertainty": uncertainty,
                },
            )

        payload = payload.model_copy(update={"instruction": current_stage.goal})

        if not blueprint.enabled:
            blueprint = blueprint.model_copy(
                update={
                    "enabled": True,
                    "active_node": current_stage.node_id,
                    "allowed_exits": current_stage.allowed_exits,
                    "subgraph_template": current_stage.subgraph_template,
                    "stage_status": "pending",
                    "stage_attempts": 0,
                }
            )
            payload = payload.model_copy(
                update={
                    "instruction": current_stage.goal,
                    "draft_text": "",
                    "stage_result": "",
                    "memory_context": [],
                }
            )
            delta = {
                "memory": self._append_cache_ref(state, cache_ref),
                "blueprint_ref": self._blueprint_graph.graph_id,
                "blueprint_stage": blueprint.active_node,
                "blueprint": blueprint,
                "payload": payload,
                "uncertainty": uncertainty,
            }
            return NodeResult(next_node="strategist", state_delta=delta)

        if blueprint.active_node == "done":
            next_node = "finish"
        elif blueprint.stage_status == "approved":
            result_key = state.payload.stage_result or "approved"
            next_stage = self._blueprint_graph.resolve_next_stage(blueprint.active_node, result_key)
            if next_stage is None and current_stage.allowed_exits:
                next_stage = current_stage.allowed_exits[0]
            if next_stage is None:
                next_stage = "done"
            if next_stage not in self._blueprint_graph.nodes:
                uncertainty = UncertaintyState(
                    status="blocked",
                    type="conflicting_evidence",
                    question_for_user=f"Blueprint transition target '{next_stage}' is invalid.",
                    blocked_by=["blueprint_transition_invalid"],
                )
                next_node = "break"
            else:
                next_bp = self._blueprint_graph.nodes[next_stage]
                blueprint = blueprint.model_copy(
                    update={
                        "enabled": True,
                        "active_node": next_bp.node_id,
                        "allowed_exits": next_bp.allowed_exits,
                        "subgraph_template": next_bp.subgraph_template,
                        "stage_status": "pending",
                        "stage_attempts": 0,
                    }
                )
                payload = payload.model_copy(
                    update={
                        "instruction": next_bp.goal,
                        "draft_text": "",
                        "stage_result": "",
                        "memory_context": [],
                    }
                )
                next_node = "finish" if next_bp.node_id == "done" else "strategist"

        delta = {
            "memory": self._append_cache_ref(state, cache_ref),
            "blueprint_ref": self._blueprint_graph.graph_id,
            "blueprint_stage": blueprint.active_node,
            "blueprint": blueprint,
            "payload": payload,
            "uncertainty": uncertainty,
        }
        return NodeResult(next_node=next_node, state_delta=delta)


class ReasoningRuntimeNode:
    def __init__(
        self,
        *,
        trace_logger: TraceLogger,
        record_event: Callable[[str, str, dict[str, object]], str],
        append_cache_ref: Callable[[RunState, str], MemoryRefs],
        append_refs: Callable[[Iterable[str], str], list[str]],
        reasoning_node: ReasoningNode,
        working_ram: WorkingRam,
    ) -> None:
        self._trace_logger = trace_logger
        self._record_event = record_event
        self._append_cache_ref = append_cache_ref
        self._append_refs = append_refs
        self._reasoning_node = reasoning_node
        self._working_ram = working_ram

    def handle(self, state: RunState) -> NodeResult:
        self._trace_logger.log(state.audit.trace_id, "node_start", "reasoning")
        cache_ref = self._record_event(state.run_id, "reasoning", {"stage": state.blueprint.active_node})
        reasoning_result = self._reasoning_node.run(state)
        ram_ref = self._working_ram.put(state.run_id, "latest_draft", reasoning_result.draft_text)
        total_tokens = state.budget.token_used + reasoning_result.input_tokens + reasoning_result.output_tokens

        pending_questions = (
            list(reasoning_result.missing_questions)
            if reasoning_result.needs_investigation
            else list(state.investigation.pending_questions)
        )
        stage_status = "need_more_evidence" if reasoning_result.needs_investigation else "in_progress"

        memory_with_cache = self._append_cache_ref(state, cache_ref)
        ram_refs = self._append_refs(memory_with_cache.ram_refs, ram_ref)

        delta = {
            "memory": memory_with_cache.model_copy(update={"ram_refs": ram_refs}),
            "payload": state.payload.model_copy(
                update={
                    "draft_text": reasoning_result.draft_text,
                    "memory_context": [],
                }
            ),
            "budget": state.budget.model_copy(update={"token_used": total_tokens}),
            "investigation": state.investigation.model_copy(
                update={
                    "active": reasoning_result.needs_investigation,
                    "pending_questions": pending_questions,
                    "enough_evidence": not reasoning_result.needs_investigation,
                }
            ),
            "blueprint": state.blueprint.model_copy(
                update={
                    "stage_status": stage_status,
                    "stage_attempts": state.blueprint.stage_attempts + 1,
                }
            ),
        }
        return NodeResult(next_node="strategist", state_delta=delta)


class InvestigationRuntimeNode:
    def __init__(
        self,
        *,
        trace_logger: TraceLogger,
        record_event: Callable[[str, str, dict[str, object]], str],
        append_cache_ref: Callable[[RunState, str], MemoryRefs],
        investigate: Callable[[RunState], DistilledEvidence],
        semantic_disk: SemanticDisk,
        model_gateway: ModelGatewayClient,
    ) -> None:
        self._trace_logger = trace_logger
        self._record_event = record_event
        self._append_cache_ref = append_cache_ref
        self._investigate = investigate
        self._semantic_disk = semantic_disk
        self._model_gateway = model_gateway

    def handle(self, state: RunState) -> NodeResult:
        self._trace_logger.log(state.audit.trace_id, "node_start", "investigation")
        cache_ref = self._record_event(state.run_id, "investigation", {"questions": state.investigation.pending_questions})
        evidence = self._investigate(state)

        memory_with_cache = self._append_cache_ref(state, cache_ref)
        accepted_facts = list(dict.fromkeys([*state.payload.accepted_facts, *evidence.facts]))
        source_refs = list(dict.fromkeys([*state.payload.source_refs, *evidence.source_refs]))

        disk_refs = list(memory_with_cache.disk_refs)
        for fact in evidence.facts:
            compression_pack = compress_text(
                fact,
                model_gateway=self._model_gateway,
                model_tier=state.routing.model_tier,
            )
            disk_refs.append(
                self._semantic_disk.save_memory(
                    run_id=state.run_id,
                    text=fact,
                    metadata={"source": "investigation", "stage": state.blueprint.active_node},
                    compression_pack=compression_pack,
                )
            )
        disk_refs = list(dict.fromkeys(disk_refs))

        if evidence.enough_evidence:
            uncertainty = UncertaintyState(status="none", type=None, question_for_user=None, blocked_by=[])
            investigation_state = state.investigation.model_copy(
                update={
                    "active": False,
                    "pending_questions": [],
                    "enough_evidence": True,
                }
            )
            blueprint = state.blueprint.model_copy(update={"stage_status": "retry"})
        else:
            uncertainty = UncertaintyState(
                status="blocked",
                type="missing_evidence",
                question_for_user="I still need source-backed evidence. Please provide at least one relevant source file path.",
                blocked_by=["no_evidence"],
            )
            investigation_state = state.investigation.model_copy(
                update={
                    "active": True,
                    "pending_questions": state.investigation.pending_questions
                    or ["Need source-backed evidence for current stage."],
                    "enough_evidence": False,
                }
            )
            blueprint = state.blueprint.model_copy(update={"stage_status": "need_more_evidence"})

        delta = {
            "memory": memory_with_cache.model_copy(update={"disk_refs": disk_refs}),
            "payload": state.payload.model_copy(
                update={
                    "accepted_facts": accepted_facts,
                    "source_refs": source_refs,
                    "memory_context": [],
                }
            ),
            "investigation": investigation_state,
            "blueprint": blueprint,
            "uncertainty": uncertainty,
        }
        return NodeResult(next_node="strategist", state_delta=delta)


class ReflectionRuntimeNode:
    def __init__(
        self,
        *,
        trace_logger: TraceLogger,
        record_event: Callable[[str, str, dict[str, object]], str],
        append_cache_ref: Callable[[RunState, str], MemoryRefs],
        reflection_node: ReflectionNode,
        blueprint_graph: BlueprintGraph,
        reflection_config: ReflectionConfig,
        model_gateway: ModelGatewayClient,
    ) -> None:
        self._trace_logger = trace_logger
        self._record_event = record_event
        self._append_cache_ref = append_cache_ref
        self._reflection_node = reflection_node
        self._blueprint_graph = blueprint_graph
        self._reflection_config = reflection_config
        self._model_gateway = model_gateway

    def handle(self, state: RunState) -> NodeResult:
        self._trace_logger.log(state.audit.trace_id, "node_start", "reflection")
        checklist = self._blueprint_graph.nodes[state.blueprint.active_node].checklist
        reflection_prompt = build_reflection_prompt(
            state=state,
            draft_text=state.payload.draft_text,
            checklist=checklist,
            model_gateway=self._model_gateway,
            model_tier=state.routing.model_tier,
        )
        cache_ref = self._record_event(
            state.run_id,
            "reflection",
            {"stage": state.blueprint.active_node, "prompt_preview": reflection_prompt[:200]},
        )
        draft = ReasoningResult(
            draft_text=state.payload.draft_text,
            needs_investigation=state.investigation.active,
            missing_questions=list(state.investigation.pending_questions),
        )
        review_input = ReflectionInput(
            stage=state.blueprint.active_node,
            stage_goal=self._blueprint_graph.nodes[state.blueprint.active_node].goal,
            checklist=checklist,
            accepted_facts=list(state.payload.accepted_facts),
            source_refs=list(state.payload.source_refs),
            required_output=state.payload.output_format,
            review_iteration=state.blueprint.stage_attempts,
            max_review_loops=self._reflection_config.max_review_loops,
            min_draft_chars=self._reflection_config.min_draft_chars,
        )
        verdict = self._reflection_node.review(
            review_input=review_input,
            draft=draft,
            model_tier=state.routing.model_tier,
        )

        if verdict.status == "approved":
            stage_status = "approved"
        elif verdict.status == "need_more_evidence":
            stage_status = "need_more_evidence"
        else:
            stage_status = "retry"

        investigation_state = state.investigation
        if verdict.status == "need_more_evidence":
            pending_questions = list(dict.fromkeys([*state.investigation.pending_questions, *verdict.missing_questions]))
            investigation_state = state.investigation.model_copy(
                update={
                    "active": True,
                    "pending_questions": pending_questions,
                    "enough_evidence": False,
                }
            )
        elif verdict.status == "approved":
            investigation_state = state.investigation.model_copy(
                update={
                    "active": False,
                    "pending_questions": [],
                    "enough_evidence": state.investigation.enough_evidence,
                }
            )

        delta = {
            "memory": self._append_cache_ref(state, cache_ref),
            "payload": state.payload.model_copy(update={"stage_result": verdict.status}),
            "blueprint": state.blueprint.model_copy(update={"stage_status": stage_status}),
            "investigation": investigation_state,
        }
        return NodeResult(next_node="strategist", state_delta=delta)


class BreakRuntimeNode:
    def __init__(
        self,
        *,
        trace_logger: TraceLogger,
        record_event: Callable[[str, str, dict[str, object]], str],
        append_cache_ref: Callable[[RunState, str], MemoryRefs],
        checkpoint_repo: CheckpointRepository,
        epistemic_guard: EpistemicGuard,
        logger: Logger,
    ) -> None:
        self._trace_logger = trace_logger
        self._record_event = record_event
        self._append_cache_ref = append_cache_ref
        self._checkpoint_repo = checkpoint_repo
        self._epistemic_guard = epistemic_guard
        self._logger = logger

    def handle(self, state: RunState) -> NodeResult:
        self._trace_logger.log(state.audit.trace_id, "node_start", "break")
        cache_ref = self._record_event(state.run_id, "break", {"reason": state.uncertainty.type})
        checkpoint_id = self._checkpoint_repo.save(state)
        uncertainty_type = state.uncertainty.type or "user_input_required"
        report = self._epistemic_guard.build_break_report(
            state,
            uncertainty_type=uncertainty_type,  # type: ignore[arg-type]
        )
        self._logger.info("Run paused | run_id=%s | question=%s", state.run_id, report.question_for_user)
        delta = {
            "memory": self._append_cache_ref(state, cache_ref),
            "status": "paused",
            "checkpoint": state.checkpoint.model_copy(
                update={
                    "last_checkpoint_id": checkpoint_id,
                    "can_resume": True,
                }
            ),
            "break_state": BreakState(
                uncertainty_type=report.uncertainty_type,
                known_now=report.known_now,
                missing_now=report.missing_now,
                question_for_user=report.question_for_user,
            ),
        }
        return NodeResult(next_node="finish", state_delta=delta)


class FinishRuntimeNode:
    def __init__(self, *, trace_logger: TraceLogger) -> None:
        self._trace_logger = trace_logger

    def handle(self, state: RunState) -> NodeResult:
        self._trace_logger.log(state.audit.trace_id, "node_end", "finish")
        final_status = "completed" if state.status == "running" else state.status
        return NodeResult(next_node="finish", state_delta={"status": final_status})
