from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agent_os.models.json_parser import extract_json_object, parse_json_as_model


class DemoPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: int


def test_json_parser_extracts_fenced_json() -> None:
    text = "prefix\n```json\n{\"name\":\"demo\",\"value\":2}\n```\nsuffix"
    payload = extract_json_object(text)
    assert payload is not None
    assert payload["name"] == "demo"


def test_json_parser_parses_model() -> None:
    text = '{"name":"demo","value":3}'
    payload = parse_json_as_model(text, DemoPayload)
    assert payload is not None
    assert payload.name == "demo"
    assert payload.value == 3

