from __future__ import annotations

import logging
import sys
from typing import Any, Callable

from agent_os.models.providers.base import BaseProvider, EchoProvider, ProviderResponse

try:
    from litellm import completion as litellm_completion
except ImportError:  # pragma: no cover - handled by factory fallback
    litellm_completion = None

LOGGER = logging.getLogger(__name__)


class LiteLLMProvider(BaseProvider):
    """LiteLLM-backed provider with model-tier routing."""

    def __init__(
        self,
        *,
        small_model: str,
        medium_model: str,
        large_model: str,
        timeout_sec: float = 30.0,
        temperature: float = 0.0,
        max_tokens: int = 800,
        stream: bool = False,
        stream_to_console: bool = True,
        mock_response: str | None = None,
        fallback_provider: BaseProvider | None = None,
        completion_fn: Callable[..., Any] | None = None,
    ) -> None:
        self._model_map = {
            "small": small_model,
            "medium": medium_model,
            "large": large_model,
        }
        self._timeout_sec = timeout_sec
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._stream = stream
        self._stream_to_console = stream_to_console
        self._mock_response = mock_response
        self._fallback_provider = fallback_provider or EchoProvider()
        self._completion_fn = completion_fn or litellm_completion
        self._stream_disabled_models: set[str] = set()
        if self._completion_fn is None:
            raise RuntimeError("litellm is not installed")

    def show_text(self, text: str) -> None:
        if self._stream_to_console and text:
            sys.stdout.write('-'*20 + 'BEGIN TEXT' + '-'*20 + '\n')
            sys.stdout.write(text)
            if not text.endswith("\n"):
                sys.stdout.write("\n")
            sys.stdout.write('-'*20 + 'END TEXT' + '-'*20 + '\n')
            sys.stdout.flush()

    def generate(self, prompt: str, model_tier: str) -> ProviderResponse:
        model_name = self._model_map.get(model_tier, self._model_map["small"])
        use_stream = self._stream and model_name not in self._stream_disabled_models
        request_payload: dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "timeout": self._timeout_sec,
        }
        if use_stream:
            request_payload["stream"] = True
            if not model_name.startswith("zai/"):
                request_payload["stream_options"] = {"include_usage": True}
        if self._mock_response is not None:
            request_payload["mock_response"] = self._mock_response

        try:
            response = self._completion_fn(**request_payload)
        except Exception as exc:
            LOGGER.exception("LiteLLM request failed | model=%s | tier=%s", model_name, model_tier)
            # Fallback keeps local workflow stable when env keys are missing.
            fallback = self._fallback_provider.generate(prompt=prompt, model_tier=model_tier)
            fallback_raw = dict(fallback.raw)
            fallback_raw.update(
                {
                    "fallback_from": "litellm",
                    "litellm_error_type": type(exc).__name__,
                    "litellm_error": str(exc),
                    "requested_model": model_name,
                }
            )
            return fallback.model_copy(update={"raw": fallback_raw})

        if use_stream:
            text, input_tokens, output_tokens = self._consume_stream(response, prompt=prompt)
            if not text.strip():
                self._stream_disabled_models.add(model_name)
                LOGGER.warning(
                    (
                        "LiteLLM stream returned empty text | model=%s | tier=%s | "
                        "retrying non-stream and disabling stream for this model in current process"
                    ),
                    model_name,
                    model_tier,
                )
                retry_response = self._request_non_stream(request_payload)
                text = self._extract_text(retry_response)
                retry_input, retry_output = self._extract_usage(retry_response)
                input_tokens = max(input_tokens, retry_input)
                output_tokens = max(output_tokens, retry_output)
                self.show_text(text)
        else:
            text = self._extract_text(response)
            input_tokens, output_tokens = self._extract_usage(response)
            self.show_text(text)
        if input_tokens <= 0:
            input_tokens = max(1, len(prompt.split()))
        if output_tokens <= 0:
            output_tokens = max(1, len(text.split()))
        return ProviderResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw={
                "provider": "litellm",
                "model": model_name,
                "tier": model_tier,
            },
        )

    def _request_non_stream(self, request_payload: dict[str, Any]) -> Any:
        payload = dict(request_payload)
        payload.pop("stream", None)
        payload.pop("stream_options", None)
        return self._completion_fn(**payload)

    def _consume_stream(self, response: Any, prompt: str) -> tuple[str, int, int]:
        if not self._is_stream_like(response):
            text = self._extract_text(response)
            input_tokens, output_tokens = self._extract_usage(response)
            return text, input_tokens, output_tokens

        parts: list[str] = []
        input_tokens = 0
        output_tokens = 0
        has_visible_token = False
        last_chunk: Any = None
        for chunk in response:
            last_chunk = chunk
            token_text = self._extract_stream_text(chunk)
            if token_text:
                parts.append(token_text)
                has_visible_token = True
                if self._stream_to_console:
                    sys.stdout.write(token_text)
                    sys.stdout.flush()
            chunk_input_tokens, chunk_output_tokens = self._extract_usage(chunk)
            input_tokens = max(input_tokens, chunk_input_tokens)
            output_tokens = max(output_tokens, chunk_output_tokens)

        if self._stream_to_console and has_visible_token:
            sys.stdout.write("\n")
            sys.stdout.flush()

        text = "".join(parts)
        if not text and last_chunk is not None:
            # Some providers may emit final full content on the last chunk.
            text = self._extract_text(last_chunk)
        return text, input_tokens, output_tokens

    def _extract_stream_text(self, chunk: Any) -> str:
        choices = self._read_attr(chunk, "choices", default=[])
        if not choices:
            return ""
        first_choice = choices[0]
        delta = self._read_attr(first_choice, "delta", default={})
        content = self._read_attr(delta, "content", default="")
        if isinstance(content, str):
            if content:
                return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                text = self._read_attr(item, "text", default="")
                if text:
                    parts.append(str(text))
            return "".join(parts)
        if content:
            return str(content)
        # Fallback for providers that stream message.content directly.
        message = self._read_attr(first_choice, "message", default={})
        message_content = self._read_attr(message, "content", default="")
        if isinstance(message_content, str):
            if message_content:
                return message_content
        return ""

    def _is_stream_like(self, response: Any) -> bool:
        if isinstance(response, (str, bytes, dict)):
            return False
        return hasattr(response, "__iter__")

    def _extract_text(self, response: Any) -> str:
        choices = self._read_attr(response, "choices", default=[])
        if not choices:
            return ""
        first_choice = choices[0]
        message = self._read_attr(first_choice, "message", default={})
        content = self._read_attr(message, "content", default="")
        if isinstance(content, str):
            if content:
                return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                text = self._read_attr(item, "text", default="")
                if text:
                    parts.append(str(text))
            return "\n".join(parts)
        return str(content)

    def _extract_usage(self, response: Any) -> tuple[int, int]:
        usage = self._read_attr(response, "usage", default={})
        input_tokens = int(self._read_attr(usage, "prompt_tokens", default=0) or 0)
        output_tokens = int(self._read_attr(usage, "completion_tokens", default=0) or 0)
        return input_tokens, output_tokens

    def _read_attr(self, source: Any, key: str, default: Any) -> Any:
        if isinstance(source, dict):
            return source.get(key, default)
        return getattr(source, key, default)
