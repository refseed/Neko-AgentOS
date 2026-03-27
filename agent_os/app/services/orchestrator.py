from __future__ import annotations

from pathlib import Path
from typing import Iterable
from uuid import uuid4

from agent_os.app.config import AgentConfig, load_agent_config
from agent_os.app.schemas.requests import ResumeRunRequest, StartRunRequest
from agent_os.cognition.memory_router.memory_router import MemoryMount
from agent_os.cognition.prompt_builder.builder import build_reasoning_prompt
from agent_os.cognition.reasoning.reasoning_node import ReasoningNode
from agent_os.cognition.reflection.reflection_node import ReflectionNode
from agent_os.cognition.resource_manager.resource_manager import ResourceManager
from agent_os.cognition.strategist.strategist import Strategist
from agent_os.investigation.extract.extractor import DistilledEvidence
from agent_os.investigation.recall.hybrid_recall import HybridRecall
from agent_os.investigation.subgraph.runner import InvestigationSubgraphRunner
from agent_os.memory.blackboard.global_blackboard import GlobalBlackboard
from agent_os.memory.cache.episodic_cache import EpisodicCache
from agent_os.memory.compression.compressor import keep_cache_refs
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
from agent_os.runtime.graph.engine import GraphEngine
from agent_os.runtime.nodes.main_graph_nodes import (
    BlueprintRuntimeNode,
    BreakRuntimeNode,
    FinishRuntimeNode,
    InteractionRuntimeNode,
    InvestigationRuntimeNode,
    ReasoningRuntimeNode,
    ReflectionRuntimeNode,
    StrategistRuntimeNode,
)
from agent_os.runtime.routing.capability_router import CapabilityRouter
from agent_os.runtime.routing.meta_router import MetaRouter
from agent_os.runtime.state.models import (
    BreakState,
    BlueprintState,
    BudgetState,
    MemoryRefs,
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
        self._investigation_runner = InvestigationSubgraphRunner(
            config=self._config.investigation,
            model_gateway=self._model_gateway,
            hybrid_recall=self._hybrid_recall,
            load_documents=self._load_documents,
        )

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

        self._interaction_runtime_node = InteractionRuntimeNode(
            trace_logger=self._trace_logger,
            record_event=self._record_event,
            append_cache_ref=self._append_cache_ref,
        )
        self._strategist_runtime_node = StrategistRuntimeNode(
            trace_logger=self._trace_logger,
            record_event=self._record_event,
            append_cache_ref=self._append_cache_ref,
            meta_router=self._meta_router,
            mount_memory_context=self._mount_memory_context,
            capability_router=self._capability_router,
            capability_loader=self._capability_loader,
            legal_targets_getter=lambda source: self._engine.legal_targets(source),
        )
        self._blueprint_runtime_node = BlueprintRuntimeNode(
            trace_logger=self._trace_logger,
            record_event=self._record_event,
            append_cache_ref=self._append_cache_ref,
            blueprint_graph=self._blueprint_graph,
        )
        self._reasoning_runtime_node = ReasoningRuntimeNode(
            trace_logger=self._trace_logger,
            record_event=self._record_event,
            append_cache_ref=self._append_cache_ref,
            append_refs=self._append_refs,
            reasoning_node=self._reasoning_node,
            working_ram=self._working_ram,
        )
        self._investigation_runtime_node = InvestigationRuntimeNode(
            trace_logger=self._trace_logger,
            record_event=self._record_event,
            append_cache_ref=self._append_cache_ref,
            investigate=lambda run_state: self._investigate(run_state),
            semantic_disk=self._semantic_disk,
            model_gateway=self._model_gateway,
        )
        self._reflection_runtime_node = ReflectionRuntimeNode(
            trace_logger=self._trace_logger,
            record_event=self._record_event,
            append_cache_ref=self._append_cache_ref,
            reflection_node=self._reflection_node,
            blueprint_graph=self._blueprint_graph,
            reflection_config=self._config.reflection,
            model_gateway=self._model_gateway,
        )
        self._break_runtime_node = BreakRuntimeNode(
            trace_logger=self._trace_logger,
            record_event=self._record_event,
            append_cache_ref=self._append_cache_ref,
            checkpoint_repo=self._checkpoint_repo,
            epistemic_guard=self._epistemic_guard,
            logger=self._logger,
        )
        self._finish_runtime_node = FinishRuntimeNode(trace_logger=self._trace_logger)

        self._engine = GraphEngine(
            handlers={
                "interaction": self._interaction_runtime_node.handle,
                "strategist": self._strategist_runtime_node.handle,
                "blueprint": self._blueprint_runtime_node.handle,
                "reasoning": self._reasoning_runtime_node.handle,
                "investigation": self._investigation_runtime_node.handle,
                "reflection": self._reflection_runtime_node.handle,
                "break": self._break_runtime_node.handle,
                "finish": self._finish_runtime_node.handle,
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

    def _append_cache_ref(self, state: RunState, cache_ref: str) -> MemoryRefs:
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

    def _investigate(self, state: RunState) -> DistilledEvidence:
        return self._investigation_runner.run(state)

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
