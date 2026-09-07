"""Local-only WealthPilot personal-use API and Web composition root."""

from __future__ import annotations

import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from wealthpilot.adapters.persistence import (
    SQLiteResearchStore,
    SQLiteWealthService,
    backup_database,
    database_digest,
    default_database_path,
    restore_database,
)
from wealthpilot.contexts.portfolio_risk import RiskSuitabilityEngine
from wealthpilot.contexts.research import EquityDataProviderError, EquityResearchWorkflow, ResearchService
from wealthpilot.contexts.wealth.application.service import WealthCsvValidationError, build_financial_snapshot
from wealthpilot.platform.model_gateway import ModelOutputError, ModelProviderError
from wealthpilot.platform.privacy import PrivacyBoundaryError

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = REPOSITORY_ROOT / "apps" / "web"
DEMO_CSV = REPOSITORY_ROOT / "tests" / "fixtures" / "demo" / "personal_finance.csv"
MAX_UPLOAD_BYTES = 1_048_576
MAX_BACKUP_BYTES = 256 * 1_048_576
DATA_LOCK = threading.RLock()


class Flags(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transfer: bool | None = None
    internal_transfer: bool | None = None
    refund: bool | None = None
    reimbursement: bool | None = None
    exclude_from_cash_flow: bool | None = None


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str | None = Field(default=None, max_length=80)
    merchant: str | None = Field(default=None, max_length=256)
    merchant_normalized: str | None = Field(default=None, max_length=256)
    flags: Flags | None = None


class ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = True


class PersonalResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=6, max_length=12)
    question: str = Field(min_length=1, max_length=500)
    as_of: str | None = None


class DemoResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1, max_length=32)
    question: str = Field(min_length=1, max_length=500)
    snapshot: dict[str, Any]


app = FastAPI(
    title="WealthPilot Personal-Use MVP",
    version="0.2.0-personal",
    description="Local-first personal finance and research. No live trading side effects.",
    docs_url="/api/docs",
    redoc_url=None,
)
demo_research_service = ResearchService()


def _database_path() -> Path:
    configured = os.getenv("WEALTHPILOT_DATABASE_PATH")
    return Path(configured).expanduser().resolve() if configured else default_database_path()


def _correction_values(request: CorrectionRequest) -> dict[str, Any]:
    flags = request.flags or Flags()
    merchant = request.merchant_normalized if request.merchant_normalized is not None else request.merchant
    return {
        "category": request.category,
        "merchant_normalized": merchant,
        "is_transfer": flags.transfer if flags.transfer is not None else flags.internal_transfer,
        "is_refund": flags.refund,
        "is_reimbursement": flags.reimbursement if flags.reimbursement is not None else flags.exclude_from_cash_flow,
    }


def _safe_error(error: Exception) -> HTTPException:
    if isinstance(error, KeyError):
        return HTTPException(status_code=404, detail="Requested local record was not found")
    if isinstance(error, (ValueError, TypeError)):
        return HTTPException(status_code=422, detail=str(error))
    return HTTPException(status_code=500, detail="Local data operation failed safely")


@app.get("/api/v1/personal/settings")
def personal_settings() -> dict[str, Any]:
    path = _database_path()
    configured_model = all(os.getenv(name) for name in (
        "WEALTHPILOT_MODEL_BASE_URL", "WEALTHPILOT_MODEL_NAME", "WEALTHPILOT_MODEL_API_KEY"
    ))
    return {"settings": {
        "mode": "PERSONAL_LOCAL", "bind": "127.0.0.1", "live_trading": False,
        "no_live_side_effect": True,
        "model": {
            "provider": "openai-compatible" if configured_model else "offline-fake",
            "model": os.getenv("WEALTHPILOT_MODEL_NAME", "deterministic-offline"),
            "status": "READY" if configured_model else "OFFLINE_FALLBACK",
        },
        "equity_data": {"provider": "BaoStock", "real_data": True, "real_time": False},
        "data": {"description": "SQLite local-first storage; secrets are not stored in the database.",
                 "database_exists": path.is_file(), "schema_version": 2},
    }}


