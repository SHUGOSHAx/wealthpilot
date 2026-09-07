"""Credential-free BaoStock adapter for personal, non-real-time research.

Runtime dependency (intentionally optional): ``pip install baostock``.
Import is lazy so offline tests and the cached demo remain dependency-free.
"""

from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from wealthpilot.contexts.research.equity_data import (
    EquityDataProvider,
    EquityDataProviderError,
    EquityResearchData,
)

OPTIONAL_DEPENDENCY = "baostock"


class BaoStockEquityDataProvider(EquityDataProvider):
    provider_name = "BaoStock"

    def __init__(self, module_loader: Callable[[], Any] | None = None) -> None:
        self._module_loader = module_loader or _load_baostock

    def fetch(self, symbol: str, *, as_of: str | None = None) -> EquityResearchData:
        code, normalized, exchange = _provider_code(symbol)
        end = date.fromisoformat(as_of) if as_of else datetime.now(timezone.utc).date()
        bs = self._module_loader()
        login = bs.login()
        if getattr(login, "error_code", "1") != "0":
            raise EquityDataProviderError("BaoStock login failed")
        try:
            basic_rows = _rows(bs.query_stock_basic(code=code))
            if not basic_rows:
                raise EquityDataProviderError(f"security not found: {normalized}")
            basic = basic_rows[0]
            market = _rows(
                bs.query_history_k_data_plus(
                    code,
                    "date,code,open,high,low,close,volume,amount,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST",
                    start_date=(end - timedelta(days=120)).isoformat(),
                    end_date=end.isoformat(),
                    frequency="d",
                    adjustflag="2",
                )
            )
            market = market[-60:]
            profit, period = self._latest_profit(bs, code, end)
        except EquityDataProviderError:
            raise
        except Exception as exc:
            raise EquityDataProviderError("BaoStock query failed") from exc
        finally:
            bs.logout()

        latest = market[-1] if market else {}
        company = str(basic.get("code_name") or normalized)
        fetched_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        evidence: list[dict[str, Any]] = []
        security_ref = f"baostock:security:{code}"
        market_ref = f"baostock:market:{code}:{latest.get('date', end.isoformat())}"
        profit_ref = f"baostock:profit:{code}:{period}"
        evidence.append({"evidence_id": security_ref, "source": "BaoStock.query_stock_basic", "as_of": end.isoformat(), "available_at": end.isoformat(), "fetched_at": fetched_at, "quality": "PUBLIC_PROVIDER_UNVERIFIED"})
        basic = dict(basic, as_of=end.isoformat(), fetched_at=fetched_at, source_reference=security_ref)
        if market:
            evidence.append({"evidence_id": market_ref, "source": "BaoStock.query_history_k_data_plus", "as_of": latest.get("date", end.isoformat()), "available_at": latest.get("date", end.isoformat()), "fetched_at": fetched_at, "quality": "PUBLIC_PROVIDER_UNVERIFIED"})
        if profit:
            profit_as_of = str(profit.get("statDate") or period)
            profit_available_at = str(profit["pubDate"]) if profit.get("pubDate") else None
            evidence.append(
                {
                    "evidence_id": profit_ref,
                    "source": "BaoStock.query_profit_data",
                    "as_of": profit_as_of,
                    "available_at": profit_available_at,
                    "fetched_at": fetched_at,
                    "quality": "PUBLIC_PROVIDER_UNVERIFIED" if profit_available_at else "AVAILABLE_AT_UNKNOWN",
                }
            )
        valuation = {
            key: {"value": latest[key], "as_of": latest.get("date", end.isoformat()), "source_reference": market_ref}
            for key in ("peTTM", "pbMRQ", "psTTM", "pcfNcfTTM")
            if latest.get(key) not in (None, "")
        }
        fundamentals = {
            key: {"value": value, "as_of": str(profit.get("statDate") or period), "source_reference": profit_ref}
            for key, value in profit.items()
            if value not in (None, "")
        }
        market = [dict(row, source_reference=market_ref) for row in market]
        limitations = ["BaoStock 为公开历史数据源，数据可能延迟，不能作为实时行情。", "本研究不构成投资建议。"]
        if not market:
            limitations.append("未取得近期日线或估值数据。")
        if not fundamentals:
            limitations.append("未取得可用的近期盈利指标。")
        elif not profit.get("pubDate"):
            limitations.append("BaoStock 未提供本季度指标的披露可用时间；available_at 保持 null。")
        return EquityResearchData(
            symbol=normalized,
            company_name=company,
            exchange=exchange,
            as_of=end.isoformat(),
            fetched_at=fetched_at,
            security_info=basic,
            recent_market_data=market,
            fundamental_metrics=fundamentals,
            valuation_metrics=valuation,
            evidence=evidence,
            limitations=limitations,
            provider=self.provider_name,
        )

    @staticmethod
    def _latest_profit(bs: Any, code: str, end: date) -> tuple[dict[str, Any], str]:
        quarter = (end.month - 1) // 3 + 1
        year = end.year
        for _ in range(6):
            rows = _rows(bs.query_profit_data(code=code, year=year, quarter=quarter))
            if rows:
                return rows[0], f"{year}-Q{quarter}"
            quarter -= 1
            if quarter == 0:
                year -= 1
                quarter = 4
        return {}, f"{end.year}-Q{(end.month - 1) // 3 + 1}"


def _load_baostock() -> Any:
    try:
        return importlib.import_module("baostock")
    except ImportError as exc:
        raise EquityDataProviderError("BaoStock dependency is unavailable; install optional package 'baostock'") from exc


def _provider_code(symbol: str) -> tuple[str, str, str]:
    normalized = symbol.strip().split(".")[-1]
    if len(normalized) != 6 or not normalized.isdigit():
        raise EquityDataProviderError("A-share symbol must contain exactly six digits")
    exchange = "SSE" if normalized.startswith(("5", "6", "9")) else "SZSE"
    prefix = "sh" if exchange == "SSE" else "sz"
    return f"{prefix}.{normalized}", normalized, exchange


def _rows(result: Any) -> list[dict[str, Any]]:
    if getattr(result, "error_code", "1") != "0":
        raise EquityDataProviderError("BaoStock returned a query error")
    fields = list(getattr(result, "fields", []))
    output: list[dict[str, Any]] = []
    while result.next():
        output.append(dict(zip(fields, result.get_row_data(), strict=True)))
    return output
