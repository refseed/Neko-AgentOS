from __future__ import annotations

from pathlib import Path
from typing import Iterable
from uuid import uuid4

from agent_os.app.config import AgentConfig, load_agent_config
from agent_os.app.schemas.requests import ResumeRunRequest, StartRunRequest
from agent_os.cognition.memory_router.memory_router import MemoryMount
from agent_os.cognition.prompt_builder.builder import build_reasoning_prompt, build_reflection_prompt
from agent_os.cognition.reasoning.reasoning_node import ReasoningNode, ReasoningResult
from agent_os.cognition.reflection.reflection_node import ReflectionInput, ReflectionNode
from agent_os.cognition.resource_manager.resource_manager import ResourceManager
from agent_os.cognition.strategist.strategist import Strategist
from agent_os.investigation.extract.extractor import DistilledEvidence, extract_distilled_facts, review_distilled_evidence
from agent_os.investigation.micro_graph.micro_graph import MicroGraph
from agent_os.investigation.query_builder.query_builder import build_retrieval_intent
from agent_os.investigation.recall.hybrid_recall import HybridRecall
from agent_os.investigation.rerank.reranker import rerank_candidates
from agent_os.memory.blackboard.global_blackboard import GlobalBlackboard
from agent_os.memory.cache.episodic_cache import EpisodicCache
from agent_os.memory.compression.compressor import compress_text, keep_cache_refs
from agent_os.memory.disk.semantic_disk import SemanticDisk
from agent_os.memory.ram.working_ram import WorkingRam
from agent_os.models.gateway.client import ModelGatewayClient
from agent_os.models.providers.factory import build_model_provider
from agent_os.observability.logging.app_logger import build_app_logger
from agent_os.observability.metrics.metrics import MetricsStore
from agent_os.observability.tracing.trace_logger import TraceLogger
from agent_os.runtime.checkpoint.repository import CheckpointRepository
from agent_os.runtime.epistemic_guard.guard import EpistemicGuard
from agent_os.runtime.graph.blueprint_loader import build_blueprint_graph
from agent_os.runtime.graph.edges import build_main_graph_edges
from agent_os.runtime.graph.engine import GraphEngine, NodeResult
from agent_os.runtime.routing.capability_router import CapabilityRouter
from agent_os.runtime.routing.meta_router import MetaRouter
from agent_os.runtime.state.models import (
    BreakState,
    BlueprintState,
    BudgetState,
    PayloadState,
    RunState,
    UncertaintyState,
)
from agent_os.tools.capability_loader.loader import CapabilityLoader
from agent_os.tools.registry.registry import ToolRegistry, ToolSpec
from agent_os.tools.runtime.tool_runtime import ToolRuntime
from agent_os.tools.sandbox.sandbox import ToolSandbox


