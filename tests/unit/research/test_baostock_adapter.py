from __future__ import annotations

import pytest

from wealthpilot.adapters.market_data import BaoStockEquityDataProvider
from wealthpilot.contexts.research import EquityDataProviderError


class Result:
    error_code = "0"

    def __init__(self, fields: list[str], rows: list[list[str]]) -> None:
        self.fields = fields
        self.rows = rows
        self.index = -1

    def next(self) -> bool:
        self.index += 1
        return self.index < len(self.rows)

    def get_row_data(self) -> list[str]:
        return self.rows[self.index]


class FakeBaoStock:
    def __init__(self) -> None:
        self.logged_out = False

    def login(self) -> Result:
        return Result([], [])

    def logout(self) -> None:
        self.logged_out = True

    def query_stock_basic(self, *, code: str) -> Result:
        assert code == "sh.600519"
        return Result(["code", "code_name", "ipoDate", "type", "status"], [[code, "贵州茅台", "2001-08-27", "1", "1"]])

    def query_history_k_data_plus(self, code: str, fields: str, **kwargs: str) -> Result:
        selected = fields.split(",")
        values = {key: "" for key in selected}
        values.update({"date": "2026-09-05", "code": code, "close": "1500", "peTTM": "22", "pbMRQ": "8"})
        return Result(selected, [[values[key] for key in selected]])

    def query_profit_data(self, *, code: str, year: int, quarter: int) -> Result:
        return Result(["code", "pubDate", "statDate", "roeAvg"], [[code, "2026-08-30", "2026-06-30", "0.25"]])


def test_baostock_adapter_keeps_provider_values_and_provenance() -> None:
    module = FakeBaoStock()
    result = BaoStockEquityDataProvider(lambda: module).fetch("600519", as_of="2026-09-05")
    assert result.symbol == "600519"
    assert result.company_name == "贵州茅台"
    assert result.valuation_metrics["peTTM"]["value"] == "22"
    assert result.valuation_metrics["peTTM"]["source_reference"].startswith("baostock:market:")
    assert result.fundamental_metrics["roeAvg"]["value"] == "0.25"
    assert all({"source", "as_of", "available_at", "fetched_at", "quality"} <= item.keys() for item in result.evidence)
    assert result.recent_market_data[0]["source_reference"].startswith("baostock:market:")
    assert module.logged_out is True


def test_optional_baostock_dependency_failure_is_clear() -> None:
    def unavailable():
        raise EquityDataProviderError("BaoStock dependency is unavailable")

    with pytest.raises(EquityDataProviderError, match="dependency is unavailable"):
        BaoStockEquityDataProvider(unavailable).fetch("600519", as_of="2026-09-05")
