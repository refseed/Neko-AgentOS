from __future__ import annotations

from pathlib import Path
import tomllib

from pydantic import BaseModel, ConfigDict, Field


class RuntimeConfig(BaseModel):
    """Runtime and persistence settings."""

    model_config = ConfigDict(extra="forbid")

    data_dir: str = ".agent_os"
    checkpoint_db: str = "checkpoints.sqlite3"
    snapshot_dir: str = "snapshots"
    semantic_disk_dir: str = "semantic_disk"
    trace_dir: str = "traces"
    max_steps: int = 120
    max_retries: int = 4
    max_node_iterations: int = 200
    max_cache_refs: int = 12


class ModelConfig(BaseModel):
    """Model provider configuration loaded from file."""

    model_config = ConfigDict(extra="forbid")

    provider: str = "litellm"
    small_model: str = "gpt-4o-mini"
    medium_model: str = "gpt-4o-mini"
    large_model: str = "gpt-4o"
    timeout_sec: float = 30.0
    temperature: float = 0.0
    max_tokens: int = 800
    use_mock: bool = False
    mock_response: str = (
        "Draft based on current evidence. If evidence is missing, investigation should gather source-backed facts."
    )


class InvestigationConfig(BaseModel):
    """Controls investigation loop and stop conditions."""

    model_config = ConfigDict(extra="forbid")

    min_fact_count: int = 2
    min_source_count: int = 1
    max_rounds: int = 3
    max_facts_per_round: int = 3


class BlueprintConfig(BaseModel):
    """Controls blueprint entry policy and default activation."""

    model_config = ConfigDict(extra="forbid")

    enabled_by_default: bool = False
    entry_keywords: list[str] = Field(
        default_factory=lambda: [
            "paper",
            "chapter",
            "outline",
            "blueprint",
            "plan",
            "写作",
            "论文",
            "大纲",
            "计划",
        ]
    )


class ReflectionConfig(BaseModel):
    """Reflection review guardrails."""

    model_config = ConfigDict(extra="forbid")

    max_review_loops: int = 3
    min_draft_chars: int = 24


class CapabilityConfig(BaseModel):
    """Node-level capability profile map."""

    model_config = ConfigDict(extra="forbid")

    permission_by_node: dict[str, str] = Field(
        default_factory=lambda: {
            "strategist": "readonly",
            "blueprint": "none",
            "reasoning": "readonly",
            "investigation": "readonly",
            "reflection": "readonly",
            "break": "none",
            "finish": "none",
        }
    )


class BlackboardConfig(BaseModel):
    """Stable constants mounted into context."""

    model_config = ConfigDict(extra="forbid")

    constants: dict[str, str] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    """Top-level application config."""

    model_config = ConfigDict(extra="forbid")

    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    investigation: InvestigationConfig = Field(default_factory=InvestigationConfig)
    blueprint: BlueprintConfig = Field(default_factory=BlueprintConfig)
    reflection: ReflectionConfig = Field(default_factory=ReflectionConfig)
    capability: CapabilityConfig = Field(default_factory=CapabilityConfig)
    blackboard: BlackboardConfig = Field(default_factory=BlackboardConfig)


def load_agent_config(workspace_root: Path, config_path: Path | None = None) -> AgentConfig:
    """Load config from explicit path, workspace config, or repository default."""

    candidate_paths: list[Path] = []
    if config_path is not None:
        candidate_paths.append(config_path)
    candidate_paths.append(workspace_root / "config" / "agent_os.toml")
    candidate_paths.append(Path(__file__).resolve().parents[2] / "config" / "agent_os.toml")

    for candidate in candidate_paths:
        if candidate.exists() and candidate.is_file():
            raw = tomllib.loads(candidate.read_text(encoding="utf-8"))
            return AgentConfig.model_validate(raw)

    return AgentConfig()
