from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from agent_os.runtime.state.models import RunState

UncertaintyType = Literal[
    "missing_evidence",
    "tool_unavailable",
    "conflicting_evidence",
    "low_confidence_routing",
    "user_input_required",
    "budget_exceeded",
]


class BreakReport(BaseModel):
    """Small human-readable summary shown when the system pauses."""

    model_config = ConfigDict(extra="forbid")

    uncertainty_type: UncertaintyType
    known_now: str
    missing_now: str
    question_for_user: str


class EpistemicGuard:
    """Generate structured uncertainty reports instead of guessing."""

    def build_break_report(self, state: RunState, uncertainty_type: UncertaintyType) -> BreakReport:
        known = ", ".join(state.payload.accepted_facts[:3]) or "no accepted facts yet"
        missing = ", ".join(state.investigation.pending_questions[:3]) or "evidence needed to continue"
        question = state.uncertainty.question_for_user or "What missing fact should be prioritized next?"
        return BreakReport(
            uncertainty_type=uncertainty_type,
            known_now=known,
            missing_now=missing,
            question_for_user=question,
        )
