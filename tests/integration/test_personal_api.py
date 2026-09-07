from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import apps.api.main as api


client = TestClient(api.app)
fixture = Path(__file__).parents[1] / "fixtures" / "demo" / "personal_finance.csv"


def _use_database(monkeypatch, tmp_path: Path) -> Path:
    database = tmp_path / "wealthpilot.db"
    monkeypatch.setenv("WEALTHPILOT_DATABASE_PATH", str(database))
    return database


def _confirmed_import(monkeypatch, tmp_path: Path) -> tuple[str, dict]:
    _use_database(monkeypatch, tmp_path)
    with fixture.open("rb") as handle:
        preview_response = client.post(
            "/api/v1/personal/imports/preview",
            files={"file": ("personal.csv", handle, "text/csv")},
        )
    assert preview_response.status_code == 200
    preview = preview_response.json()["preview"]
    transaction_id = preview["transactions"][0]["transaction_id"]
    correction = client.patch(
        f"/api/v1/personal/imports/{preview['batch_id']}/transactions/{transaction_id}",
        json={"category": "工资收入", "merchant": "工资"},
    )
    assert correction.status_code == 200
    confirmed = client.post(
        f"/api/v1/personal/imports/{preview['batch_id']}/confirm",
        json={"confirmed": True},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["reconciliation"]["balanced"] is True
    return transaction_id, confirmed.json()["snapshot"]


def test_personal_import_preview_correction_confirm_restart_and_duplicate(monkeypatch, tmp_path) -> None:
    _, snapshot = _confirmed_import(monkeypatch, tmp_path)
    assert snapshot["assets"]["amount"] == "2016000.00"
    assert snapshot["liabilities"]["amount"] == "955000.00"
    assert snapshot["net_worth"]["amount"] == "1061000.00"
    assert snapshot["cash_flow"]["net"]["amount"] == "16000.00"

    overview = client.get("/api/v1/personal/overview")
    assert overview.status_code == 200
    assert overview.json()["snapshot"] == snapshot
    transactions = client.get("/api/v1/personal/transactions").json()["transactions"]
    assert transactions[0]["category"]

    with fixture.open("rb") as handle:
        repeated = client.post(
            "/api/v1/personal/imports/preview",
            files={"file": ("again.csv", handle, "text/csv")},
        ).json()["preview"]
    assert repeated["status"] == "CONFIRMED"
    assert client.post(
        f"/api/v1/personal/imports/{repeated['batch_id']}/confirm",
        json={"confirmed": True},
    ).json()["snapshot"] == snapshot


def test_personal_backup_restore_is_verified_and_preserves_previous_state(monkeypatch, tmp_path) -> None:
    transaction_id, _ = _confirmed_import(monkeypatch, tmp_path)
    backup = client.post("/api/v1/personal/data/backup")
    assert backup.status_code == 200
    before = next(
        item for item in client.get("/api/v1/personal/transactions").json()["transactions"]
        if item["transaction_id"] == transaction_id
    )
    changed = client.patch(
        f"/api/v1/personal/transactions/{transaction_id}",
        json={"category": "临时修改"},
    )
    assert changed.status_code == 200
    assert changed.json()["transaction"]["category"] == "临时修改"

    restored = client.post(
        "/api/v1/personal/data/restore",
        files={"file": ("backup.wpbackup", backup.content, "application/octet-stream")},
    )
    assert restored.status_code == 200
    assert restored.json() == {"restored": True, "verified": True, "safety_backup": True}
    after = next(
        item for item in client.get("/api/v1/personal/transactions").json()["transactions"]
        if item["transaction_id"] == transaction_id
    )
    assert after["category"] == before["category"]


def test_research_is_snapshot_bound_deterministic_and_persisted(monkeypatch, tmp_path) -> None:
    _confirmed_import(monkeypatch, tmp_path)

    class FakeWorkflow:
        def analyze(self, symbol: str, question: str, *, as_of=None):
            return {
                "schema_version": "test", "symbol": symbol, "company_name": "测试公司",
                "exchange": "SSE", "as_of": "2026-09-05", "fetched_at": "2026-09-06T00:00:00Z",
                "data_provider": "TEST_PUBLIC", "research_risk_level": "MEDIUM",
                "research_risk_signals": ["TEST"], "research_risk_reasons": ["测试"],
                "research_summary": "有引用的测试摘要", "key_positives": [], "key_risks": [],
                "security_info": {}, "recent_market_data": [], "fundamental_metrics": {},
                "valuation_metrics": {}, "evidence": [], "limitations": ["TEST ONLY"],
                "model": {"provider": "fake", "model": "test", "cached": False, "authority": "NARRATIVE_ONLY"},
                "disclaimer": "测试", "no_live_side_effect": True,
            }

    monkeypatch.setattr(api, "EquityResearchWorkflow", FakeWorkflow)
    response = client.post(
        "/api/v1/personal/research",
        json={"symbol": "600519", "question": "是否适合？"},
    )
    assert response.status_code == 200
    record = response.json()
    assert record["snapshot_reference"]["as_of"] == "2026-09-04T00:00:00Z"
    assert record["memo"]["recommended_max_allocation"]["amount"] == "66000"
    assert record["memo"]["no_live_side_effect"] is True
    history = client.get("/api/v1/personal/research/history").json()["history"]
    assert history[0]["research_id"] == record["research_id"]
