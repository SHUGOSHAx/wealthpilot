from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import app


ROOT = Path(__file__).resolve().parents[2]
DEMO_CSV = ROOT / "tests" / "fixtures" / "demo" / "personal_finance.csv"
client = TestClient(app, raise_server_exceptions=False)


def _snapshot() -> dict:
    response = client.post(
        "/api/v1/demo/import",
        files={"file": ("demo.csv", DEMO_CSV.read_bytes(), "text/csv")},
    )
    assert response.status_code == 200
    return response.json()["snapshot"]


def test_health_is_explicitly_demo_and_no_live_side_effect() -> None:
    response = client.get("/api/v1/demo/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "mode": "DEMO",
        "model_gateway": "offline_fake",
        "live_trading": False,
        "no_live_side_effect": True,
    }


def test_sample_import_produces_exact_financial_snapshot() -> None:
    response = client.get("/api/v1/demo/sample-csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")

    snapshot = _snapshot()
    assert snapshot["assets"] == {"amount": "2000000.00", "currency": "CNY"}
    assert snapshot["liabilities"] == {"amount": "955000.00", "currency": "CNY"}
    assert snapshot["net_worth"] == {"amount": "1045000.00", "currency": "CNY"}
    assert snapshot["cash_flow"]["net"] == {"amount": "16000.00", "currency": "CNY"}
    assert snapshot["emergency_fund_months"] == "14.29"


def test_research_returns_narrative_plus_deterministic_limit() -> None:
    response = client.post(
        "/api/v1/demo/research",
        json={
            "symbol": "600519",
            "question": "结合我的财务状况，这只股票是否适合我？",
            "snapshot": _snapshot(),
        },
    )
    assert response.status_code == 200
    memo = response.json()["memo"]
    assert memo["symbol"] == "600519"
    assert memo["company_name"] == "贵州茅台"
    assert memo["personal_suitability"] == "SUITABLE"
    assert memo["recommended_max_allocation"] == {
        "percent": "5.55",
        "amount": "58000",
        "currency": "CNY",
    }
    assert memo["model"]["authority"] == "NARRATIVE_ONLY"
    assert memo["no_live_side_effect"] is True


def test_research_rejects_probable_p3_without_echoing_it() -> None:
    secret = "6222000000000000"
    response = client.post(
        "/api/v1/demo/research",
        json={"symbol": "600519", "question": f"请分析账号 {secret}", "snapshot": _snapshot()},
    )
    assert response.status_code == 403
    assert secret not in response.text


def test_import_error_does_not_echo_raw_description() -> None:
    raw = "PRIVATE_DESCRIPTION_DO_NOT_ECHO"
    malformed = (
        "record_type,date,account,account_type,category,description,amount,currency,liquid\n"
        f"TRANSACTION,not-a-date,demo,ASSET,EXPENSE,{raw},1.00,CNY,true\n"
    ).encode()
    response = client.post(
        "/api/v1/demo/import",
        files={"file": ("bad.csv", malformed, "text/csv")},
    )
    assert response.status_code == 422
    assert raw not in response.text


def test_static_web_shell_is_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "WealthPilot" in response.text
    assert "NO LIVE SIDE EFFECT" in response.text
