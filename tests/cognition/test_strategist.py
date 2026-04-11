from __future__ import annotations

from types import SimpleNamespace

from agent_os.cognition.resource_manager.resource_manager import ResourceDecision
from agent_os.cognition.strategist.strategist import Strategist
from agent_os.runtime.state.models import BlueprintState, InvestigationState, PayloadState, RunState


def test_strategist_routes_to_reasoning_when_no_draft() -> None:
    strategist = Strategist()
    state = RunState(run_id="run_1", task_id="task_1", goal="demo")
    decision = strategist.decide(
        state=state,
        resource=ResourceDecision(allow_execution=True, model_tier="small", reason="ok"),
    )
    assert decision.next_node == "reasoning"


def test_strategist_routes_to_break_on_blocked_budget() -> None:
    strategist = Strategist()
    state = RunState(run_id="run_1", task_id="task_1", goal="demo")
    decision = strategist.decide(
        state=state,
        resource=ResourceDecision(
            allow_execution=False,
            model_tier="small",
            reason="max_steps_exceeded",
        ),
    )
    assert decision.next_node == "break"


def test_strategist_can_use_model_json_route() -> None:
    class FakeGateway:
        def request(self, prompt: str, model_tier: str):
            return SimpleNamespace(
                text='{"next_node":"reflection","confidence":0.91,"tool_profile":"reflection_readonly","guardrail_flags":[]}'
            )

    strategist = Strategist(model_gateway=FakeGateway())
    state = RunState(run_id="run_1", task_id="task_1", goal="demo")
    decision = strategist.decide(
        state=state,
        resource=ResourceDecision(allow_execution=True, model_tier="small", reason="ok"),
    )
    assert decision.next_node == "reflection"


def test_strategist_respects_allowed_targets() -> None:
    strategist = Strategist()
    state = RunState(run_id="run_1", task_id="task_1", goal="demo")
    decision = strategist.decide(
        state=state,
        resource=ResourceDecision(allow_execution=True, model_tier="small", reason="ok"),
        allowed_targets={"reflection"},
    )
    assert decision.next_node == "reflection"


def test_strategist_can_enable_blueprint_for_planning_goal() -> None:
    strategist = Strategist()
    state = RunState(
        run_id="run_1",
        task_id="task_1",
        goal="write a paper outline with chapter planning",
    )
    decision = strategist.decide(
        state=state,
        resource=ResourceDecision(allow_execution=True, model_tier="small", reason="ok"),
    )
    assert decision.next_node == "blueprint"


def test_strategist_build_prompt_is_used_when_gateway_exists() -> None:
    captured: dict[str, str] = {}

    class FakeGateway:
        def request(self, prompt: str, model_tier: str):
            captured["prompt"] = prompt
            return SimpleNamespace(
                text='{"next_node":"reasoning","confidence":0.9,"tool_profile":"reasoning_readonly","guardrail_flags":[]}'
            )

    strategist = Strategist(model_gateway=FakeGateway())
    state = RunState(run_id="run_1", task_id="task_1", goal="demo")
    strategist.decide(
        state=state,
        resource=ResourceDecision(allow_execution=True, model_tier="small", reason="ok"),
    )
    assert "allowed_targets=" in captured["prompt"]


def test_strategist_uses_meta_selected_model_tier() -> None:
    class FakeGateway:
        def request(self, prompt: str, model_tier: str):
            return SimpleNamespace(
                text=(
                    '{"next_node":"reasoning","confidence":0.93,"tool_profile":"reasoning_readonly",'
                    '"model_tier":"large","guardrail_flags":[]}'
                )
            )

    strategist = Strategist(model_gateway=FakeGateway())
    state = RunState(run_id="run_1", task_id="task_1", goal="demo")
    decision = strategist.decide(
        state=state,
        resource=ResourceDecision(allow_execution=True, model_tier="small", reason="ok"),
    )
    assert decision.model_tier == "large"


