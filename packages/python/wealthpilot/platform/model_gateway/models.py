"""Provider-independent model request and response values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ModelRequest:
    symbol: str
    question: str
    public_research: dict[str, Any]
    financial_metrics: dict[str, str]
    privacy_level: str = "P1"
    task_type: str = "MVP_RESEARCH_NARRATIVE"

    def as_payload(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "symbol": self.symbol,
            "question": self.question,
            "public_research": self.public_research,
            "financial_metrics": self.financial_metrics,
        }


@dataclass(frozen=True, slots=True)
class ModelResponse:
    structured_output: dict[str, Any]
    provider: str
    model: str
    cached: bool
