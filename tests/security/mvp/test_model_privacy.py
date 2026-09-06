from __future__ import annotations

import pytest

from wealthpilot.platform.model_gateway import FakeModelGateway, ModelRequest
from wealthpilot.platform.privacy import PrivacyBoundaryError


def safe_request(**changes: object) -> ModelRequest:
    values: dict[str, object] = {
        "symbol": "600519",
        "question": "这只股票是否适合当前财务情况？",
        "public_research": {"company_name": "贵州茅台", "positives": [], "risks": []},
        "financial_metrics": {"net_worth": "80000", "monthly_expenses": "5000"},
        "privacy_level": "P1",
    }
    values.update(changes)
    return ModelRequest(**values)  # type: ignore[arg-type]


def test_gateway_captures_only_safe_aggregate_payload() -> None:
    gateway = FakeModelGateway()
    gateway.generate_structured(safe_request())
    assert gateway.captured_payloads[0]["financial_metrics"] == {
        "net_worth": "80000",
        "monthly_expenses": "5000",
    }


@pytest.mark.parametrize(
    "mutation",
    [
        {"transactions": [{"description": "raw merchant"}]},
        {"account_number": "6222021234567890"},
        {"password": "super-secret"},
        {"safe_note": "token=secret-value-123"},
    ],
)
def test_p2_p3_mutations_fail_closed(mutation: dict[str, object]) -> None:
    gateway = FakeModelGateway()
    request = safe_request(public_research={"company_name": "贵州茅台", **mutation})
    with pytest.raises(PrivacyBoundaryError):
        gateway.generate_structured(request)
    assert gateway.captured_payloads == []


def test_explicit_p3_classification_is_rejected() -> None:
    with pytest.raises(PrivacyBoundaryError):
        FakeModelGateway().generate_structured(safe_request(privacy_level="P3"))
