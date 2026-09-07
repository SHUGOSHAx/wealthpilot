"""Deterministic personal suitability for the demonstration vertical slice."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Mapping


_REQUIRED = (
    "total_assets",
    "total_liabilities",
    "net_worth",
    "liquid_assets",
    "monthly_income",
    "monthly_expenses",
    "investable_capital",
    "existing_equity_exposure",
)
_RISK_BUDGET = {"LOW": Decimal("0.75"), "MEDIUM": Decimal("0.50"), "HIGH": Decimal("0.25")}


@dataclass(frozen=True, slots=True)
class RiskResult:
    suitability: str
    warning: str
    recommended_percent: str | None
    recommended_amount: str | None
    currency: str
    formula_limits: dict[str, str]
    missing_inputs: tuple[str, ...]
    no_live_side_effect: bool = True

    def as_dict(self) -> dict[str, Any]:
        allocation = None
        if self.recommended_amount is not None:
            allocation = {
                "percent": self.recommended_percent,
                "amount": self.recommended_amount,
                "currency": self.currency,
            }
        return {
            "personal_suitability": self.suitability,
            "risk_warning": self.warning,
            "recommended_max_allocation": allocation,
            "calculation": {
                "method": "DETERMINISTIC_MIN_LIMITS_V1",
                "limits": self.formula_limits,
                "missing_inputs": list(self.missing_inputs),
            },
            "no_live_side_effect": self.no_live_side_effect,
        }


class RiskSuitabilityEngine:
    """Calculate authoritative limits without model involvement.

    MVP formula:
      min(investable capital, reserve headroom, single-security limit,
          risk-budget limit), less the existing position in this symbol.
    """

    reserve_months = Decimal("6")
    single_security_limit = Decimal("0.10")
    equity_limit = Decimal("0.60")

    def assess(self, snapshot: Any, *, research_risk_level: str) -> dict[str, Any]:
        metrics, currency = extract_financial_metrics(snapshot)
        missing = tuple(name for name in _REQUIRED if name not in metrics)
        risk_level = research_risk_level.upper()
        if risk_level not in _RISK_BUDGET:
            missing += ("research_risk_level",)
        if missing:
            return RiskResult(
                suitability="INSUFFICIENT_DATA",
                warning="缺少必要的确定性财务输入，无法给出具体仓位。",
                recommended_percent=None,
                recommended_amount=None,
                currency=currency,
                formula_limits={},
                missing_inputs=missing,
            ).as_dict()

        net_worth = metrics["net_worth"]
        cash_flow = metrics["monthly_income"] - metrics["monthly_expenses"]
        reserve_required = metrics["monthly_expenses"] * self.reserve_months
        reserve_headroom = max(metrics["liquid_assets"] - reserve_required, Decimal("0"))
        existing_position = max(metrics.get("existing_position_value", Decimal("0")), Decimal("0"))
        limits = {
            "investable_capital": max(metrics["investable_capital"], Decimal("0")),
            "cash_reserve_headroom": reserve_headroom,
            "single_security_limit": max(net_worth * self.single_security_limit, Decimal("0")),
            "risk_budget_limit": max(metrics["investable_capital"] * _RISK_BUDGET[risk_level], Decimal("0")),
            "equity_headroom": max(
                net_worth * self.equity_limit - metrics["existing_equity_exposure"],
                Decimal("0"),
            ),
        }

        if net_worth <= 0:
            suitability, warning, maximum = "UNSUITABLE", "净资产非正，不建议建立证券仓位。", Decimal("0")
        elif cash_flow <= 0:
            suitability, warning, maximum = "UNSUITABLE", "月度现金流不足，应先恢复收支安全边际。", Decimal("0")
        elif reserve_headroom <= 0:
            suitability, warning, maximum = "UNSUITABLE", "流动资产未覆盖六个月应急储备，不建议建立仓位。", Decimal("0")
        elif limits["equity_headroom"] <= 0:
            suitability, warning, maximum = "CAUTION", "现有权益暴露已达到个人使用版上限，不建议增加仓位。", Decimal("0")
        else:
            maximum = max(min(limits.values()) - existing_position, Decimal("0"))
            suitability = "CAUTION" if risk_level == "HIGH" else "SUITABLE"
            warning = (
                "标的风险较高；即使适配也不得超过确定性上限。"
                if risk_level == "HIGH"
                else "研究存在不确定性；仓位不得超过确定性上限。"
            )

        amount = _canonical_money(maximum)
        percent = _canonical_percent(maximum / net_worth * Decimal("100")) if net_worth > 0 else "0"
        return RiskResult(
            suitability=suitability,
            warning=warning,
            recommended_percent=percent,
            recommended_amount=amount,
            currency=currency,
            formula_limits={key: _canonical_money(value) for key, value in limits.items()},
            missing_inputs=(),
        ).as_dict()


def extract_financial_metrics(snapshot: Any) -> tuple[dict[str, Decimal], str]:
    """Read only anonymous aggregate values from mapping/Pydantic snapshots."""

    data = _mapping(snapshot)
    sources: list[Mapping[str, Any]] = [data]
    for key in ("mvp_metrics", "financial_profile", "cash_flow_summary", "cash_flow"):
        nested = data.get(key)
        if isinstance(nested, Mapping):
            sources.append(nested)
    aliases = {
        "total_assets": ("total_assets", "assets_total", "assets"),
        "total_liabilities": ("total_liabilities", "liabilities_total", "liabilities"),
        "net_worth": ("net_worth",),
        "liquid_assets": ("liquid_assets", "cash_and_equivalents"),
        "monthly_income": ("monthly_income", "total_inflows", "inflow"),
        "monthly_expenses": ("monthly_expenses", "total_outflows", "outflow"),
        "investable_capital": ("investable_capital",),
        "existing_position_value": ("existing_position_value",),
        "existing_equity_exposure": ("existing_equity_exposure", "equity_exposure"),
    }
    metrics: dict[str, Decimal] = {}
    for canonical, names in aliases.items():
        for source in sources:
            for name in names:
                if name in source:
                    parsed = _decimal(source[name])
                    if parsed is not None:
                        metrics[canonical] = parsed
                        break
            if canonical in metrics:
                break
    currency = str(data.get("base_currency") or data.get("currency") or "CNY")
    return metrics, currency


def public_aggregate_metrics(snapshot: Any) -> dict[str, str]:
    """Return the allowlisted P1 projection permitted to cross the gateway."""

    metrics, _ = extract_financial_metrics(snapshot)
    return {key: _canonical_money(value) for key, value in metrics.items() if key in _REQUIRED}


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        if isinstance(dumped, Mapping):
            return dumped
    raise TypeError("snapshot must be a mapping or Pydantic model")


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, Mapping):
        value = value.get("amount")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _canonical_money(value: Decimal) -> str:
    value = value.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    text = format(value, "f").rstrip("0").rstrip(".")
    return text or "0"


def _canonical_percent(value: Decimal) -> str:
    value = value.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    text = format(value, "f").rstrip("0").rstrip(".")
    return text or "0"
