from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_os.runtime.state.models import RunState


def test_run_state_valid_model() -> None:
    state = RunState(run_id="run_demo", task_id="task_demo", goal="read one paper")
    assert state.current_node == "interaction"
    assert state.memory.ram_refs == []
    assert state.blueprint.enabled is False


def test_run_state_rejects_empty_goal() -> None:
    with pytest.raises(ValidationError):
        RunState(run_id="run_demo", task_id="task_demo", goal="   ")
