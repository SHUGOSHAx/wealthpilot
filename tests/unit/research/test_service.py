from __future__ import annotations

from wealthpilot.contexts.research import ResearchService
from wealthpilot.platform.model_gateway import FakeModelGateway, ModelResponse


def complete_snapshot() -> dict[str, object]:
    return {
        "base_currency": "CNY",
        "total_assets": {"amount": "100000", "currency": "CNY"},
        "total_liabilities": {"amount": "20000", "currency": "CNY"},
        "net_worth": {"amount": "80000", "currency": "CNY"},
        "liquid_assets": {"amount": "60000", "currency": "CNY"},
        "monthly_income": {"amount": "15000", "currency": "CNY"},
        "monthly_expenses": {"amount": "5000", "currency": "CNY"},
        "investable_capital": {"amount": "30000", "currency": "CNY"},
        "transactions": [{"description": "PRIVATE RAW MERCHANT", "amount": "1"}],
        "account_balances": [{"account_id": "LOCAL-PRIVATE-ID"}],
    }


def test_supported_symbol_returns_complete_offline_memo() -> None:
    gateway = FakeModelGateway()
    result = ResearchService(gateway).analyze(
        "600519 贵州茅台", "结合我的财务状况，这只股票是否适合我？", complete_snapshot()
    )
    assert result["symbol"] == "600519"
    assert result["company_name"] == "贵州茅台"
    assert result["research_summary"]
    assert result["key_positives"] and result["key_risks"] and result["evidence"]
    assert result["personal_suitability"] == "SUITABLE"
    assert result["recommended_max_allocation"]["amount"] == "8000"
    assert result["model"]["authority"] == "NARRATIVE_ONLY"
    assert result["data_summary"] == "DEMO_CACHED_NOT_REAL_TIME"
    assert result["no_live_side_effect"] is True

    captured = gateway.captured_payloads[0]
    rendered = repr(captured)
    assert "transactions" not in captured
    assert "account_balances" not in captured
    assert "PRIVATE RAW MERCHANT" not in rendered
    assert "LOCAL-PRIVATE-ID" not in rendered


def test_unknown_symbol_does_not_call_model_or_create_allocation() -> None:
    gateway = FakeModelGateway()
    result = ResearchService(gateway).analyze("000001", "是否适合？", complete_snapshot())
    assert result["data_summary"] == "UNAVAILABLE"
    assert result["recommended_max_allocation"] is None
    assert gateway.captured_payloads == []


class AdversarialNarrativeGateway:
    def generate_structured(self, request):  # type: ignore[no-untyped-def]
        return ModelResponse(
            structured_output={
                "research_summary": "模型试图影响仓位，但该字段不会被业务服务读取。",
                "recommended_max_allocation": {"amount": "999999999", "percent": "100"},
                "personal_suitability": "GUARANTEED_PROFIT",
            },
            provider="adversarial-fake",
            model="test-only",
            cached=True,
        )


def test_model_cannot_override_authoritative_suitability_or_allocation() -> None:
    result = ResearchService(AdversarialNarrativeGateway()).analyze(
        "600519", "是否适合？", complete_snapshot()
    )
    assert result["personal_suitability"] == "SUITABLE"
    assert result["recommended_max_allocation"] == {
        "amount": "8000",
        "percent": "10",
        "currency": "CNY",
    }
