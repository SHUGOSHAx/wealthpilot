"""Stable MVP research entry point."""

from __future__ import annotations

import re
from typing import Any

from wealthpilot.contexts.portfolio_risk.engine import (
    RiskSuitabilityEngine,
    public_aggregate_metrics,
)
from wealthpilot.platform.model_gateway import FakeModelGateway, ModelGateway, ModelRequest

from .catalog import get_cached_research


class ResearchService:
    """Combine public research narrative with deterministic personal risk."""

    def __init__(
        self,
        model_gateway: ModelGateway | None = None,
        risk_engine: RiskSuitabilityEngine | None = None,
    ) -> None:
        self.model_gateway = model_gateway or FakeModelGateway()
        self.risk_engine = risk_engine or RiskSuitabilityEngine()

    def analyze(self, symbol: str, question: str, snapshot: Any) -> dict[str, Any]:
        normalized = _normalize_symbol(symbol)
        research = get_cached_research(normalized)
        if research is None:
            return {
                "symbol": normalized,
                "research_summary": "当前离线演示资料库不包含该标的。",
                "key_positives": [],
                "key_risks": ["缺少可核验的缓存研究资料"],
                "evidence": [],
                "data_summary": "UNAVAILABLE",
                "personal_suitability": "INSUFFICIENT_DATA",
                "risk_warning": "缺少标的研究输入，无法生成适配性或具体仓位。",
                "recommended_max_allocation": None,
                "model": None,
                "disclaimer": "离线演示资料不可用，不构成投资建议。",
                "no_live_side_effect": True,
            }

        request = ModelRequest(
            symbol=normalized,
            question=question,
            public_research=research,
            financial_metrics=public_aggregate_metrics(snapshot),
            privacy_level="P1",
        )
        model_response = self.model_gateway.generate_structured(request)
        risk = self.risk_engine.assess(snapshot, research_risk_level=str(research["risk_level"]))
        return {
            "symbol": normalized,
            "company_name": research["company_name"],
            "as_of": research["as_of"],
            "research_summary": model_response.structured_output["research_summary"],
            "key_positives": research["positives"],
            "key_risks": research["risks"],
            "evidence": research["evidence"],
            "data_summary": research["data_status"],
            **risk,
            "model": {
                "provider": model_response.provider,
                "model": model_response.model,
                "cached": model_response.cached,
                "authority": "NARRATIVE_ONLY",
            },
            "disclaimer": research["disclaimer"],
            "no_live_side_effect": True,
        }


def _normalize_symbol(value: str) -> str:
    match = re.search(r"(?<!\d)(\d{6})(?!\d)", value.strip())
    return match.group(1) if match else value.strip().upper()
