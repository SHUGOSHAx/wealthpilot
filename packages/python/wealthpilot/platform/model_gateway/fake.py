"""Offline, deterministic model adapter used by the MVP demo and tests."""

from __future__ import annotations

from copy import deepcopy

from .gateway import ModelGateway
from .models import ModelRequest, ModelResponse


class FakeModelGateway(ModelGateway):
    """A no-network gateway with capture support for privacy assertions."""

    provider = "fake"
    model = "wealthpilot-offline-research-v1"

    def __init__(self) -> None:
        self.captured_payloads: list[dict[str, object]] = []

    def _generate(self, request: ModelRequest) -> ModelResponse:
        payload = request.as_payload()
        # Capture only after the privacy gate has accepted the request.
        self.captured_payloads.append(deepcopy(payload))
        facts = request.public_research
        company = str(facts.get("company_name", request.symbol))
        positives = list(facts.get("positives", []))
        risks = list(facts.get("risks", []))
        summary = (
            f"{company}（{request.symbol}）离线研究摘要："
            f"当前缓存资料显示 {len(positives)} 项积极因素与 {len(risks)} 项主要风险。"
            "本段为研究叙述，不构成投资建议。"
        )
        return ModelResponse(
            structured_output={
                "research_summary": summary,
                "interpretation": "请将公开研究证据与个人风险承受能力一并评估。",
            },
            provider=self.provider,
            model=self.model,
            cached=True,
        )
