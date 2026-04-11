from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_os.cognition.reasoning.reasoning_node import ReasoningResult
from agent_os.runtime.nodes.base import BaseLLMNode, NodeEnvelopeMixin, NodeGateway


class ReflectionInput(BaseModel):
    """Readonly review payload isolated from full runtime state."""

    model_config = ConfigDict(extra="forbid")

    stage: str
    stage_goal: str = ""
    checklist: list[str] = Field(default_factory=list)
    context_entries: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    required_output: str = "markdown"
    review_iteration: int = 0
    max_review_loops: int = 3
    min_draft_chars: int = 24


class ReflectionVerdict(NodeEnvelopeMixin):
    """Review result for one stage output."""

    node_name: str = "reflection"

    status: str
    issues: list[str] = Field(default_factory=list)
    next_action: str
    checklist_coverage: list[str] = Field(default_factory=list)
    interaction_requirements: list[str] = Field(default_factory=list)


class ReflectionNode(BaseLLMNode[ReflectionInput, ReflectionVerdict]):
    """General-purpose reflection node for reviewing previous-node outputs."""

    @property
    def output_model(self) -> type[ReflectionVerdict]:
        return ReflectionVerdict

    def __init__(self, model_gateway: NodeGateway | None = None) -> None:
        super().__init__(node_name="reflection", model_gateway=model_gateway)
        self._latest_draft: ReasoningResult | None = None

    def review(
        self,
        review_input: ReflectionInput,
        draft: ReasoningResult,
        model_tier: str = "small",
    ) -> ReflectionVerdict:
        self._latest_draft = draft
        output = self.run(review_input, model_tier=model_tier)
        if output.status not in {"approved", "retry", "need_more_evidence"}:
            return self._heuristic_review(review_input=review_input, draft=draft)
        if output.next_action not in {"strategist", "reasoning", "investigation"}:
            return self._heuristic_review(review_input=review_input, draft=draft)
        if output.status == "approved" and output.next_action != "strategist":
            return self._heuristic_review(review_input=review_input, draft=draft)
        if output.status == "retry" and output.next_action != "reasoning":
            return self._heuristic_review(review_input=review_input, draft=draft)
        if output.status == "need_more_evidence" and output.next_action != "investigation":
            return self._heuristic_review(review_input=review_input, draft=draft)
        return output

    def _heuristic_review(self, review_input: ReflectionInput, draft: ReasoningResult) -> ReflectionVerdict:
        draft_text = draft.draft_text.strip()
        checklist_coverage = self._evaluate_checklist_coverage(draft_text, review_input.checklist)
        missing_checklist = [item for item in review_input.checklist if item not in checklist_coverage]

        if not draft_text:
            return ReflectionVerdict(
                protocol_version="node-io/v1",
                confidence=0.9,
                notes=["fallback_heuristic"],
                status="retry",
                issues=["draft is empty"],
                next_action="reasoning",
                checklist_coverage=checklist_coverage,
                interaction_requirements=["Please provide a complete draft for reflection review."],
            )
        if review_input.review_iteration >= review_input.max_review_loops:
            return ReflectionVerdict(
                protocol_version="node-io/v1",
                confidence=0.92,
                notes=["fallback_heuristic", "max_review_loops_reached"],
                status="need_more_evidence",
                issues=["max review loops reached without stable approval"],
                next_action="investigation",
                checklist_coverage=checklist_coverage,
                interaction_requirements=["What missing evidence can break the current review loop?"],
            )
        if draft.needs_investigation and not review_input.context_entries:
            return ReflectionVerdict(
                protocol_version="node-io/v1",
                confidence=0.85,
                notes=["fallback_heuristic"],
                status="need_more_evidence",
                issues=["output indicates unresolved evidence gap"],
                next_action="investigation",
                checklist_coverage=checklist_coverage,
                interaction_requirements=["请补充可验证的关键信息，解决当前未闭合的问题。"],
            )
        if len(draft_text) < review_input.min_draft_chars:
            return ReflectionVerdict(
                protocol_version="node-io/v1",
                confidence=0.87,
                notes=["fallback_heuristic"],
                status="retry",
                issues=[f"draft is too short (<{review_input.min_draft_chars} chars)"],
                next_action="reasoning",
                checklist_coverage=checklist_coverage,
                interaction_requirements=["Expand the draft with explicit conclusions and evidence links."],
            )
        needs_source = bool(review_input.context_entries) and any(
            any(keyword in item.lower() for keyword in ("evidence", "source", "citation", "reference"))
            for item in review_input.checklist
        )
        if needs_source and not review_input.source_refs:
            return ReflectionVerdict(
                protocol_version="node-io/v1",
                confidence=0.83,
                notes=["fallback_heuristic"],
                status="need_more_evidence",
                issues=["checklist requires source references"],
                next_action="investigation",
                checklist_coverage=checklist_coverage,
                interaction_requirements=["Add at least one verifiable source reference."],
            )
        if missing_checklist:
            return ReflectionVerdict(
                protocol_version="node-io/v1",
                confidence=0.81,
                notes=["fallback_heuristic"],
                status="retry",
                issues=[f"checklist not covered: {item}" for item in missing_checklist[:3]],
                next_action="reasoning",
                checklist_coverage=checklist_coverage,
                interaction_requirements=["Address uncovered checklist items in the draft."],
            )
        if review_input.stage_goal and not self._is_goal_aligned(draft_text=draft_text, stage_goal=review_input.stage_goal):
            return ReflectionVerdict(
                protocol_version="node-io/v1",
                confidence=0.8,
                notes=["fallback_heuristic"],
                status="retry",
                issues=["draft may drift from stage goal"],
                next_action="reasoning",
                checklist_coverage=checklist_coverage,
                interaction_requirements=["Revise the draft so that it directly answers the stage goal."],
            )

        return ReflectionVerdict(
            protocol_version="node-io/v1",
            confidence=0.8,
            notes=["fallback_heuristic"],
            status="approved",
            issues=[],
            next_action="strategist",
            checklist_coverage=checklist_coverage,
            interaction_requirements=[],
        )

    def build_prompt(self, review_input: ReflectionInput) -> str:
        draft = self._latest_draft or ReasoningResult(draft_text="", needs_investigation=False)
        checklist_text = "\n".join(f"- {item}" for item in review_input.checklist) or "- no checklist"
        facts_text = "\n".join(f"- {fact}" for fact in review_input.context_entries[:8]) or "- none"
        sources_text = "\n".join(f"- {ref}" for ref in review_input.source_refs[:8]) or "- none"
        return (
            "Role: general reflection node.\n"
            "Goal: review the previous node output and decide whether to continue, revise, or gather more information.\n"
            "Review dimensions (generic):\n"
            "1) Intent alignment: does the output answer the current goal/stage?\n"
            "2) Internal quality: logic consistency, completeness, clarity, and actionability.\n"
            "3) Risk signals: unsupported assumptions, contradictions, uncertainty not surfaced.\n"
            "4) Evidence grounding when evidence is required by checklist or current context.\n"
            "Hard output contract:\n"
            "- Output strict JSON only. No markdown. No analysis text.\n"
            "- Required keys: protocol_version, node_name, confidence, notes, status, issues, next_action, checklist_coverage, interaction_requirements.\n"
            "- protocol_version='node-io/v1'. node_name='reflection'.\n"
            "- status must be one of: approved, retry, need_more_evidence.\n"
            "- next_action mapping is strict: approved->strategist, retry->reasoning, need_more_evidence->investigation.\n"
            "- If status=retry, issues must describe what to revise.\n"
            "- If status=need_more_evidence, interaction_requirements must be specific and actionable.\n"
            "Return exactly one JSON object.\n"
            f"stage={review_input.stage}\n"
            f"stage_goal={review_input.stage_goal}\n"
            f"required_output={review_input.required_output}\n"
            f"review_iteration={review_input.review_iteration}\n"
            f"max_review_loops={review_input.max_review_loops}\n"
            f"min_draft_chars={review_input.min_draft_chars}\n"
            f"checklist:\n{checklist_text}\n"
            f"context_entries:\n{facts_text}\n"
            f"source_refs:\n{sources_text}\n"
            f"draft:\n{draft.draft_text}\n"
            f"draft_needs_investigation={draft.needs_investigation}\n"
        )

    def fallback(self, review_input: ReflectionInput) -> ReflectionVerdict:
        draft = self._latest_draft or ReasoningResult(draft_text="", needs_investigation=True)
        return self._heuristic_review(review_input=review_input, draft=draft)

    def _evaluate_checklist_coverage(self, draft_text: str, checklist: list[str]) -> list[str]:
        lowered_draft = draft_text.lower()
        covered: list[str] = []
        for item in checklist:
            item_words = [token for token in item.lower().replace("/", " ").split() if len(token) >= 3]
            if not item_words:
                covered.append(item)
                continue
            if any(word in lowered_draft for word in item_words):
                covered.append(item)
        return covered

    def _is_goal_aligned(self, draft_text: str, stage_goal: str) -> bool:
        goal_terms = [token for token in stage_goal.lower().replace("/", " ").split() if len(token) >= 3]
        if not goal_terms:
            return True
        lowered_draft = draft_text.lower()
        matched = sum(1 for token in goal_terms if token in lowered_draft)
        return matched >= max(1, min(2, len(goal_terms)))
