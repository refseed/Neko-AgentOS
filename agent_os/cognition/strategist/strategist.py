from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from agent_os.cognition.memory_router.memory_router import MemoryMount
from agent_os.cognition.resource_manager.resource_manager import ResourceDecision
from agent_os.runtime.nodes.base import BaseLLMNode, NodeEnvelopeMixin, NodeGateway
from agent_os.runtime.state.models import RunState

DEFAULT_META_TARGETS = ("blueprint", "reasoning", "investigation", "reflection", "break", "finish")


class RoutingDecision(BaseModel):
    """Describe what the control layer decided to do next."""

    model_config = ConfigDict(extra="forbid")

    next_node: str
    confidence: float
    tool_profile: str
    model_tier: str
    memory_mounts: list[MemoryMount] = Field(default_factory=list)
    guardrail_flags: list[str] = Field(default_factory=list)


class MetaRoutingInput(BaseModel):
    """Protocol input for meta routing node."""

    model_config = ConfigDict(extra="forbid")

    goal: str
    stage: str
    stage_status: str
    stage_result: str
    has_draft: bool
    investigation_active: bool
    accepted_fact_count: int
    uncertainty: str
    budget: str
    resource_allowed: bool
    resource_reason: str
    blueprint_enabled: bool
    blueprint_entry_hint: bool
    allowed_targets: list[str] = Field(default_factory=list)


class MetaRoutingOutput(NodeEnvelopeMixin):
    """Protocol output for meta routing node."""

    node_name: str = "meta_router"
    next_node: str
    tool_profile: str
    guardrail_flags: list[str] = Field(default_factory=list)


