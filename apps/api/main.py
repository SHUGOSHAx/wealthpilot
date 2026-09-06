"""Local-only WealthPilot MVP API and Web composition root."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from wealthpilot.contexts.research import ResearchService
from wealthpilot.contexts.wealth.application.service import (
    WealthCsvValidationError,
    build_financial_snapshot,
)
from wealthpilot.platform.model_gateway import ModelOutputError
from wealthpilot.platform.privacy import PrivacyBoundaryError


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = REPOSITORY_ROOT / "apps" / "web"
DEMO_CSV = REPOSITORY_ROOT / "tests" / "fixtures" / "demo" / "personal_finance.csv"
MAX_UPLOAD_BYTES = 1_048_576


class ResearchRequest(BaseModel):
    """Private MVP request; not a frozen public Architecture contract."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=32)
    question: str = Field(min_length=1, max_length=500)
    snapshot: dict[str, Any]


app = FastAPI(
    title="WealthPilot MVP",
    version="0.1.0-mvp",
    description="Synthetic-data local demo. No live trading side effects.",
    docs_url="/api/docs",
    redoc_url=None,
)
research_service = ResearchService()


@app.get("/api/v1/demo/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "mode": os.getenv("WEALTHPILOT_MODE", "DEMO"),
        "model_gateway": "offline_fake",
        "live_trading": False,
        "no_live_side_effect": True,
    }


@app.get("/api/v1/demo/sample-csv")
def sample_csv() -> FileResponse:
    if not DEMO_CSV.is_file():
        raise HTTPException(status_code=503, detail="Synthetic demo fixture is unavailable")
    return FileResponse(DEMO_CSV, media_type="text/csv", filename="wealthpilot-demo.csv")


@app.post("/api/v1/demo/import")
async def import_finance_csv(file: UploadFile = File(...)) -> dict[str, Any]:
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=422, detail="Only synthetic CSV files are supported")
    body = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV exceeds the 1 MiB MVP limit")
    try:
        snapshot = build_financial_snapshot(body)
    except WealthCsvValidationError as error:
        detail: dict[str, Any] = {"code": error.code, "message": "CSV validation failed"}
        if error.row_number is not None:
            detail["row_number"] = error.row_number
        raise HTTPException(status_code=422, detail=detail) from error
    return {"snapshot": snapshot}


@app.get("/api/v1/demo/symbols")
def symbols() -> dict[str, Any]:
    return {
        "symbols": [
            {
                "symbol": "600519",
                "name": "贵州茅台",
                "data_status": "DEMO_CACHED_NOT_REAL_TIME",
            }
        ]
    }


@app.post("/api/v1/demo/research")
def research(request: ResearchRequest) -> dict[str, Any]:
    try:
        memo = research_service.analyze(request.symbol, request.question, request.snapshot)
    except PrivacyBoundaryError as error:
        raise HTTPException(status_code=403, detail="Research request failed privacy checks") from error
    except ModelOutputError as error:
        raise HTTPException(status_code=502, detail="Model Gateway returned invalid structured output") from error
    return {"memo": memo}


@app.exception_handler(Exception)
async def unexpected_error(_request: Any, error: Exception) -> JSONResponse:
    """Keep unexpected details and uploaded content out of HTTP responses."""

    if isinstance(error, HTTPException):
        return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
    return JSONResponse(status_code=500, content={"detail": "Unexpected local demo error"})


if WEB_ROOT.is_dir():
    app.mount("/", StaticFiles(directory=WEB_ROOT, html=True), name="web")
