from __future__ import annotations

import json

import pytest

from wealthpilot.contexts.research import (
    EquityDataProvider,
    EquityDataProviderError,
    EquityResearchData,
    EquityResearchWorkflow,
    ResearchMemoValidationError,
)
from wealthpilot.platform.model_gateway import FakeModelGateway, ModelGateway, ModelOutputError, ModelResponse


def dataset(*, missing: bool = False) -> EquityResearchData:
    fetched = "2026-09-06T01:00:00Z"
    evidence = [
        {
            "evidence_id": "fake:security:600519",
            "source": "FakePublicProvider.security",
            "as_of": "2026-09-05",
            "available_at": "2026-09-05",
            "fetched_at": fetched,
            "quality": "TEST_FIXTURE",
        }
    ]
    return EquityResearchData(
        symbol="600519",
        company_name="贵州茅台",
        exchange="SSE",
        as_of="2026-09-05",
        fetched_at=fetched,
        security_info={"code": "sh.600519", "code_name": "贵州茅台", "source_reference": "fake:security:600519"},
        recent_market_data=[] if missing else [{"date": "2026-09-05", "close": "1500", "source_reference": "fake:security:600519"}],
        fundamental_metrics={} if missing else {"roeAvg": {"value": "0.25", "as_of": "2026-Q2", "source_reference": "fake:security:600519"}},
        valuation_metrics={} if missing else {"peTTM": {"value": "22", "as_of": "2026-09-05", "source_reference": "fake:security:600519"}},
        evidence=evidence,
        limitations=["缺少近期财务和行情数据。"] if missing else ["公开历史数据可能延迟。"],
        provider="FakePublicProvider",
    )


class FakeProvider(EquityDataProvider):
    def __init__(self, value: EquityResearchData) -> None:
        self.value = value

    def fetch(self, symbol: str, *, as_of: str | None = None) -> EquityResearchData:
        return self.value


class FailingProvider(EquityDataProvider):
    def fetch(self, symbol: str, *, as_of: str | None = None) -> EquityResearchData:
        raise EquityDataProviderError("public provider unavailable")


class InvalidStructuredGateway(ModelGateway):
    def _generate(self, request):  # type: ignore[no-untyped-def]
        return ModelResponse({"research_summary": "uncited"}, "fake", "invalid", False)


class UnknownCitationGateway(ModelGateway):
    def _generate(self, request):  # type: ignore[no-untyped-def]
        return ModelResponse(
            {
                "research_summary": "摘要",
                "key_positives": [{"claim": "无法追溯", "evidence_ids": ["invented:evidence"]}],
                "key_risks": [],
            },
            "fake",
            "bad-citation",
            False,
        )


def test_real_data_workflow_returns_plain_persistable_cited_memo() -> None:
    gateway = FakeModelGateway()
    result = EquityResearchWorkflow(FakeProvider(dataset()), gateway).analyze(
        "600519", "请基于公开信息研究"
    )
    assert result["symbol"] == "600519"
    assert result["data_provider"] == "FakePublicProvider"
    assert result["valuation_metrics"]["peTTM"]["value"] == "22"
    assert result["research_risk_level"] == "LOW"
    assert result["key_positives"][0]["evidence_ids"] == ["fake:security:600519"]
    assert result["no_live_side_effect"] is True
    json.dumps(result, ensure_ascii=False)
    projection = gateway.captured_payloads[0]["public_research"]
    assert "recent_market_data" not in projection
    assert projection["latest_market_observation"] == {
        "date": "2026-09-05",
        "close": "1500",
        "source_reference": "fake:security:600519",
    }


def test_missing_provider_data_stays_missing_and_is_disclosed() -> None:
    result = EquityResearchWorkflow(FakeProvider(dataset(missing=True)), FakeModelGateway()).analyze(
        "600519", "研究"
    )
    assert result["recent_market_data"] == []
    assert result["fundamental_metrics"] == {}
    assert result["valuation_metrics"] == {}
    assert result["research_risk_level"] == "HIGH"
    assert "NO_RECENT_MARKET_DATA" in result["research_risk_signals"]
    assert "缺少近期财务和行情数据。" in result["limitations"]


def test_provider_failure_is_explicit() -> None:
    with pytest.raises(EquityDataProviderError, match="public provider unavailable"):
        EquityResearchWorkflow(FailingProvider(), FakeModelGateway()).analyze("600519", "研究")


def test_invalid_structured_output_is_rejected() -> None:
    with pytest.raises(ModelOutputError):
        EquityResearchWorkflow(FakeProvider(dataset()), InvalidStructuredGateway()).analyze("600519", "研究")


def test_unknown_model_evidence_is_rejected() -> None:
    with pytest.raises(ResearchMemoValidationError):
        EquityResearchWorkflow(FakeProvider(dataset()), UnknownCitationGateway()).analyze("600519", "研究")
