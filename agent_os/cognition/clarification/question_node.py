from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from agent_os.models.json_parser import extract_json_object
from agent_os.runtime.nodes.base import NODE_PROTOCOL_VERSION, NodeEnvelopeMixin, NodeGateway


class ClarificationQuestionInput(BaseModel):
    """Protocol input for user-interaction generation node."""

    model_config = ConfigDict(extra="forbid")

    goal: str
    stage: str
    stage_status: str
    has_source_refs: bool
    context_entry_count: int
    pending_questions: list[str] = Field(default_factory=list)
    draft_preview: str = ""
    interaction_message: str = ""
    uncertainty_type: str | None = None
    blocked_by: list[str] = Field(default_factory=list)


class ClarificationQuestionOutput(NodeEnvelopeMixin):
    """Protocol output for user-facing interaction text."""

    node_name: str = "clarification_question"
    question_for_user: str
    pending_questions: list[str] = Field(default_factory=list)


class ClarificationQuestionError(RuntimeError):
    """Raised when clarification generation fails strict validation."""


class ClarificationQuestionNode:
    """Model-driven interaction node that turns upstream intent into user-facing text."""

    def __init__(
        self,
        node_name: str,
        model_gateway: NodeGateway | None = None,
        *,
        max_parse_retries: int = 2,
    ) -> None:
        self._node_name = node_name
        self._model_gateway = model_gateway
        self._max_parse_retries = max(0, int(max_parse_retries))

    def ask(
        self,
        *,
        goal: str,
        stage: str,
        stage_status: str,
        has_source_refs: bool,
        context_entry_count: int,
        pending_questions: list[str],
        draft_preview: str,
        interaction_message: str | None = None,
        uncertainty_type: str | None = None,
        blocked_by: list[str] | None = None,
        model_tier: str = "small",
    ) -> ClarificationQuestionOutput:
        node_input = ClarificationQuestionInput(
            goal=goal,
            stage=stage,
            stage_status=stage_status,
            has_source_refs=has_source_refs,
            context_entry_count=context_entry_count,
            pending_questions=list(pending_questions),
            draft_preview=draft_preview,
            interaction_message=(interaction_message or "").strip(),
            uncertainty_type=uncertainty_type,
            blocked_by=list(blocked_by or []),
        )
        return self.run(node_input=node_input, model_tier=model_tier)

    def run(self, node_input: ClarificationQuestionInput, model_tier: str) -> ClarificationQuestionOutput:
        if self._model_gateway is None:
            raise ClarificationQuestionError("clarification_question requires an available model gateway")

        base_prompt = self.build_prompt(node_input)
        max_attempts = self._max_parse_retries + 1
        last_error = "unknown_error"
        last_preview = ""

        for attempt in range(1, max_attempts + 1):
            prompt = (
                base_prompt
                if attempt == 1
                else self._build_retry_prompt(
                    base_prompt=base_prompt,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    last_error=last_error,
                    last_preview=last_preview,
                )
            )
            try:
                response = self._model_gateway.request(prompt=prompt, model_tier=model_tier)
            except Exception as exc:  # noqa: BLE001
                last_error = f"model request failed: {exc}"
                if attempt == max_attempts:
                    raise ClarificationQuestionError(
                        f"clarification_question model request failed after {max_attempts} attempts: {exc}"
                    ) from exc
                continue

            payload = extract_json_object(response.text)
            if payload is None:
                last_preview = response.text[:1000]
                last_error = (
                    "json parse failed "
                    f"| response_len={len(response.text)} | response_preview={last_preview}"
                )
                if attempt == max_attempts:
                    raise ClarificationQuestionError(
                        "clarification_question JSON parse failed "
                        f"after {max_attempts} attempts | response_len={len(response.text)} "
                        f"| response_preview={last_preview}"
                    )
                continue

            normalized_payload = self._normalize_payload(payload)
            try:
                parsed = ClarificationQuestionOutput.model_validate(normalized_payload)
            except Exception as exc:  # noqa: BLE001
                last_error = f"schema validation failed | payload={normalized_payload} | error={exc}"
                if attempt == max_attempts:
                    raise ClarificationQuestionError(
                        "clarification_question schema validation failed "
                        f"after {max_attempts} attempts | payload={normalized_payload} | error={exc}"
                    ) from exc
                continue

            if parsed.protocol_version != NODE_PROTOCOL_VERSION:
                last_error = f"protocol_version mismatch: {parsed.protocol_version!r}"
                if attempt == max_attempts:
                    raise ClarificationQuestionError(
                        f"clarification_question protocol_version mismatch after {max_attempts} attempts: "
                        f"{parsed.protocol_version!r}"
                    )
                continue

            if parsed.node_name and parsed.node_name != self._node_name:
                last_error = f"node_name mismatch: {parsed.node_name!r}"
                if attempt == max_attempts:
                    raise ClarificationQuestionError(
                        f"clarification_question node_name mismatch after {max_attempts} attempts: "
                        f"{parsed.node_name!r}"
                    )
                continue

            validated, error = self._validate_semantics(parsed=parsed, node_input=node_input)
            if error is not None:
                last_error = error
                if attempt == max_attempts:
                    raise ClarificationQuestionError(
                        f"clarification_question semantic validation failed after {max_attempts} attempts: {error}"
                    )
                continue
            return validated

        raise ClarificationQuestionError(
            f"clarification_question failed after {max_attempts} attempts | last_error={last_error}"
        )

    def build_prompt(self, node_input: ClarificationQuestionInput) -> str:
        pending_text = "\n".join(f"- {item}" for item in node_input.pending_questions[:8]) or "- none"
        blocked_text = ", ".join(node_input.blocked_by) or "none"
        return (
            "Role: clarification_question node.\n"
            "You are the model-facing user interaction writer.\n"
            "Upstream nodes already decided user participation is required.\n"
            "Your job is to produce user-facing interaction text only.\n"
            "Important: this is not limited to asking questions.\n"
            "It may ask user to provide info, upload artifacts, confirm choices, or execute actions.\n"
            "Hard output contract:\n"
            "- Output strict JSON only. No markdown. No analysis text.\n"
            "- Required keys: protocol_version, node_name, confidence, notes, question_for_user, pending_questions.\n"
            "- protocol_version='node-io/v1'. node_name='clarification_question'.\n"
            "- question_for_user must contain 1-3 numbered actionable lines.\n"
            "- pending_questions must contain the same 1-3 atomic actionable items.\n"
            "- Use same language as goal.\n"
            "- Do not invent requirements unrelated to upstream intent.\n"
            "- If has_source_refs=false, do not force file paths unless upstream intent explicitly asks for artifacts.\n"
            "Return exactly one JSON object.\n"
            f"goal={node_input.goal}\n"
            f"stage={node_input.stage}\n"
            f"stage_status={node_input.stage_status}\n"
            f"has_source_refs={node_input.has_source_refs}\n"
            f"context_entry_count={node_input.context_entry_count}\n"
            f"uncertainty_type={node_input.uncertainty_type}\n"
            f"blocked_by={blocked_text}\n"
            f"upstream_interaction_message={node_input.interaction_message}\n"
            f"upstream_pending_items:\n{pending_text}\n"
            f"draft_preview={node_input.draft_preview[:300]}\n"
        )

    def _build_retry_prompt(
        self,
        *,
        base_prompt: str,
        attempt: int,
        max_attempts: int,
        last_error: str,
        last_preview: str,
    ) -> str:
        return (
            "Your previous output is invalid for this protocol.\n"
            f"retry_attempt={attempt}/{max_attempts}\n"
            f"last_error={last_error[:300]}\n"
            f"last_response_preview={last_preview[:300]}\n"
            "Fix and output JSON only.\n"
            '{"protocol_version":"node-io/v1","node_name":"clarification_question","confidence":0.8,'
            '"notes":["..."],"question_for_user":"1. ...\\n2. ...","pending_questions":["...","..."]}\n'
            f"{base_prompt}\n"
        )

    def _validate_semantics(
        self,
        *,
        parsed: ClarificationQuestionOutput,
        node_input: ClarificationQuestionInput,
    ) -> tuple[ClarificationQuestionOutput, str | None]:
        question = parsed.question_for_user.strip()
        pending = [item.strip() for item in parsed.pending_questions if item.strip()]
        if not question:
            return parsed, "missing question_for_user"
        if not pending:
            return parsed, "missing pending_questions"
        if not self._is_actionable_text(question=question, node_input=node_input):
            return parsed, "question_for_user is not actionable or language-mismatched"
        return (
            parsed.model_copy(
                update={
                    "question_for_user": question,
                    "pending_questions": list(dict.fromkeys(pending))[:3],
                }
            ),
            None,
        )

    def _contains_cjk(self, text: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", text))

    def _is_actionable_text(self, *, question: str, node_input: ClarificationQuestionInput) -> bool:
        if len(question) < 20:
            return False
        if not re.search(r"(^|\n)\d+\.\s*", question):
            return False
        if self._contains_cjk(node_input.goal) and not self._contains_cjk(question):
            return False
        generic_markers = (
            "please provide more details",
            "请提供更多信息",
            "请补充更多信息",
        )
        lowered = question.lower()
        if any(marker in lowered for marker in generic_markers):
            return False
        return True

    def _normalize_payload(self, payload: dict[str, object]) -> dict[str, object]:
        normalized = dict(payload)

        notes_value = normalized.get("notes")
        if isinstance(notes_value, str):
            normalized["notes"] = [notes_value]
        elif isinstance(notes_value, list):
            normalized["notes"] = [str(item).strip() for item in notes_value if str(item).strip()]
        elif notes_value is None:
            normalized["notes"] = []
        else:
            normalized["notes"] = [str(notes_value)]

        pending_value = normalized.get("pending_questions")
        if isinstance(pending_value, str):
            parts = [item.strip(" -\t") for item in re.split(r"[\n\r;；]+", pending_value) if item.strip()]
            normalized["pending_questions"] = parts
        elif isinstance(pending_value, list):
            normalized["pending_questions"] = [str(item).strip() for item in pending_value if str(item).strip()]
        elif pending_value is None:
            normalized["pending_questions"] = []
        else:
            normalized["pending_questions"] = [str(pending_value).strip()]

        question_value = normalized.get("question_for_user")
        if isinstance(question_value, list):
            normalized["question_for_user"] = "\n".join(
                str(item).strip() for item in question_value if str(item).strip()
            )
        elif question_value is None:
            normalized["question_for_user"] = ""
        else:
            normalized["question_for_user"] = str(question_value)

        confidence_value = normalized.get("confidence")
        if confidence_value is not None:
            try:
                normalized["confidence"] = float(confidence_value)
            except (TypeError, ValueError):
                normalized["confidence"] = 0.0
        return normalized
