from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from agent_os.cognition.memory_router.memory_router import MemoryMount
from agent_os.cognition.resource_manager.resource_manager import ResourceDecision
from agent_os.runtime.nodes.base import BaseLLMNode, NodeEnvelopeMixin, NodeGateway
from agent_os.runtime.state.models import RunState, UncertaintyState

DEFAULT_META_TARGETS = ("blueprint", "reasoning", "investigation", "reflection", "break", "finish")
MODEL_TIER_ORDER = ("small", "medium", "large")


class RoutingDecision(BaseModel):
    """Describe what the control layer decided to do next."""

    model_config = ConfigDict(extra="forbid")

    next_node: str
    confidence: float
    tool_profile: str
    model_tier: str
    memory_mounts: list[MemoryMount] = Field(default_factory=list)
    guardrail_flags: list[str] = Field(default_factory=list)
    payload_delta: dict[str, object] = Field(default_factory=dict)
    uncertainty_report: UncertaintyState = Field(default_factory=UncertaintyState)


class MetaRoutingInput(BaseModel):
    """Protocol input for meta routing node."""

    model_config = ConfigDict(extra="forbid")

    goal: str
    stage: str
    stage_status: str
    stage_result: str
    has_draft: bool
    investigation_active: bool
    context_entry_count: int
    uncertainty: str
    budget: str
    resource_allowed: bool
    resource_reason: str
    blueprint_enabled: bool
    blueprint_entry_hint: bool
    context_chars: int
    expected_output_tokens: int
    task_complexity: str
    source_ref_count: int
    memory_context_items: int
    stage_attempts: int = 0
    allowed_targets: list[str] = Field(default_factory=list)


class MetaRoutingOutput(NodeEnvelopeMixin):
    """Protocol output for meta routing node."""

    node_name: str = "meta_router"
    next_node: str
    tool_profile: str
    model_tier: str = "small"
    guardrail_flags: list[str] = Field(default_factory=list)
    payload_delta: dict[str, object] = Field(default_factory=dict)
    uncertainty_report: UncertaintyState = Field(default_factory=UncertaintyState)


