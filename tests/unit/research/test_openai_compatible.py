from __future__ import annotations

import json

import pytest

from wealthpilot.platform.model_gateway import (
    ModelProviderError,
    ModelRequest,
    OpenAICompatibleConfig,
    OpenAICompatibleModelGateway,
)


def request() -> ModelRequest:
    return ModelRequest(
        symbol="600519",
        question="研究",
        public_research={
            "company_name": "贵州茅台",
            "evidence": [{"evidence_id": "source:1", "as_of": "2026-09-05"}],
        },
        financial_metrics={},
        privacy_level="P0",
        task_type="A_SHARE_RESEARCH_MEMO",
        response_contract="EQUITY_RESEARCH_MEMO_V1",
    )


def test_injected_transport_receives_env_config_without_secret_in_body() -> None:
    captured: dict[str, object] = {}

    def transport(url, headers, body, timeout):  # type: ignore[no-untyped-def]
        captured.update(url=url, headers=headers, body=body, timeout=timeout)
        content = {
            "research_summary": "有证据的摘要",
            "key_positives": [{"claim": "公开事实", "evidence_ids": ["source:1"]}],
            "key_risks": [],
        }
        return {"choices": [{"message": {"content": json.dumps(content)}}]}

    config = OpenAICompatibleConfig.from_env(
        {
            "WEALTHPILOT_MODEL_BASE_URL": "https://model.example/v1/",
            "WEALTHPILOT_MODEL_NAME": "demo-model",
            "WEALTHPILOT_MODEL_API_KEY": "test-key-never-persisted",
            "WEALTHPILOT_MODEL_TIMEOUT_SECONDS": "12",
        }
    )
    assert "test-key-never-persisted" not in repr(config)
    result = OpenAICompatibleModelGateway(config, transport=transport).generate_structured(request())
    assert result.structured_output["research_summary"] == "有证据的摘要"
    assert captured["url"] == "https://model.example/v1/chat/completions"
    assert captured["timeout"] == 12.0
    assert captured["headers"]["Authorization"] == "Bearer test-key-never-persisted"  # type: ignore[index]
    assert b"test-key-never-persisted" not in captured["body"]  # type: ignore[operator]


def test_missing_env_configuration_fails_closed() -> None:
    with pytest.raises(ModelProviderError, match="WEALTHPILOT_MODEL_API_KEY"):
        OpenAICompatibleConfig.from_env(
            {"WEALTHPILOT_MODEL_BASE_URL": "https://model.example/v1", "WEALTHPILOT_MODEL_NAME": "model"}
        )