@app.get("/api/v1/personal/overview")
def personal_overview() -> dict[str, Any]:
    with SQLiteWealthService(_database_path()) as service:
        snapshot = service.latest_financial_snapshot()
        transactions = service.list_transactions()[:5]
    return {"has_data": snapshot is not None, "snapshot": snapshot or {}, "recent_transactions": transactions}


@app.get("/api/v1/personal/transactions")
def personal_transactions() -> dict[str, Any]:
    with SQLiteWealthService(_database_path()) as service:
        return {"transactions": service.list_transactions()}


@app.post("/api/v1/personal/imports/preview")
async def personal_import_preview(file: UploadFile = File(...)) -> dict[str, Any]:
    filename = file.filename or "import.csv"
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Only CSV import is currently supported")
    body = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV exceeds the 1 MiB personal-use limit")
    try:
        with DATA_LOCK, SQLiteWealthService(_database_path()) as service:
            preview = service.create_import_preview(body, source_kind="GENERIC_CSV", source_filename=filename)
    except WealthCsvValidationError as error:
        detail: dict[str, Any] = {"code": error.code, "message": "CSV validation failed"}
        if error.row_number is not None:
            detail["row_number"] = error.row_number
        raise HTTPException(status_code=422, detail=detail) from error
    return {"preview": preview}


@app.patch("/api/v1/personal/imports/{batch_id}/transactions/{transaction_id}")
def personal_preview_correction(batch_id: str, transaction_id: str, request: CorrectionRequest) -> dict[str, Any]:
    try:
        with DATA_LOCK, SQLiteWealthService(_database_path()) as service:
            preview = service.correct_transaction(batch_id, transaction_id, **_correction_values(request))
    except Exception as error:
        raise _safe_error(error) from error
    transaction = next(item for item in preview["transactions"] if item["transaction_id"] == transaction_id)
    return {"transaction": transaction, "preview": preview}


@app.post("/api/v1/personal/imports/{batch_id}/confirm")
def personal_confirm_import(batch_id: str, request: ConfirmationRequest) -> dict[str, Any]:
    if not request.confirmed:
        raise HTTPException(status_code=422, detail="Explicit confirmation is required")
    try:
        with DATA_LOCK, SQLiteWealthService(_database_path()) as service:
            preview = service.get_import_preview(batch_id)
            snapshot = service.confirm_import(batch_id)
            reconciliation = service.reconcile()
    except Exception as error:
        raise _safe_error(error) from error
    return {"imported_count": preview["new_transaction_count"],
            "duplicate_count": preview["duplicate_transaction_count"],
            "snapshot": snapshot, "reconciliation": reconciliation}


@app.patch("/api/v1/personal/transactions/{transaction_id}")
def personal_committed_correction(transaction_id: str, request: CorrectionRequest) -> dict[str, Any]:
    try:
        with DATA_LOCK, SQLiteWealthService(_database_path()) as service:
            current = next(item for item in service.list_transactions() if item["transaction_id"] == transaction_id)
            snapshot = service.correct_confirmed_transaction(
                current["batch_id"], transaction_id, **_correction_values(request)
            )
            updated = next(item for item in service.list_transactions() if item["transaction_id"] == transaction_id)
    except (StopIteration, KeyError) as error:
        raise HTTPException(status_code=404, detail="Transaction not found") from error
    except Exception as error:
        raise _safe_error(error) from error
    return {"transaction": updated, "snapshot": snapshot}


@app.get("/api/v1/personal/snapshots")
def personal_snapshots() -> dict[str, Any]:
    with SQLiteWealthService(_database_path()) as service:
        return {"snapshots": service.financial_snapshot_history()}


@app.post("/api/v1/personal/research")
def personal_research(request: PersonalResearchRequest) -> dict[str, Any]:
    with SQLiteWealthService(_database_path()) as service:
        snapshot = service.latest_financial_snapshot()
    if snapshot is None:
        raise HTTPException(status_code=409, detail="Confirm personal finance data before research")
    try:
        memo = EquityResearchWorkflow().analyze(request.symbol, request.question, as_of=request.as_of)
        risk = RiskSuitabilityEngine().assess(snapshot, research_risk_level=memo["research_risk_level"])
        with DATA_LOCK, SQLiteResearchStore(_database_path()) as store:
            record = store.save(query=request.question, snapshot=snapshot, memo=memo, risk=risk)
    except PrivacyBoundaryError as error:
        raise HTTPException(status_code=403, detail="Research request failed privacy checks") from error
    except EquityDataProviderError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (ModelOutputError, ModelProviderError) as error:
        raise HTTPException(status_code=502, detail="Model Gateway failed safely") from error
    return record


