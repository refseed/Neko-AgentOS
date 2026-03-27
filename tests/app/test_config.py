from __future__ import annotations

from pathlib import Path

from agent_os.app.config import load_agent_config


def test_config_loader_reads_blueprint_and_reflection_sections(tmp_path: Path) -> None:
    config_path = tmp_path / "agent_os.toml"
    config_path.write_text(
        (
            "[blueprint]\n"
            "enabled_by_default = true\n"
            "entry_keywords = [\"paper\", \"outline\"]\n\n"
            "[reflection]\n"
            "max_review_loops = 5\n"
            "min_draft_chars = 48\n"
        ),
        encoding="utf-8",
    )

    config = load_agent_config(workspace_root=tmp_path, config_path=config_path)

    assert config.blueprint.enabled_by_default is True
    assert config.blueprint.entry_keywords == ["paper", "outline"]
    assert config.reflection.max_review_loops == 5
    assert config.reflection.min_draft_chars == 48
