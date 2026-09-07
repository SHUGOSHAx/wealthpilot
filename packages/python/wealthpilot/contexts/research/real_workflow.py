"""Real-data A-share research workflow with cited structured output."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from wealthpilot.platform.model_gateway import (
    FakeModelGateway,
    ModelGateway,
    ModelProviderError,
    ModelRequest,
    OpenAICompatibleModelGateway,
)

from .equity_data import EquityDataProvider, EquityDataProviderError, EquityResearchData


class ResearchMemoValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResearchMemo:
    schema_version: str
    symbol: str
    company_name: str
    exchange: str
    as_of: str
    fetched_at: str
    data_provider: str
    research_risk_level: str
    research_risk_signals: list[str]
    research_risk_reasons: list[str]
    research_summary: str
    key_positives: list[dict[str, Any]]
    key_risks: list[dict[str, Any]]
    security_info: dict[str, Any]
    recent_market_data: list[dict[str, Any]]
    fundamental_metrics: dict[str, Any]
    valuation_metrics: dict[str, Any]
    evidence: list[dict[str, Any]]
    limitations: list[str]
    model: dict[str, Any]
    disclaimer: str
    no_live_side_effect: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EquityResearchWorkflow:
    """Fetch public data, obtain cited narrative, and return a persistable memo."""

    def __init__(self, data_provider: EquityDataProvider | None = None, model_gateway: ModelGateway | None = None) -> None:
        if data_provider is None:
            from wealthpilot.adapters.market_data import BaoStockEquityDataProvider

            data_provider = BaoStockEquityDataProvider()
        self.data_provider = data_provider
        if model_gateway is None:
            try:
                model_gateway = OpenAICompatibleModelGateway()
            except ModelProviderError:
                model_gateway = FakeModelGateway()
        self.model_gateway = model_gateway

    def analyze(self, symbol: str, question: str, *, as_of: str | None = None) -> dict[str, Any]:
        data = self.data_provider.fetch(symbol, as_of=as_of)
        public_data = _model_projection(data)
        response = self.model_gateway.generate_structured(
            ModelRequest(
                symbol=data.symbol,
                question=question,
                public_research=public_data,
                financial_metrics={},
                # The question may contain user-authored context. The gateway
                # must apply its P1/P2/P3 guard even though only public market
                # facts (never the FinancialSnapshot) are projected here.
                privacy_level="P1",
                task_type="A_SHARE_RESEARCH_MEMO",
                response_contract="EQUITY_RESEARCH_MEMO_V1",
            )
        )
        narrative = response.structured_output
        _validate_citations(narrative, {item["evidence_id"] for item in data.evidence})
        risk_level, risk_signals, risk_reasons = determine_research_risk(data)
        limitations = list(data.limitations)
        if response.provider == "fake":
            limitations.append("未配置生产模型网关，研究叙述由离线 deterministic fake 生成。")
        return ResearchMemo(
            schema_version="0.1.0-mvp",
            symbol=data.symbol,
            company_name=data.company_name,
            exchange=data.exchange,
            as_of=data.as_of,
            fetched_at=data.fetched_at,
            data_provider=data.provider,
            research_risk_level=risk_level,
            research_risk_signals=risk_signals,
            research_risk_reasons=risk_reasons,
            research_summary=narrative["research_summary"],
            key_positives=narrative["key_positives"],
            key_risks=narrative["key_risks"],
            security_info=data.security_info,
            recent_market_data=data.recent_market_data,
            fundamental_metrics=data.fundamental_metrics,
            valuation_metrics=data.valuation_metrics,
            evidence=data.evidence,
            limitations=limitations,
            model={"provider": response.provider, "model": response.model, "cached": response.cached, "authority": "NARRATIVE_ONLY"},
            disclaimer="公开数据研究，仅供个人演示与决策支持，不构成投资建议。",
        ).to_dict()


def _validate_citations(output: dict[str, Any], available: set[str]) -> None:
    for field in ("key_positives", "key_risks"):
        for item in output[field]:
            unknown = set(item["evidence_ids"]) - available
            if unknown:
                raise ResearchMemoValidationError(f"model cited unavailable evidence in {field}")


def _model_projection(data: EquityResearchData) -> dict[str, Any]:
    """Minimize public provider data before the model call.

    Full price history remains in the persisted memo; the model receives only
    the latest selected public fields and already-labelled provider metrics.
    """

    latest = data.recent_market_data[-1] if data.recent_market_data else {}
    safe_market_keys = ("date", "close", "turn", "tradestatus", "pctChg", "isST", "source_reference")
    return {
        "symbol": data.symbol,
        "company_name": data.company_name,
        "exchange": data.exchange,
        "as_of": data.as_of,
        "latest_market_observation": {key: latest[key] for key in safe_market_keys if latest.get(key) not in (None, "")},
        "fundamental_metrics": data.fundamental_metrics,
        "valuation_metrics": data.valuation_metrics,
        "evidence": data.evidence,
        "limitations": data.limitations,
    }


def determine_research_risk(data: EquityResearchData) -> tuple[str, list[str], list[str]]:
    """Classify research risk from provider facts only, never model output."""

    signals: list[str] = []
    reasons: list[str] = []
    latest = data.recent_market_data[-1] if data.recent_market_data else None
    company_upper = data.company_name.upper()
    if latest is None:
        signals.append("NO_RECENT_MARKET_DATA")
        reasons.append("未取得近期市场数据。")
    else:
        if str(latest.get("tradestatus", "1")) != "1":
            signals.append("TRADING_SUSPENDED")
            reasons.append("最新公开交易状态不是正常交易。")
        if str(latest.get("isST", "0")) == "1" or "ST" in company_upper:
            signals.append("SPECIAL_TREATMENT")
            reasons.append("标的被公开数据标记为 ST/特别处理。")
        changes = [_decimal(row.get("pctChg")) for row in data.recent_market_data]
        if any(value is not None and abs(value) >= Decimal("7") for value in changes):
            signals.append("ELEVATED_DAILY_MOVE")
            reasons.append("近期存在绝对值不低于 7% 的单日涨跌幅。")
    pe = _metric_decimal(data.valuation_metrics.get("peTTM"))
    if pe is not None and pe >= Decimal("35"):
        signals.append("ELEVATED_PE_TTM")
        reasons.append("公开数据中的滚动市盈率不低于 35。")

    hard = {"NO_RECENT_MARKET_DATA", "TRADING_SUSPENDED", "SPECIAL_TREATMENT"}
    if hard.intersection(signals):
        return "HIGH", signals, reasons
    if not data.fundamental_metrics:
        signals.append("FUNDAMENTALS_MISSING")
        reasons.append("近期盈利指标缺失。")
    if not data.valuation_metrics:
        signals.append("VALUATION_MISSING")
        reasons.append("近期估值指标缺失。")
    if signals:
        return "MEDIUM", signals, reasons
    return "LOW", ["NO_ELEVATED_PUBLIC_DATA_SIGNAL"], ["公开数据完整且未触发 MVP 升级规则。"]


def _metric_decimal(metric: Any) -> Decimal | None:
    return _decimal(metric.get("value")) if isinstance(metric, dict) else _decimal(metric)


def _decimal(value: Any) -> Decimal | None:
    try:
        if value in (None, ""):
            return None
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


__all__ = [
    "EquityResearchWorkflow",
    "EquityDataProviderError",
    "ResearchMemo",
    "ResearchMemoValidationError",
    "determine_research_risk",
]
