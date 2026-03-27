from __future__ import annotations

from dataclasses import dataclass

from agent_os.runtime.state.models import RunState


@dataclass(frozen=True)
class MemoryMount:
    """One request to load a saved memory item into active work."""

    source: str
    ref_id: str
    detail_level: str


class MemoryRouter:
    """Select memory mounts needed for the next node."""

    def plan_mounts(self, state: RunState, next_node: str) -> list[MemoryMount]:
        mounts: list[MemoryMount] = []
        if next_node == "strategist":
            detail_level = "L1"
        elif next_node == "reflection":
            detail_level = "L3"
        else:
            detail_level = "L2"

        if next_node in {"strategist", "reasoning", "reflection"} and state.memory.blackboard_ref:
            mounts.append(
                MemoryMount(
                    source="blackboard",
                    ref_id=state.memory.blackboard_ref,
                    detail_level="L1",
                )
            )

        for ref_id in state.memory.ram_refs[:2]:
            mounts.append(MemoryMount(source="ram", ref_id=ref_id, detail_level=detail_level))
        for ref_id in state.memory.cache_refs[:2]:
            mounts.append(MemoryMount(source="cache", ref_id=ref_id, detail_level=detail_level))
        if next_node in {"reasoning", "reflection"}:
            for ref_id in state.memory.disk_refs[:2]:
                mounts.append(MemoryMount(source="disk", ref_id=ref_id, detail_level=detail_level))
        return mounts