def test_strategist_escalates_low_confidence_to_stronger_review() -> None:
    calls: list[str] = []

    class FakeGateway:
        def request(self, prompt: str, model_tier: str):
            calls.append(model_tier)
            confidence = 0.45 if len(calls) == 1 else 0.91
            return SimpleNamespace(
                text=(
                    '{"next_node":"reasoning","confidence":'
                    f"{confidence}"
                    ',"tool_profile":"reasoning_readonly","model_tier":"medium","guardrail_flags":[]}'
                )
            )

    strategist = Strategist(model_gateway=FakeGateway(), low_confidence_threshold=0.7)
    state = RunState(run_id="run_1", task_id="task_1", goal="demo")
    decision = strategist.decide(
        state=state,
        resource=ResourceDecision(allow_execution=True, model_tier="small", reason="ok"),
    )

    assert calls == ["small", "medium"]
    assert decision.next_node == "reasoning"
    assert "low_confidence_recovered_by_review" in decision.guardrail_flags


def test_strategist_breaks_when_review_still_low_confidence() -> None:
    calls: list[str] = []

    class FakeGateway:
        def request(self, prompt: str, model_tier: str):
            calls.append(model_tier)
            return SimpleNamespace(
                text=(
                    '{"next_node":"reasoning","confidence":0.4,"tool_profile":"reasoning_readonly",'
                    '"model_tier":"medium","guardrail_flags":[]}'
                )
            )

    strategist = Strategist(model_gateway=FakeGateway(), low_confidence_threshold=0.7)
    state = RunState(run_id="run_1", task_id="task_1", goal="demo")
    decision = strategist.decide(
        state=state,
        resource=ResourceDecision(allow_execution=True, model_tier="small", reason="ok"),
    )

    assert calls == ["small", "medium"]
    assert decision.next_node == "break"
    assert decision.uncertainty_report.status == "blocked"


def test_strategist_breaks_when_investigation_needed_but_unavailable() -> None:
    strategist = Strategist()
    state = RunState(
        run_id="run_1",
        task_id="task_1",
        goal="demo",
        payload=PayloadState(stage_result="need_more_evidence"),
        blueprint=BlueprintState(stage_status="need_more_evidence"),
        investigation=InvestigationState(active=True),
    )
    decision = strategist.decide(
        state=state,
        resource=ResourceDecision(allow_execution=True, model_tier="small", reason="ok"),
        allowed_targets={"reasoning", "reflection", "break", "finish"},
    )
    assert decision.next_node == "break"
    assert "investigation_unavailable" in decision.guardrail_flags
    assert decision.uncertainty_report.status == "blocked"


def test_strategist_routes_to_reflection_when_draft_exists_and_in_progress() -> None:
    strategist = Strategist()
    state = RunState(
        run_id="run_1",
        task_id="task_1",
        goal="demo",
        payload=PayloadState(draft_text="This is a completed draft answer."),
        blueprint=BlueprintState(stage_status="in_progress", stage_attempts=1),
    )
    decision = strategist.decide(
        state=state,
        resource=ResourceDecision(allow_execution=True, model_tier="small", reason="ok"),
    )
    assert decision.next_node == "reflection"
    assert decision.confidence >= 0.9


def test_strategist_repetition_guard_overrides_llm_reasoning_loop() -> None:
    class FakeGateway:
        def request(self, prompt: str, model_tier: str):
            return SimpleNamespace(
                text='{"next_node":"reasoning","confidence":0.88,"tool_profile":"reasoning_readonly","guardrail_flags":[]}'
            )

    strategist = Strategist(model_gateway=FakeGateway())
    state = RunState(
        run_id="run_1",
        task_id="task_1",
        goal="demo",
        payload=PayloadState(draft_text="A valid draft."),
        blueprint=BlueprintState(stage_status="in_progress", stage_attempts=3),
    )
    decision = strategist.decide(
        state=state,
        resource=ResourceDecision(allow_execution=True, model_tier="small", reason="ok"),
    )
    assert decision.next_node == "reflection"


def test_strategist_routes_to_investigation_when_available() -> None:
    strategist = Strategist()
    state = RunState(
        run_id="run_1",
        task_id="task_1",
        goal="demo",
        payload=PayloadState(stage_result="need_more_evidence"),
        blueprint=BlueprintState(stage_status="need_more_evidence"),
        investigation=InvestigationState(active=True),
    )
    decision = strategist.decide(
        state=state,
        resource=ResourceDecision(allow_execution=True, model_tier="small", reason="ok"),
        allowed_targets={"reasoning", "investigation", "reflection", "break", "finish"},
    )
    assert decision.next_node == "investigation"
