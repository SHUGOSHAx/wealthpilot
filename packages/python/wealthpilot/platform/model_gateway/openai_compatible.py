"""OpenAI-compatible production gateway with env-only credentials.

No request, response, or credential is logged or persisted here.  Tests inject a
transport; the default transport performs the only network operation.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .gateway import ModelGateway, ModelOutputError
from .models import ModelRequest, ModelResponse


class ModelProviderError(RuntimeError):
    """Safe provider error that never contains response bodies or secrets."""


@dataclass(frozen=True, slots=True)
class OpenAICompatibleConfig:
    base_url: str
    model: str
    api_key: str = field(repr=False)
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "OpenAICompatibleConfig":
        values = os.environ if environ is None else environ
        try:
            base_url = values["WEALTHPILOT_MODEL_BASE_URL"].rstrip("/")
            model = values["WEALTHPILOT_MODEL_NAME"]
            api_key = values["WEALTHPILOT_MODEL_API_KEY"]
        except KeyError as exc:
            raise ModelProviderError(f"missing model configuration: {exc.args[0]}") from None
        if not base_url.startswith(("https://", "http://")) or not model or not api_key:
            raise ModelProviderError("invalid model configuration")
        try:
            timeout = float(values.get("WEALTHPILOT_MODEL_TIMEOUT_SECONDS", "30"))
        except ValueError:
            raise ModelProviderError("invalid model timeout") from None
        if not 0 < timeout <= 120:
            raise ModelProviderError("model timeout must be between 0 and 120 seconds")
        return cls(base_url=base_url, model=model, api_key=api_key, timeout_seconds=timeout)


Transport = Callable[[str, Mapping[str, str], bytes, float], dict[str, Any]]


class OpenAICompatibleModelGateway(ModelGateway):
    def __init__(self, config: OpenAICompatibleConfig | None = None, *, transport: Transport | None = None) -> None:
        self.config = config or OpenAICompatibleConfig.from_env()
        self._transport = transport or _urlopen_transport

    def _generate(self, request: ModelRequest) -> ModelResponse:
        body = json.dumps(
            {
                "model": self.config.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Return only JSON matching response_contract. Use only supplied facts; "
                            "never invent missing values or authoritative financial, risk, suitability, "
                            "allocation, or trading decisions. Every research claim must cite supplied evidence IDs."
                        ),
                    },
                    {"role": "user", "content": json.dumps(request.as_payload(), ensure_ascii=False, separators=(",", ":"))},
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"}
        try:
            raw = self._transport(
                f"{self.config.base_url}/chat/completions", headers, body, self.config.timeout_seconds
            )
            message = raw["choices"][0]["message"]["content"]
            output = json.loads(message) if isinstance(message, str) else message
        except ModelProviderError:
            raise
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ModelOutputError("model provider returned invalid structured output") from exc
        return ModelResponse(
            structured_output=output,
            provider="openai-compatible",
            model=self.config.model,
            cached=False,
        )


def _urlopen_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured provider URL
            return json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ModelProviderError("model provider request failed") from exc