class Strategist(BaseLLMNode[MetaRoutingInput, MetaRoutingOutput]):
    """Choose next logical action without side effects."""

    @property
    def output_model(self) -> type[MetaRoutingOutput]:
        return MetaRoutingOutput

    def __init__(
        self,
        model_gateway: NodeGateway | None = None,
        blueprint_entry_keywords: Sequence[str] | None = None,
    ) -> None:
        super().__init__(node_name="meta_router", model_gateway=model_gateway)
        default_keywords = ("paper", "chapter", "outline", "blueprint", "plan", "写作", "论文", "大纲", "计划")
        selected_keywords = blueprint_entry_keywords or default_keywords
        self._blueprint_entry_keywords = tuple(keyword.strip().lower() for keyword in selected_keywords if keyword.strip())

    def decide(
        self,
        state: RunState,
        resource: ResourceDecision,
        allowed_targets: set[str] | None = None,
    ) -> RoutingDecision:
        normalized_targets = self._normalize_allowed_targets(allowed_targets)
        heuristic = self._heuristic_decide(
            state=state,
            resource=resource,
            allowed_targets=normalized_targets,
        )
        output = self.run(
            self._build_input(
                state=state,
                resource=resource,
                allowed_targets=normalized_targets,
            ),
            model_tier=resource.model_tier,
        )
        candidate = RoutingDecision(
            next_node=output.next_node,
            confidence=output.confidence,
            tool_profile=output.tool_profile,
            model_tier=resource.model_tier,
            memory_mounts=[],
            guardrail_flags=list(output.guardrail_flags),
        )

        if candidate.next_node not in normalized_targets:
            return heuristic
        return candidate

    def _heuristic_decide(
        self,
        state: RunState,
        resource: ResourceDecision,
        allowed_targets: set[str],
    ) -> RoutingDecision:
        if not resource.allow_execution:
            return self._decision_with_allowed_targets(
                preferred_targets=("break",),
                allowed_targets=allowed_targets,
                confidence=1.0,
                model_tier=resource.model_tier,
                guardrail_flags=[resource.reason],
            )

        if state.uncertainty.status == "blocked":
            return self._decision_with_allowed_targets(
                preferred_targets=("break",),
                allowed_targets=allowed_targets,
                confidence=0.9,
                model_tier=resource.model_tier,
                guardrail_flags=["uncertainty_blocked"],
            )

        if state.blueprint.enabled and state.blueprint.active_node == "done":
            return self._decision_with_allowed_targets(
                preferred_targets=("finish",),
                allowed_targets=allowed_targets,
                confidence=0.98,
                model_tier=resource.model_tier,
            )

        if not state.blueprint.enabled and self._should_enable_blueprint(state):
            return self._decision_with_allowed_targets(
                preferred_targets=("blueprint", "reasoning"),
                allowed_targets=allowed_targets,
                confidence=0.9,
                model_tier=resource.model_tier,
            )

        if state.blueprint.enabled and state.blueprint.stage_status == "approved":
            return self._decision_with_allowed_targets(
                preferred_targets=("blueprint", "reflection"),
                allowed_targets=allowed_targets,
                confidence=0.92,
                model_tier=resource.model_tier,
            )

        if (
            state.blueprint.stage_status == "need_more_evidence"
            or state.payload.stage_result == "need_more_evidence"
            or state.investigation.active
        ):
            return self._decision_with_allowed_targets(
                preferred_targets=("investigation", "reasoning"),
                allowed_targets=allowed_targets,
                confidence=0.87,
                model_tier=resource.model_tier,
            )

        if state.payload.stage_result == "retry" or state.blueprint.stage_status in {"pending", "retry"}:
            return self._decision_with_allowed_targets(
                preferred_targets=("reasoning", "investigation"),
                allowed_targets=allowed_targets,
                confidence=0.86,
                model_tier=resource.model_tier,
            )

        if not state.payload.draft_text.strip():
            return self._decision_with_allowed_targets(
                preferred_targets=("reasoning",),
                allowed_targets=allowed_targets,
                confidence=0.84,
                model_tier=resource.model_tier,
            )

        if state.payload.stage_result == "approved":
            preferred = ("blueprint", "finish") if state.blueprint.enabled else ("finish", "reflection")
            return self._decision_with_allowed_targets(
                preferred_targets=preferred,
                allowed_targets=allowed_targets,
                confidence=0.91,
                model_tier=resource.model_tier,
            )

        return self._decision_with_allowed_targets(
            preferred_targets=("reflection", "reasoning"),
            allowed_targets=allowed_targets,
            confidence=0.8,
            model_tier=resource.model_tier,
        )

    def _build_input(
        self,
        state: RunState,
        resource: ResourceDecision,
        allowed_targets: set[str],
    ) -> MetaRoutingInput:
        return MetaRoutingInput(
            goal=state.goal,
            stage=state.blueprint.active_node,
            stage_status=state.blueprint.stage_status,
            stage_result=state.payload.stage_result,
            has_draft=bool(state.payload.draft_text),
            investigation_active=state.investigation.active,
            accepted_fact_count=len(state.payload.accepted_facts),
            uncertainty=f"{state.uncertainty.status}:{state.uncertainty.type}",
            budget=f"{state.budget.step_used}/{state.budget.max_steps}",
            resource_allowed=resource.allow_execution,
            resource_reason=resource.reason,
            blueprint_enabled=state.blueprint.enabled,
            blueprint_entry_hint=self._should_enable_blueprint(state),
            allowed_targets=sorted(allowed_targets),
        )

    def build_prompt(self, node_input: MetaRoutingInput) -> str:
        allowed_targets_text = ", ".join(node_input.allowed_targets)
        return (
            "You are the meta routing node in an Agent OS graph.\n"
            "Decide one next node only from the runtime-legal allowed targets.\n"
            "Protocol:\n"
            "- Return strict JSON only.\n"
            "- Required keys: protocol_version, node_name, confidence, notes, next_node, tool_profile, guardrail_flags.\n"
            "- protocol_version must be 'node-io/v1'.\n"
            "- node_name must be 'meta_router'.\n"
            f"allowed_targets={allowed_targets_text}\n"
            f"goal={node_input.goal}\n"
            f"stage={node_input.stage}\n"
            f"stage_status={node_input.stage_status}\n"
            f"stage_result={node_input.stage_result}\n"
            f"has_draft={node_input.has_draft}\n"
            f"investigation_active={node_input.investigation_active}\n"
            f"accepted_fact_count={node_input.accepted_fact_count}\n"
            f"uncertainty={node_input.uncertainty}\n"
            f"budget={node_input.budget}\n"
            f"resource_allowed={node_input.resource_allowed}\n"
            f"resource_reason={node_input.resource_reason}\n"
            f"blueprint_enabled={node_input.blueprint_enabled}\n"
            f"blueprint_entry_hint={node_input.blueprint_entry_hint}\n"
        )

    def fallback(self, node_input: MetaRoutingInput) -> MetaRoutingOutput:
        heuristic = self._heuristic_from_input(
            node_input=node_input,
            allowed_targets=self._normalize_allowed_targets(set(node_input.allowed_targets)),
        )
        return MetaRoutingOutput(
            protocol_version="node-io/v1",
            node_name="meta_router",
            confidence=heuristic.confidence,
            notes=["fallback_heuristic"],
            next_node=heuristic.next_node,
            tool_profile=heuristic.tool_profile,
            guardrail_flags=list(heuristic.guardrail_flags),
        )

    def _heuristic_from_input(
        self,
        node_input: MetaRoutingInput,
        allowed_targets: set[str],
    ) -> RoutingDecision:
        if not node_input.resource_allowed:
            return self._decision_with_allowed_targets(
                preferred_targets=("break",),
                allowed_targets=allowed_targets,
                confidence=1.0,
                model_tier="small",
                guardrail_flags=[node_input.resource_reason],
            )
        if node_input.uncertainty.startswith("blocked:"):
            return self._decision_with_allowed_targets(
                preferred_targets=("break",),
                allowed_targets=allowed_targets,
                confidence=0.9,
                model_tier="small",
                guardrail_flags=["uncertainty_blocked"],
            )
        if node_input.blueprint_enabled and node_input.stage == "done":
            return self._decision_with_allowed_targets(
                preferred_targets=("finish",),
                allowed_targets=allowed_targets,
                confidence=0.98,
                model_tier="small",
            )
        if not node_input.blueprint_enabled and node_input.blueprint_entry_hint:
            return self._decision_with_allowed_targets(
                preferred_targets=("blueprint", "reasoning"),
                allowed_targets=allowed_targets,
                confidence=0.9,
                model_tier="small",
            )
        if node_input.blueprint_enabled and node_input.stage_status == "approved":
            return self._decision_with_allowed_targets(
                preferred_targets=("blueprint", "reflection"),
                allowed_targets=allowed_targets,
                confidence=0.92,
                model_tier="small",
            )
        if (
            node_input.stage_status == "need_more_evidence"
            or node_input.stage_result == "need_more_evidence"
            or node_input.investigation_active
        ):
            return self._decision_with_allowed_targets(
                preferred_targets=("investigation", "reasoning"),
                allowed_targets=allowed_targets,
                confidence=0.87,
                model_tier="small",
            )
        if node_input.stage_result == "retry" or node_input.stage_status in {"pending", "retry"}:
            return self._decision_with_allowed_targets(
                preferred_targets=("reasoning", "investigation"),
                allowed_targets=allowed_targets,
                confidence=0.86,
                model_tier="small",
            )
        if not node_input.has_draft:
            return self._decision_with_allowed_targets(
                preferred_targets=("reasoning",),
                allowed_targets=allowed_targets,
                confidence=0.84,
                model_tier="small",
            )
        if node_input.stage_result == "approved":
            preferred = ("blueprint", "finish") if node_input.blueprint_enabled else ("finish", "reflection")
            return self._decision_with_allowed_targets(
                preferred_targets=preferred,
                allowed_targets=allowed_targets,
                confidence=0.91,
                model_tier="small",
            )
        return self._decision_with_allowed_targets(
            preferred_targets=("reflection", "reasoning"),
            allowed_targets=allowed_targets,
            confidence=0.8,
            model_tier="small",
        )

    def _normalize_allowed_targets(self, allowed_targets: set[str] | None) -> set[str]:
        if not allowed_targets:
            return set(DEFAULT_META_TARGETS)
        normalized = {target.strip() for target in allowed_targets if target.strip()}
        return normalized or set(DEFAULT_META_TARGETS)

    def _decision_with_allowed_targets(
        self,
        preferred_targets: Sequence[str],
        allowed_targets: set[str],
        confidence: float,
        model_tier: str,
        guardrail_flags: list[str] | None = None,
    ) -> RoutingDecision:
        target = self._pick_allowed_target(preferred_targets, allowed_targets)
        return RoutingDecision(
            next_node=target,
            confidence=confidence,
            tool_profile=self._tool_profile_for_target(target),
            model_tier=model_tier,
            guardrail_flags=list(guardrail_flags or []),
        )

    def _pick_allowed_target(self, preferred_targets: Sequence[str], allowed_targets: set[str]) -> str:
        for target in preferred_targets:
            if target in allowed_targets:
                return target
        for fallback in DEFAULT_META_TARGETS:
            if fallback in allowed_targets:
                return fallback
        return next(iter(allowed_targets))

    def _tool_profile_for_target(self, target: str) -> str:
        profile_by_target = {
            "reasoning": "reasoning_readonly",
            "investigation": "investigation_readonly",
            "reflection": "reflection_readonly",
            "blueprint": "none",
            "break": "none",
            "finish": "none",
        }
        return profile_by_target.get(target, "none")

    def _should_enable_blueprint(self, state: RunState) -> bool:
        if state.blueprint.enabled:
            return False
        composed_goal = f"{state.goal}\n{state.payload.instruction}".lower()
        keyword_hit = any(keyword in composed_goal for keyword in self._blueprint_entry_keywords)
        if keyword_hit:
            return True
        return len(state.payload.source_refs) >= 3 or len(state.goal) >= 72
