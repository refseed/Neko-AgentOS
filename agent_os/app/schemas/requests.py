from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StartRunRequest(BaseModel):
    """Normalized input for start-run command."""

    model_config = ConfigDict(extra="forbid")

    goal: str
    source_paths: list[str] = Field(default_factory=list)

    @field_validator("goal")
    @classmethod
    def _goal_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("goal must not be empty")
        return value

    @field_validator("source_paths")
    @classmethod
    def _normalize_sources(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            normalized.append(str(Path(value)))
        return normalized


class ResumeRunRequest(BaseModel):
    """Normalized input for resume-run command."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    user_answer: str | None = None