class Strategist(BaseLLMNode[MetaRoutingInput, MetaRoutingOutput]):
    """Choose next logical action without side effects."""

    @property
    def output_model(self) -> type[MetaRoutingOutput]:
        return MetaRoutingOutput

    def __init__(
        self,
        model_gateway: NodeGateway | None = None,
        blueprint_entry_keywords: Sequence[str] | None = None,
        low_confidence_threshold: float = 0.72,
        enable_low_confidence_review: bool = True,
    ) -> None:
        super().__init__(node_name="meta_router", model_gateway=model_gateway)
        default_keywords = ("paper", "chapter", "outline", "blueprint", "plan", "写作", "论文", "大纲", "计划")
        selected_keywords = blueprint_entry_keywords or default_keywords
        self._blueprint_entry_keywords = tuple(keyword.strip().lower() for keyword in selected_keywords if keyword.strip())
        self._low_confidence_threshold = min(max(low_confidence_threshold, 0.0), 1.0)
        self._enable_low_confidence_review = enable_low_confidence_review

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
        if not resource.allow_execution:
            return heuristic

        node_input = self._build_input(
            state=state,
            resource=resource,
            allowed_targets=normalized_targets,
        )
        primary_tier = self._normalize_model_tier(resource.model_tier, fallback=heuristic.model_tier)
        candidate = self._candidate_from_model(node_input=node_input, model_tier=primary_tier, heuristic=heuristic)

        if (
            candidate.next_node == "reasoning"
            and state.blueprint.stage_attempts >= 2
            and state.payload.draft_text.strip()
            and heuristic.next_node in ("reflection", "finish")
        ):
            candidate = heuristic

        if candidate.next_node not in normalized_targets:
            candidate = heuristic

        if candidate.confidence >= self._low_confidence_threshold:
            return candidate

        if not self._enable_low_confidence_review:
            return self._low_confidence_break(
                allowed_targets=normalized_targets,
                model_tier=candidate.model_tier,
                reason=f"low_confidence_{candidate.confidence:.2f}",
            )

        review_tier = self._upgrade_model_tier(primary_tier)
        if review_tier == primary_tier:
            return self._low_confidence_break(
                allowed_targets=normalized_targets,
                model_tier=candidate.model_tier,
                reason="low_confidence_no_higher_tier",
            )

        reviewed = self._candidate_from_model(node_input=node_input, model_tier=review_tier, heuristic=heuristic)
        if reviewed.next_node not in normalized_targets:
            reviewed = heuristic

        if reviewed.confidence >= self._low_confidence_threshold:
            return reviewed.model_copy(
                update={
                    "guardrail_flags": list(
                        dict.fromkeys([*reviewed.guardrail_flags, "low_confidence_recovered_by_review"])
                    )
                }
            )

        return self._low_confidence_break(
            allowed_targets=normalized_targets,
            model_tier=reviewed.model_tier,
            reason=f"low_confidence_after_review_{reviewed.confidence:.2f}",
        )

    def _candidate_from_model(
        self,
        *,
        node_input: MetaRoutingInput,
        model_tier: str,
        heuristic: RoutingDecision,
    ) -> RoutingDecision:
        output = self.run(node_input, model_tier=model_tier)
        selected_tier = self._normalize_model_tier(output.model_tier, fallback=heuristic.model_tier)
        return RoutingDecision(
            next_node=output.next_node,
            confidence=output.confidence,
            tool_profile=output.tool_profile,
            model_tier=selected_tier,
            memory_mounts=[],
            guardrail_flags=list(output.guardrail_flags),
            payload_delta=dict(output.payload_delta),
            uncertainty_report=output.uncertainty_report,
        )

    def _low_confidence_break(self, allowed_targets: set[str], model_tier: str, reason: str) -> RoutingDecision:
        question = "Routing confidence is low after review. Should I continue with manual guidance?"
        return self._decision_with_allowed_targets(
            preferred_targets=("break",),
            allowed_targets=allowed_targets,
            confidence=0.99,
            model_tier=model_tier,
            guardrail_flags=[reason],
            uncertainty_report=UncertaintyState(
                status="blocked",
                type="low_confidence_routing",
                question_for_user=question,
                blocked_by=[reason],
            ),
        )

    def _heuristic_decide(
        self,
        state: RunState,
        resource: ResourceDecision,
        allowed_targets: set[str],
    ) -> RoutingDecision:
        suggested_tier = self._estimate_model_tier_for_state(state)

        if not resource.allow_execution:
            return self._decision_with_allowed_targets(
                preferred_targets=("break",),
                allowed_targets=allowed_targets,
                confidence=1.0,
                model_tier=suggested_tier,
                guardrail_flags=[resource.reason],
            )

        if state.uncertainty.status == "blocked":
            return self._decision_with_allowed_targets(
                preferred_targets=("break",),
                allowed_targets=allowed_targets,
                confidence=0.9,
                model_tier=suggested_tier,
                guardrail_flags=["uncertainty_blocked"],
                uncertainty_report=state.uncertainty,
            )

        if state.blueprint.enabled and state.blueprint.active_node == "done":
            return self._decision_with_allowed_targets(
                preferred_targets=("finish",),
                allowed_targets=allowed_targets,
                confidence=0.98,
                model_tier=suggested_tier,
            )

        if not state.blueprint.enabled and self._should_enable_blueprint(state):
            return self._decision_with_allowed_targets(
                preferred_targets=("blueprint", "reasoning"),
                allowed_targets=allowed_targets,
                confidence=0.9,
                model_tier=suggested_tier,
            )

        if state.blueprint.enabled and state.blueprint.stage_status == "approved":
            return self._decision_with_allowed_targets(
                preferred_targets=("blueprint", "reflection"),
                allowed_targets=allowed_targets,
                confidence=0.92,
                model_tier=suggested_tier,
            )

        if (
            state.blueprint.stage_status == "need_more_evidence"
            or state.payload.stage_result == "need_more_evidence"
            or state.investigation.active
        ):
            if "investigation" not in allowed_targets:
                return self._decision_with_allowed_targets(
                    preferred_targets=("break",),
                    allowed_targets=allowed_targets,
                    confidence=0.95,
                    model_tier=suggested_tier,
                    guardrail_flags=["investigation_unavailable"],
                    uncertainty_report=UncertaintyState(
                        status="blocked",
                        type="missing_evidence",
                        question_for_user=(
                            "当前任务需要额外的证据支撑，但没有可供检索的数据源。"
                            "如果任务需要外部数据，请提供数据文件路径(source_paths)；"
                            "如果不需要外部数据，请简化问题或直接提供所需信息。"
                        ),
                        blocked_by=["no_data_source"],
                    ),
                )
            return self._decision_with_allowed_targets(
                preferred_targets=("investigation", "reasoning"),
                allowed_targets=allowed_targets,
                confidence=0.87,
                model_tier=suggested_tier,
            )

        if state.payload.stage_result == "retry" or state.blueprint.stage_status in {"pending", "retry"}:
            return self._decision_with_allowed_targets(
                preferred_targets=("reasoning", "investigation"),
                allowed_targets=allowed_targets,
                confidence=0.86,
                model_tier=suggested_tier,
            )

        if not state.payload.draft_text.strip():
            return self._decision_with_allowed_targets(
                preferred_targets=("reasoning",),
                allowed_targets=allowed_targets,
                confidence=0.84,
                model_tier=suggested_tier,
            )

        if state.payload.draft_text.strip() and state.blueprint.stage_status == "in_progress":
            return self._decision_with_allowed_targets(
                preferred_targets=("reflection",),
                allowed_targets=allowed_targets,
                confidence=0.93,
                model_tier=suggested_tier,
            )

        if state.payload.stage_result == "approved":
            preferred = ("blueprint", "finish") if state.blueprint.enabled else ("finish", "reflection")
            return self._decision_with_allowed_targets(
                preferred_targets=preferred,
                allowed_targets=allowed_targets,
                confidence=0.91,
                model_tier=suggested_tier,
            )

        return self._decision_with_allowed_targets(
            preferred_targets=("reflection", "reasoning"),
            allowed_targets=allowed_targets,
            confidence=0.8,
            model_tier=suggested_tier,
        )

    def _build_input(
        self,
        state: RunState,
        resource: ResourceDecision,
        allowed_targets: set[str],
    ) -> MetaRoutingInput:
        context_chars = self._estimate_context_chars(state)
        expected_output_tokens = self._estimate_expected_output_tokens(state)
        task_complexity = self._estimate_task_complexity(state=state, context_chars=context_chars)
        return MetaRoutingInput(
            goal=state.goal,
            stage=state.blueprint.active_node,
            stage_status=state.blueprint.stage_status,
            stage_result=state.payload.stage_result,
            has_draft=bool(state.payload.draft_text),
            investigation_active=state.investigation.active,
            context_entry_count=len(state.payload.context_entries),
            uncertainty=f"{state.uncertainty.status}:{state.uncertainty.type}",
            budget=f"{state.budget.step_used}/{state.budget.max_steps}",
            resource_allowed=resource.allow_execution,
            resource_reason=resource.reason,
            blueprint_enabled=state.blueprint.enabled,
            blueprint_entry_hint=self._should_enable_blueprint(state),
            context_chars=context_chars,
            expected_output_tokens=expected_output_tokens,
            task_complexity=task_complexity,
            source_ref_count=len(state.payload.source_refs),
            memory_context_items=len(state.payload.memory_context),
            stage_attempts=state.blueprint.stage_attempts,
            allowed_targets=sorted(allowed_targets),
        )

    def build_prompt(self, node_input: MetaRoutingInput) -> str:
        allowed_targets_text = ", ".join(node_input.allowed_targets)
        return (
            "Role: meta routing node.\n"
            "Task: choose exactly one next_node from allowed_targets, and choose model_tier for that next node.\n"
            "Hard output contract:\n"
            "- Output strict JSON only. No markdown. No analysis text.\n"
            "- First char must be '{' and last char must be '}'.\n"
            "- Required keys: protocol_version, node_name, confidence, notes, next_node, tool_profile, model_tier, guardrail_flags, payload_delta, uncertainty_report.\n"
            "- protocol_version='node-io/v1', node_name='meta_router'.\n"
            "- next_node MUST be one of allowed_targets.\n"
            "- model_tier MUST be one of: small, medium, large.\n"
            "- uncertainty_report schema: {status, type, question_for_user, blocked_by}.\n"
            "- Keep payload_delta minimal.\n"
            "Node behavior guide:\n"
            "- reasoning: generate or revise a draft. Route here only when no draft exists or reflection returned 'retry'.\n"
            "- reflection: evaluate the current draft quality. Route here after reasoning has produced a draft.\n"
            "- investigation: search data sources for evidence. Only useful when source_ref_count > 0.\n"
            "- blueprint: advance to the next blueprint stage after reflection approves.\n"
            "- finish: complete the task and return output.\n"
            "- break: pause and ask the user for clarification.\n"
            f"allowed_targets={allowed_targets_text}\n"
            f"goal={node_input.goal}\n"
            f"stage={node_input.stage}\n"
            f"stage_status={node_input.stage_status}\n"
            f"stage_result={node_input.stage_result}\n"
            f"has_draft={node_input.has_draft}\n"
            f"investigation_active={node_input.investigation_active}\n"
            f"context_entry_count={node_input.context_entry_count}\n"
            f"uncertainty={node_input.uncertainty}\n"
            f"budget={node_input.budget}\n"
            f"resource_allowed={node_input.resource_allowed}\n"
            f"resource_reason={node_input.resource_reason}\n"
            f"blueprint_enabled={node_input.blueprint_enabled}\n"
            f"blueprint_entry_hint={node_input.blueprint_entry_hint}\n"
            f"context_chars={node_input.context_chars}\n"
            f"expected_output_tokens={node_input.expected_output_tokens}\n"
            f"task_complexity={node_input.task_complexity}\n"
            f"source_ref_count={node_input.source_ref_count}\n"
            f"memory_context_items={node_input.memory_context_items}\n"
            f"stage_attempts={node_input.stage_attempts}\n"
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
            model_tier=heuristic.model_tier,
            guardrail_flags=list(heuristic.guardrail_flags),
            payload_delta=dict(heuristic.payload_delta),
            uncertainty_report=heuristic.uncertainty_report,
        )

    def _heuristic_from_input(
        self,
        node_input: MetaRoutingInput,
        allowed_targets: set[str],
    ) -> RoutingDecision:
        suggested_tier = self._estimate_model_tier_for_input(node_input)
        if not node_input.resource_allowed:
            return self._decision_with_allowed_targets(
                preferred_targets=("break",),
                allowed_targets=allowed_targets,
                confidence=1.0,
                model_tier=suggested_tier,
                guardrail_flags=[node_input.resource_reason],
            )
        if node_input.uncertainty.startswith("blocked:"):
            return self._decision_with_allowed_targets(
                preferred_targets=("break",),
                allowed_targets=allowed_targets,
                confidence=0.9,
                model_tier=suggested_tier,
                guardrail_flags=["uncertainty_blocked"],
            )
        if node_input.blueprint_enabled and node_input.stage == "done":
            return self._decision_with_allowed_targets(
                preferred_targets=("finish",),
                allowed_targets=allowed_targets,
                confidence=0.98,
                model_tier=suggested_tier,
            )
        if not node_input.blueprint_enabled and node_input.blueprint_entry_hint:
            return self._decision_with_allowed_targets(
                preferred_targets=("blueprint", "reasoning"),
                allowed_targets=allowed_targets,
                confidence=0.9,
                model_tier=suggested_tier,
            )
        if node_input.blueprint_enabled and node_input.stage_status == "approved":
            return self._decision_with_allowed_targets(
                preferred_targets=("blueprint", "reflection"),
                allowed_targets=allowed_targets,
                confidence=0.92,
                model_tier=suggested_tier,
            )
        if (
            node_input.stage_status == "need_more_evidence"
            or node_input.stage_result == "need_more_evidence"
            or node_input.investigation_active
        ):
            if "investigation" not in allowed_targets:
                return self._decision_with_allowed_targets(
                    preferred_targets=("break",),
                    allowed_targets=allowed_targets,
                    confidence=0.95,
                    model_tier=suggested_tier,
                    guardrail_flags=["investigation_unavailable"],
                    uncertainty_report=UncertaintyState(
                        status="blocked",
                        type="missing_evidence",
                        question_for_user=(
                            "当前任务需要额外的证据支撑，但没有可供检索的数据源。"
                            "如果任务需要外部数据，请提供数据文件路径(source_paths)；"
                            "如果不需要外部数据，请简化问题或直接提供所需信息。"
                        ),
                        blocked_by=["no_data_source"],
                    ),
                )
            return self._decision_with_allowed_targets(
                preferred_targets=("investigation", "reasoning"),
                allowed_targets=allowed_targets,
                confidence=0.87,
                model_tier=suggested_tier,
            )
        if node_input.stage_result == "retry" or node_input.stage_status in {"pending", "retry"}:
            return self._decision_with_allowed_targets(
                preferred_targets=("reasoning", "investigation"),
                allowed_targets=allowed_targets,
                confidence=0.86,
                model_tier=suggested_tier,
            )
        if not node_input.has_draft:
            return self._decision_with_allowed_targets(
                preferred_targets=("reasoning",),
                allowed_targets=allowed_targets,
                confidence=0.84,
                model_tier=suggested_tier,
            )
        if node_input.has_draft and node_input.stage_status == "in_progress":
            return self._decision_with_allowed_targets(
                preferred_targets=("reflection",),
                allowed_targets=allowed_targets,
                confidence=0.93,
                model_tier=suggested_tier,
            )
        if node_input.stage_result == "approved":
            preferred = ("blueprint", "finish") if node_input.blueprint_enabled else ("finish", "reflection")
            return self._decision_with_allowed_targets(
                preferred_targets=preferred,
                allowed_targets=allowed_targets,
                confidence=0.91,
                model_tier=suggested_tier,
            )
        return self._decision_with_allowed_targets(
            preferred_targets=("reflection", "reasoning"),
            allowed_targets=allowed_targets,
            confidence=0.8,
            model_tier=suggested_tier,
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
        payload_delta: dict[str, object] | None = None,
        uncertainty_report: UncertaintyState | None = None,
    ) -> RoutingDecision:
        target = self._pick_allowed_target(preferred_targets, allowed_targets)
        return RoutingDecision(
            next_node=target,
            confidence=confidence,
            tool_profile=self._tool_profile_for_target(target),
            model_tier=self._normalize_model_tier(model_tier),
            guardrail_flags=list(guardrail_flags or []),
            payload_delta=dict(payload_delta or {}),
            uncertainty_report=uncertainty_report or UncertaintyState(),
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

    def _normalize_model_tier(self, model_tier: str, fallback: str = "small") -> str:
        if model_tier in MODEL_TIER_ORDER:
            return model_tier
        if fallback in MODEL_TIER_ORDER:
            return fallback
        return "small"

    def _upgrade_model_tier(self, model_tier: str) -> str:
        normalized = self._normalize_model_tier(model_tier)
        current_index = MODEL_TIER_ORDER.index(normalized)
        if current_index >= len(MODEL_TIER_ORDER) - 1:
            return normalized
        return MODEL_TIER_ORDER[current_index + 1]

    def _estimate_context_chars(self, state: RunState) -> int:
        memory_chars = sum(len(item) for item in state.payload.memory_context[:6])
        fact_chars = sum(len(item) for item in state.payload.context_entries[:8])
        return len(state.goal) + len(state.payload.instruction) + len(state.payload.draft_text) + memory_chars + fact_chars

    def _estimate_task_complexity(self, *, state: RunState, context_chars: int) -> str:
        score = 0
        if context_chars >= 2600:
            score += 2
        elif context_chars >= 900:
            score += 1
        if state.blueprint.enabled:
            score += 1
        if state.blueprint.stage_status in {"retry", "need_more_evidence"}:
            score += 2
        if state.investigation.active:
            score += 1
        if len(state.payload.source_refs) >= 3:
            score += 1
        if state.payload.stage_result in {"retry", "need_more_evidence"}:
            score += 1
        if score >= 4:
            return "high"
        if score >= 2:
            return "medium"
        return "low"

    def _estimate_expected_output_tokens(self, state: RunState) -> int:
        base = 120 + len(state.goal) // 4 + len(state.payload.instruction) // 3
        if state.payload.output_format == "markdown":
            base += 80
        if state.blueprint.active_node in {"idea_summary", "writing_plan"}:
            base += 120
        if state.payload.draft_text:
            base += min(220, len(state.payload.draft_text) // 6)
        return max(120, min(base, 1800))

    def _estimate_model_tier(
        self,
        *,
        context_chars: int,
        task_complexity: str,
        expected_output_tokens: int,
        investigation_active: bool,
        context_entry_count: int,
    ) -> str:
        score = 0
        if context_chars >= 5500:
            score += 3
        elif context_chars >= 2400:
            score += 2
        elif context_chars >= 900:
            score += 1

        if expected_output_tokens >= 1200:
            score += 2
        elif expected_output_tokens >= 420:
            score += 1

        if task_complexity == "high":
            score += 2
        elif task_complexity == "medium":
            score += 1

        if investigation_active:
            score += 1
        if context_entry_count >= 8:
            score += 1

        if score >= 6:
            return "large"
        if score >= 3:
            return "medium"
        return "small"

    def _estimate_model_tier_for_state(self, state: RunState) -> str:
        context_chars = self._estimate_context_chars(state)
        complexity = self._estimate_task_complexity(state=state, context_chars=context_chars)
        expected_output_tokens = self._estimate_expected_output_tokens(state)
        return self._estimate_model_tier(
            context_chars=context_chars,
            task_complexity=complexity,
            expected_output_tokens=expected_output_tokens,
            investigation_active=state.investigation.active,
            context_entry_count=len(state.payload.context_entries),
        )

    def _estimate_model_tier_for_input(self, node_input: MetaRoutingInput) -> str:
        return self._estimate_model_tier(
            context_chars=node_input.context_chars,
            task_complexity=node_input.task_complexity,
            expected_output_tokens=node_input.expected_output_tokens,
            investigation_active=node_input.investigation_active,
            context_entry_count=node_input.context_entry_count,
        )

    def _should_enable_blueprint(self, state: RunState) -> bool:
        if state.blueprint.enabled:
            return False
        composed_goal = f"{state.goal}\n{state.payload.instruction}".lower()
        keyword_hit = any(keyword in composed_goal for keyword in self._blueprint_entry_keywords)
        if keyword_hit:
            return True
        return len(state.payload.source_refs) >= 3 or len(state.goal) >= 72
