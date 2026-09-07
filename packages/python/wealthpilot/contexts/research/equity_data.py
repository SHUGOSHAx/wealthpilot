"""Port and immutable values for credential-free public A-share data."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class EquityDataProviderError(RuntimeError):
    """Safe provider failure containing no credentials or private user data."""


@dataclass(frozen=True, slots=True)
class EquityResearchData:
    symbol: str
    company_name: str
    exchange: str
    as_of: str
    fetched_at: str
    security_info: dict[str, Any]
    recent_market_data: list[dict[str, Any]]
    fundamental_metrics: dict[str, Any]
    valuation_metrics: dict[str, Any]
    evidence: list[dict[str, Any]]
    limitations: list[str]
    provider: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "exchange": self.exchange,
            "as_of": self.as_of,
            "fetched_at": self.fetched_at,
            "security_info": self.security_info,
            "recent_market_data": self.recent_market_data,
            "fundamental_metrics": self.fundamental_metrics,
            "valuation_metrics": self.valuation_metrics,
            "evidence": self.evidence,
            "limitations": self.limitations,
            "provider": self.provider,
        }


class EquityDataProvider(ABC):
    @abstractmethod
    def fetch(self, symbol: str, *, as_of: str | None = None) -> EquityResearchData:
        """Fetch public evidence available no later than ``as_of``."""
