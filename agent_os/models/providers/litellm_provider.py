from __future__ import annotations

from typing import Any, Callable

from agent_os.models.providers.base import BaseProvider, EchoProvider, ProviderResponse

try:
    from litellm import completion as litellm_completion
except ImportError:  # pragma: no cover - handled by factory fallback
    litellm_completion = None


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
        self._mock_response = mock_response
        self._fallback_provider = fallback_provider or EchoProvider()
        self._completion_fn = completion_fn or litellm_completion
        if self._completion_fn is None:
            raise RuntimeError("litellm is not installed")

    def generate(self, prompt: str, model_tier: str) -> ProviderResponse:
        model_name = self._model_map.get(model_tier, self._model_map["small"])
        request_payload: dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "timeout": self._timeout_sec,
        }
        if self._mock_response is not None:
            request_payload["mock_response"] = self._mock_response

        try:
            response = self._completion_fn(**request_payload)
        except Exception:
            # Fallback keeps local workflow stable when env keys are missing.
            return self._fallback_provider.generate(prompt=prompt, model_tier=model_tier)

        text = self._extract_text(response)
        input_tokens, output_tokens = self._extract_usage(response)
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

    def _extract_text(self, response: Any) -> str:
        choices = self._read_attr(response, "choices", default=[])
        if not choices:
            return ""
        first_choice = choices[0]
        message = self._read_attr(first_choice, "message", default={})
        content = self._read_attr(message, "content", default="")
        if isinstance(content, str):
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