class AgentOrchestrator:
    """Coordinates runtime components for start and resume flows."""

    def __init__(self, workspace_root: Path, config_path: Path | None = None) -> None:
        self._workspace_root = workspace_root
        self._config: AgentConfig = load_agent_config(workspace_root=workspace_root, config_path=config_path)

        data_root = self._resolve_path(self._config.runtime.data_dir)
        data_root.mkdir(parents=True, exist_ok=True)
        self._data_root = data_root

        self._logger = build_app_logger()
        self._trace_logger = TraceLogger(self._resolve_data_path(self._config.runtime.trace_dir))
        self._trace_ids: dict[str, str] = {}

        self._metrics = MetricsStore()
        self._checkpoint_repo = CheckpointRepository(
            db_path=self._resolve_data_path(self._config.runtime.checkpoint_db),
            snapshot_dir=self._resolve_data_path(self._config.runtime.snapshot_dir),
        )
        self._semantic_disk = SemanticDisk(self._resolve_data_path(self._config.runtime.semantic_disk_dir))
        self._working_ram = WorkingRam()
        self._global_blackboard = GlobalBlackboard(constants=dict(self._config.blackboard.constants))
        self._epistemic_guard = EpistemicGuard()
        self._blueprint_graph = build_blueprint_graph()

        self._resource_manager = ResourceManager()
        self._model_gateway = ModelGatewayClient(build_model_provider(self._config.model))
        self._strategist = Strategist(
            model_gateway=self._model_gateway,
            blueprint_entry_keywords=self._config.blueprint.entry_keywords,
        )
        self._meta_router = MetaRouter(
            strategist=self._strategist,
            resource_manager=self._resource_manager,
        )
        self._capability_router = CapabilityRouter(
            permission_by_node=self._config.capability.permission_by_node,
        )
        self._episodic_cache = EpisodicCache()
        self._reasoning_node = ReasoningNode(
            prompt_builder=lambda run_state: build_reasoning_prompt(
                run_state,
                model_gateway=self._model_gateway,
                model_tier=run_state.routing.model_tier,
            ),
            model_gateway=self._model_gateway,
        )
        self._reflection_node = ReflectionNode(model_gateway=self._model_gateway)
        self._hybrid_recall = HybridRecall()

        registry = ToolRegistry()
        registry.register(
            ToolSpec(
                name="read_local_text",
                description="Read local text files",
                permission_level="readonly",
                handler=self._read_local_text_tool,
            )
        )
        registry.register(
            ToolSpec(
                name="write_local_file",
                description="Write local files",
                permission_level="write",
                handler=lambda _ctx, payload: {"written": bool(payload)},
            )
        )
        self._capability_loader = CapabilityLoader(registry=registry)
        self._tool_runtime = ToolRuntime(
            registry=registry,
            sandbox=ToolSandbox(allowed_roots=[self._workspace_root.resolve(), self._data_root.resolve()]),
            audit_callback=self._emit_tool_event,
        )

        self._engine = GraphEngine(
            handlers={
                "interaction": self._handle_interaction,
                "strategist": self._handle_strategist,
                "blueprint": self._handle_blueprint,
                "reasoning": self._handle_reasoning,
                "investigation": self._handle_investigation,
                "reflection": self._handle_reflection,
                "break": self._handle_break,
                "finish": self._handle_finish,
            },
            legal_edges=build_main_graph_edges(),
        )

    def start_run(self, request: StartRunRequest) -> dict[str, object]:
        run_id = f"run_{uuid4().hex[:12]}"
        start_node = self._blueprint_graph.nodes[self._blueprint_graph.start_node]
        blueprint_enabled = self._config.blueprint.enabled_by_default
        instruction = start_node.goal if blueprint_enabled else request.goal
        initial_state = RunState(
            run_id=run_id,
            task_id=f"task_{uuid4().hex[:12]}",
            goal=request.goal,
            blueprint_ref=self._blueprint_graph.graph_id,
            blueprint_stage=self._blueprint_graph.start_node,
            payload=PayloadState(
                instruction=instruction,
                source_refs=list(request.source_paths),
            ),
            blueprint=BlueprintState(
                enabled=blueprint_enabled,
                ref=self._blueprint_graph.graph_id,
                active_node=self._blueprint_graph.start_node,
                allowed_exits=start_node.allowed_exits,
                subgraph_template=start_node.subgraph_template,
                stage_status="pending",
            ),
            budget=BudgetState(
                max_steps=self._config.runtime.max_steps,
                max_retries=self._config.runtime.max_retries,
            ),
        )
        self._trace_ids[run_id] = initial_state.audit.trace_id
        return self._run_until_stop(initial_state)

    def resume_run(self, request: ResumeRunRequest) -> dict[str, object]:
        state = self._checkpoint_repo.load_latest(request.run_id)
        if state is None:
            return {"status": "error", "message": f"run_id not found: {request.run_id}"}

        accepted_facts = list(state.payload.accepted_facts)
        if request.user_answer:
            accepted_facts.append(f"user_input: {request.user_answer}")
        resumed = state.model_copy(
            update={
                "status": "running",
                "current_node": "interaction",
                "payload": state.payload.model_copy(update={"accepted_facts": accepted_facts}),
                "uncertainty": UncertaintyState(status="none", type=None, question_for_user=None, blocked_by=[]),
                "break_state": BreakState(),
            }
        )
        self._trace_ids[resumed.run_id] = resumed.audit.trace_id
        return self._run_until_stop(resumed)

    def _resolve_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return self._workspace_root / path

    def _resolve_data_path(self, raw_path: str) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        return self._data_root / path

    def _run_until_stop(self, initial_state: RunState) -> dict[str, object]:
        state = initial_state
        steps = 0
        while state.current_node != "finish" and state.status == "running":
            steps += 1
            if steps > self._config.runtime.max_node_iterations:
                state = state.model_copy(
                    update={
                        "status": "failed",
                        "uncertainty": UncertaintyState(
                            status="blocked",
                            type="budget_exceeded",
                            question_for_user="Node iteration limit reached; review routing constraints before retry.",
                            blocked_by=["max_node_iterations"],
                        ),
                        "current_node": "finish",
                    }
                )
                break
            state = self._engine.run_one_step(state)
            self._trace_ids[state.run_id] = state.audit.trace_id

        if state.current_node == "finish":
            state = self._engine.run_one_step(state)

        break_report: dict[str, object] | None = None
        if state.status == "paused":
            break_report = {
                "uncertainty_type": state.break_state.uncertainty_type,
                "known_now": state.break_state.known_now,
                "missing_now": state.break_state.missing_now,
                "question_for_user": state.break_state.question_for_user,
            }

        result = {
            "run_id": state.run_id,
            "status": state.status,
            "current_node": state.current_node,
            "blueprint_stage": state.blueprint.active_node,
            "draft_text": state.payload.draft_text,
            "verdict": state.payload.stage_result,
            "accepted_facts": state.payload.accepted_facts,
            "checkpoint_id": state.checkpoint.last_checkpoint_id,
            "break_report": break_report,
            "token_used": state.budget.token_used,
            "memory_refs": state.memory.model_dump(),
        }
        return result

    def _append_cache_ref(self, state: RunState, cache_ref: str) -> object:
        cache_refs = list(dict.fromkeys([*state.memory.cache_refs, cache_ref]))
        cache_refs = keep_cache_refs(
            cache_refs=cache_refs,
            model_gateway=self._model_gateway,
            model_tier=state.routing.model_tier,
            keep_limit=self._config.runtime.max_cache_refs,
        )
        return state.memory.model_copy(update={"cache_refs": cache_refs})

    def _append_refs(self, refs: Iterable[str], value: str) -> list[str]:
        return list(dict.fromkeys([*refs, value]))

    def _handle_interaction(self, state: RunState) -> NodeResult:
        self._trace_logger.log(state.audit.trace_id, "node_start", "interaction")
        cache_ref = self._record_event(state.run_id, "interaction", {"node": "interaction"})
        delta = {
            "status": "running",
            "memory": self._append_cache_ref(state, cache_ref),
            "uncertainty": UncertaintyState(status="none", type=None, question_for_user=None, blocked_by=[]),
            "break_state": BreakState(),
        }
        return NodeResult(next_node="strategist", state_delta=delta)

    def _handle_strategist(self, state: RunState) -> NodeResult:
        self._trace_logger.log(state.audit.trace_id, "node_start", "strategist")
        cache_ref = self._record_event(
            state.run_id,
            "strategist",
            {"stage": state.blueprint.active_node, "stage_status": state.blueprint.stage_status},
        )
        allowed_targets = self._engine.legal_targets(state.current_node)
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

    def _handle_blueprint(self, state: RunState) -> NodeResult:
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

    def _handle_reasoning(self, state: RunState) -> NodeResult:
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

    def _load_documents(self, state: RunState) -> list[tuple[str, str]]:
        documents: list[tuple[str, str]] = []
        allowed_tools = set(state.capabilities.loaded_tools) if state.capabilities.loaded_tools else None
        permission_level = "readonly" if "readonly" in state.capabilities.load_reason else "none"
        for source in state.payload.source_refs:
            result = self._tool_runtime.execute(
                tool_name="read_local_text",
                run_id=state.run_id,
                permission_level=permission_level,
                payload={"path": source},
                allowed_tools=allowed_tools,
            )
            if result.ok:
                text = str(result.output.get("content", ""))
                if text:
                    documents.append((source, text))
        return documents

    def _investigate(self, state: RunState) -> DistilledEvidence:
        docs = self._load_documents(state)
        if not docs:
            return DistilledEvidence(facts=[], source_refs=[], enough_evidence=False)

        questions = list(state.investigation.pending_questions) or [state.payload.instruction or state.goal]
        micro_graph = MicroGraph()

        for retrieval_goal in questions[: self._config.investigation.max_rounds]:
            intent = build_retrieval_intent(
                retrieval_goal,
                model_gateway=self._model_gateway,
                model_tier=state.routing.model_tier,
            )
            candidates = self._hybrid_recall.search(intent=intent, documents=docs)
            ranked = rerank_candidates(candidates)
            evidence = extract_distilled_facts(
                ranked,
                max_facts=self._config.investigation.max_facts_per_round,
                model_gateway=self._model_gateway,
                model_tier=state.routing.model_tier,
            )
            evidence_review = review_distilled_evidence(
                question=retrieval_goal,
                evidence=evidence,
                model_gateway=self._model_gateway,
                model_tier=state.routing.model_tier,
            )
            evidence = evidence.model_copy(update={"enough_evidence": evidence_review.enough_evidence})
            for fact, source in zip(evidence.facts, evidence.source_refs, strict=False):
                micro_graph.add_support(retrieval_goal, fact, source)

            unique_sources = list(dict.fromkeys(micro_graph.fact_sources.values()))
            if len(micro_graph.fact_sources) >= self._config.investigation.min_fact_count and len(
                unique_sources
            ) >= self._config.investigation.min_source_count:
                break

        facts = list(micro_graph.fact_sources.keys())
        source_refs = list(dict.fromkeys(micro_graph.fact_sources.values()))
        enough_evidence = len(facts) >= self._config.investigation.min_fact_count and len(
            source_refs
        ) >= self._config.investigation.min_source_count

        return DistilledEvidence(
            facts=facts[: self._config.investigation.max_facts_per_round],
            source_refs=source_refs[: self._config.investigation.max_facts_per_round],
            enough_evidence=enough_evidence,
        )

    def _handle_investigation(self, state: RunState) -> NodeResult:
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

    def _handle_reflection(self, state: RunState) -> NodeResult:
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
            max_review_loops=self._config.reflection.max_review_loops,
            min_draft_chars=self._config.reflection.min_draft_chars,
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

    def _handle_break(self, state: RunState) -> NodeResult:
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

    def _mount_memory_context(self, state: RunState, mounts: list[MemoryMount]) -> list[str]:
        mounted: list[str] = []
        for mount in mounts:
            if mount.source == "ram":
                _, _, key = mount.ref_id.partition(f"ram:{state.run_id}:")
                if key:
                    value = self._working_ram.get(state.run_id, key)
                    if isinstance(value, str) and value:
                        mounted.append(value)
            elif mount.source == "cache":
                event = self._episodic_cache.load_by_ref(mount.ref_id)
                if event:
                    event_type = str(event.get("event_type", "event"))
                    details = event.get("details", {})
                    mounted.append(f"{event_type}: {details}")
            elif mount.source == "disk":
                disk_value = self._semantic_disk.load_by_ref(mount.ref_id, detail_level=mount.detail_level)
                if disk_value:
                    mounted.append(disk_value)
            elif mount.source == "blackboard":
                mounted.extend(self._global_blackboard.render_context())
        return list(dict.fromkeys(mounted))[:10]

    def _read_local_text_tool(self, _context, payload: dict[str, object]) -> dict[str, object]:
        path_value = payload.get("path")
        if not isinstance(path_value, str):
            return {"content": ""}
        path = Path(path_value)
        if not path.is_absolute():
            path = (self._workspace_root / path).resolve()
        if not path.exists() or not path.is_file():
            return {"content": ""}
        return {"content": path.read_text(encoding="utf-8")}

    def _emit_tool_event(self, event_type: str, tool_name: str, details: dict[str, object]) -> None:
        run_id = str(details.get("run_id", "unknown_run"))
        self._record_event(run_id, event_type, {"tool_name": tool_name, **details})

    def _record_event(self, run_id: str, event_type: str, details: dict[str, object]) -> str:
        self._metrics.inc(f"event_{event_type}")
        cache_ref = self._episodic_cache.append(
            run_id=run_id,
            event={
                "event_type": event_type,
                "details": details,
            },
        )
        trace_id = self._trace_ids.get(run_id)
        if trace_id:
            self._trace_logger.log(
                trace_id=trace_id,
                event_type=event_type,
                message=event_type,
                details=details,
            )
        return cache_ref

    def _handle_finish(self, state: RunState) -> NodeResult:
        self._trace_logger.log(state.audit.trace_id, "node_end", "finish")
        final_status = "completed" if state.status == "running" else state.status
        return NodeResult(next_node="finish", state_delta={"status": final_status})
