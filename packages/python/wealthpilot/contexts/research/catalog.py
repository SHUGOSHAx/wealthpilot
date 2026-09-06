"""Synthetic/cached public research records for the offline MVP."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_CATALOG: dict[str, dict[str, Any]] = {
    "600519": {
        "symbol": "600519",
        "company_name": "贵州茅台",
        "exchange": "SSE",
        "as_of": "2026-08-31",
        "data_status": "DEMO_CACHED_NOT_REAL_TIME",
        "risk_level": "MEDIUM",
        "positives": [
            "品牌认知度与高端白酒市场地位较强",
            "历史经营现金流与盈利能力具有韧性",
            "渠道与产品结构为长期经营提供支撑",
        ],
        "risks": [
            "消费需求和渠道库存变化可能影响增长",
            "估值水平可能放大市场波动",
            "行业政策、税制与消费偏好变化存在不确定性",
        ],
        "evidence": [
            {"label": "公司定期报告摘要（演示缓存）", "as_of": "2026-06-30", "value": "经营与现金流趋势摘要"},
            {"label": "公开行业资料摘要（演示缓存）", "as_of": "2026-08-31", "value": "高端白酒竞争与需求风险"},
        ],
        "disclaimer": "演示缓存数据，非实时行情或完整投研资料，不构成投资建议。",
    }
}


def get_cached_research(symbol: str) -> dict[str, Any] | None:
    record = _CATALOG.get(symbol)
    return deepcopy(record) if record else None