@app.get("/api/v1/personal/research/history")
def personal_research_history() -> dict[str, Any]:
    with SQLiteResearchStore(_database_path()) as store:
        return {"history": store.history()}


@app.post("/api/v1/personal/data/backup")
def personal_backup() -> FileResponse:
    database = _database_path()
    if not database.is_file():
        raise HTTPException(status_code=404, detail="No local database to back up")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = database.parent / "backups" / f"wealthpilot-{stamp}.wpbackup"
    with DATA_LOCK:
        backup_database(database, destination)
    return FileResponse(destination, media_type="application/octet-stream", filename=destination.name)


@app.post("/api/v1/personal/data/restore")
async def personal_restore(file: UploadFile = File(...)) -> dict[str, Any]:
    body = await file.read(MAX_BACKUP_BYTES + 1)
    await file.close()
    if len(body) > MAX_BACKUP_BYTES:
        raise HTTPException(status_code=413, detail="Backup exceeds the 256 MiB limit")
    database = _database_path()
    database.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix="restore-", suffix=".wpbackup")
    os.close(descriptor)
    incoming = Path(temporary_name)
    incoming.write_bytes(body)
    safety_backup: Path | None = None
    try:
        database_digest(incoming)
        with DATA_LOCK:
            if database.is_file():
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                safety_backup = database.parent / "backups" / f"pre-restore-{stamp}.wpbackup"
                backup_database(database, safety_backup)
            result = restore_database(incoming, database, overwrite=True)
    except Exception as error:
        raise HTTPException(status_code=422, detail="Backup validation or restore failed") from error
    finally:
        incoming.unlink(missing_ok=True)
    return {"restored": True, "verified": result["verified"], "safety_backup": safety_backup is not None}


# Compatibility/demo routes remain useful for first-run and regression tests.
@app.get("/api/v1/demo/health")
def demo_health() -> dict[str, Any]:
    return {"status": "ok", "mode": "DEMO", "model_gateway": "offline_fake",
            "live_trading": False, "no_live_side_effect": True}


@app.get("/api/v1/demo/sample-csv")
def sample_csv() -> FileResponse:
    return FileResponse(DEMO_CSV, media_type="text/csv", filename="wealthpilot-sample.csv")


@app.post("/api/v1/demo/import")
async def demo_import(file: UploadFile = File(...)) -> dict[str, Any]:
    body = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV exceeds limit")
    try:
        return {"snapshot": build_financial_snapshot(body)}
    except WealthCsvValidationError as error:
        raise HTTPException(status_code=422, detail={"code": error.code, "message": "CSV validation failed"}) from error


@app.get("/api/v1/demo/symbols")
def demo_symbols() -> dict[str, Any]:
    return {"symbols": [{"symbol": "600519", "name": "贵州茅台"}]}


@app.post("/api/v1/demo/research")
def demo_research(request: DemoResearchRequest) -> dict[str, Any]:
    try:
        return {"memo": demo_research_service.analyze(request.symbol, request.question, request.snapshot)}
    except PrivacyBoundaryError as error:
        raise HTTPException(status_code=403, detail="Research request failed privacy checks") from error
    except ModelOutputError as error:
        raise HTTPException(status_code=502, detail="Model Gateway returned invalid output") from error


@app.exception_handler(Exception)
async def unexpected_error(_request: Any, error: Exception) -> JSONResponse:
    if isinstance(error, HTTPException):
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
    return JSONResponse(status_code=500, content={"detail": "Unexpected local error"})


if WEB_ROOT.is_dir():
    app.mount("/", StaticFiles(directory=WEB_ROOT, html=True), name="web")
