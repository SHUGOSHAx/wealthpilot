from __future__ import annotations

from wealthpilot.contexts.portfolio_risk import RiskSuitabilityEngine


def snapshot(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "base_currency": "CNY",
        "total_assets": {"amount": "100000", "currency": "CNY"},
        "total_liabilities": {"amount": "20000", "currency": "CNY"},
        "net_worth": {"amount": "80000", "currency": "CNY"},
        "liquid_assets": {"amount": "60000", "currency": "CNY"},
        "monthly_income": {"amount": "15000", "currency": "CNY"},
        "monthly_expenses": {"amount": "5000", "currency": "CNY"},
        "investable_capital": {"amount": "30000", "currency": "CNY"},
    }
    base.update(changes)
    return base


def test_normal_allocation_uses_minimum_deterministic_limit() -> None:
    result = RiskSuitabilityEngine().assess(snapshot(), research_risk_level="MEDIUM")
    assert result["personal_suitability"] == "SUITABLE"
    assert result["recommended_max_allocation"] == {"amount": "8000", "percent": "10", "currency": "CNY"}
    assert result["calculation"]["limits"] == {
        "investable_capital": "30000",
        "cash_reserve_headroom": "30000",
        "single_security_limit": "8000",
        "risk_budget_limit": "15000",
    }


def test_negative_net_worth_blocks_position() -> None:
    result = RiskSuitabilityEngine().assess(
        snapshot(net_worth={"amount": "-1", "currency": "CNY"}), research_risk_level="LOW"
    )
    assert result["personal_suitability"] == "UNSUITABLE"
    assert result["recommended_max_allocation"]["amount"] == "0"


def test_non_positive_cash_flow_blocks_position() -> None:
    result = RiskSuitabilityEngine().assess(
        snapshot(monthly_income={"amount": "4000", "currency": "CNY"}), research_risk_level="LOW"
    )
    assert result["personal_suitability"] == "UNSUITABLE"
    assert result["recommended_max_allocation"]["amount"] == "0"


def test_reserve_shortfall_blocks_position() -> None:
    result = RiskSuitabilityEngine().assess(
        snapshot(liquid_assets={"amount": "10000", "currency": "CNY"}), research_risk_level="LOW"
    )
    assert result["personal_suitability"] == "UNSUITABLE"
    assert result["recommended_max_allocation"]["amount"] == "0"


def test_missing_required_input_produces_no_specific_position() -> None:
    value = snapshot()
    value.pop("investable_capital")
    result = RiskSuitabilityEngine().assess(value, research_risk_level="MEDIUM")
    assert result["personal_suitability"] == "INSUFFICIENT_DATA"
    assert result["recommended_max_allocation"] is None
    assert result["calculation"]["missing_inputs"] == ["investable_capital"]
