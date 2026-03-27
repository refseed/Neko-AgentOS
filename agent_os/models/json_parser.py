from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel

try:
    from json_repair import repair_json as _repair_json  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency
    _repair_json = None

T = TypeVar("T", bound=BaseModel)


def _extract_json_candidates(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []

    candidates: list[str] = [stripped]

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())

    left = stripped.find("{")
    right = stripped.rfind("}")
    if left >= 0 and right > left:
        candidates.append(stripped[left : right + 1].strip())

    return list(dict.fromkeys(candidates))


def _json_loads_robust(candidate: str) -> dict[str, Any] | None:
    try:
        value = json.loads(candidate)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    if _repair_json is None:
        return None

    # json_repair API has minor version differences; handle both return modes.
    try:
        repaired = _repair_json(candidate)  # type: ignore[misc]
    except TypeError:
        repaired = _repair_json(candidate, return_objects=False)  # type: ignore[misc]
    except Exception:
        return None

    if isinstance(repaired, dict):
        return repaired
    if isinstance(repaired, str):
        try:
            value = json.loads(repaired)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            return None
    return None


def extract_json_object(text: str) -> dict[str, Any] | None:
    """Best-effort extraction of one JSON object from model text output."""

    for candidate in _extract_json_candidates(text):
        payload = _json_loads_robust(candidate)
        if payload is not None:
            return payload
    return None


def parse_json_as_model(text: str, model_cls: type[T]) -> T | None:
    """Parse model text as the target pydantic model using robust JSON recovery."""

    payload = extract_json_object(text)
    if payload is None:
        return None
    try:
        return model_cls.model_validate(payload)
    except Exception:
        return None

