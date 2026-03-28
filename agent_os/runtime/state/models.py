from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PayloadState(BaseModel):
    """Task payload used by cognition and investigation nodes."""

    model_config = ConfigDict(extra="forbid")

    instruction: str = ""
    accepted_facts: list[str] = Field(default_factory=list)
    output_format: str = "markdown"
    draft_text: str = ""
    stage_result: str = ""
    source_refs: list[str] = Field(default_factory=list)
    memory_context: list[str] = Field(default_factory=list)


class BlueprintState(BaseModel):
    """Active blueprint position in the static stage graph."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    ref: str = "bp_default"
    active_node: str = "literature_scan"
    allowed_exits: list[str] = Field(default_factory=list)
    subgraph_template: str = "paper_research"
    stage_status: str = "pending"
    stage_attempts: int = 0


class MemoryRefs(BaseModel):
    """Pointers to memory layers used by the current run."""

    model_config = ConfigDict(extra="forbid")

    ram_refs: list[str] = Field(default_factory=list)
    cache_refs: list[str] = Field(default_factory=list)
    disk_refs: list[str] = Field(default_factory=list)
    blackboard_ref: str = "bb_default"


class InvestigationState(BaseModel):
    """State slice for the investigation subgraph."""

    model_config = ConfigDict(extra="forbid")

    active: bool = False
    micro_graph_ref: str | None = None
    pending_questions: list[str] = Field(default_factory=list)
    enough_evidence: bool = False


class RoutingState(BaseModel):
    """Routing metadata produced by control modules."""

    model_config = ConfigDict(extra="forbid")

    confidence: float = 1.0
    candidate_nodes: list[str] = Field(default_factory=list)
    deterministic: bool = True
    tool_profile: str = "default_readonly"
    model_tier: Literal["small", "medium", "large"] = "small"
    guardrail_flags: list[str] = Field(default_factory=list)
    payload_delta: dict[str, Any] = Field(default_factory=dict)
    uncertainty_report: dict[str, Any] = Field(default_factory=dict)


class CapabilitiesState(BaseModel):
    """Tools exposed to the current step."""

    model_config = ConfigDict(extra="forbid")

    loaded_tools: list[str] = Field(default_factory=list)
    withheld_tools: list[str] = Field(default_factory=list)
    permission_level: Literal["none", "readonly", "write"] = "none"
    load_reason: str = ""


class BudgetState(BaseModel):
    """Cost and retry counters for circuit breaking."""

    model_config = ConfigDict(extra="forbid")

    token_used: int = 0
    time_used_sec: int = 0
    step_used: int = 0
    max_steps: int = 120
    retry_used: int = 0
    max_retries: int = 4


class CheckpointState(BaseModel):
    """Checkpoint metadata used for pause and resume."""

    model_config = ConfigDict(extra="forbid")

    last_checkpoint_id: str | None = None
    can_resume: bool = False


class UncertaintyState(BaseModel):
    """Epistemic status with focused user question support."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["none", "blocked"] = "none"
    type: str | None = None
    question_for_user: str | None = None
    blocked_by: list[str] = Field(default_factory=list)


class BreakState(BaseModel):
    """Structured report recorded when run pauses for human input."""

    model_config = ConfigDict(extra="forbid")

    uncertainty_type: str | None = None
    known_now: str = ""
    missing_now: str = ""
    question_for_user: str = ""


class AuditState(BaseModel):
    """Trace metadata and structured events."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(default_factory=lambda: f"trace_{uuid4().hex[:12]}")
    events: list[dict[str, Any]] = Field(default_factory=list)


class RunState(BaseModel):
    """Shared record of what the system is doing right now."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_id: str
    status: Literal["running", "paused", "completed", "failed"] = "running"
    current_node: str = "interaction"
    blueprint_ref: str = "bp_default"
    blueprint_stage: str = "literature_scan"
    goal: str
    payload: PayloadState = Field(default_factory=PayloadState)
    blueprint: BlueprintState = Field(default_factory=BlueprintState)
    memory: MemoryRefs = Field(default_factory=MemoryRefs)
    investigation: InvestigationState = Field(default_factory=InvestigationState)
    routing: RoutingState = Field(default_factory=RoutingState)
    capabilities: CapabilitiesState = Field(default_factory=CapabilitiesState)
    budget: BudgetState = Field(default_factory=BudgetState)
    checkpoint: CheckpointState = Field(default_factory=CheckpointState)
    uncertainty: UncertaintyState = Field(default_factory=UncertaintyState)
    break_state: BreakState = Field(default_factory=BreakState)
    audit: AuditState = Field(default_factory=AuditState)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("current_node", "goal")
    @classmethod
    def _must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    def touch(self) -> "RunState":
        return self.model_copy(update={"updated_at": datetime.now(timezone.utc)})
