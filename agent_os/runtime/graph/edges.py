from __future__ import annotations


def build_main_graph_edges() -> dict[str, set[str]]:
    """Return legal edges for the MVP main graph."""

    return {
        "interaction": {"strategist"},
        "strategist": {"blueprint", "reasoning", "investigation", "reflection", "break", "finish"},
        "blueprint": {"strategist", "finish", "break"},
        "reasoning": {"strategist", "break"},
        "investigation": {"strategist", "break"},
        "reflection": {"strategist", "break"},
        "break": {"finish"},
        "finish": {"finish"},
    }
