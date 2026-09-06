from __future__ import annotations

import hashlib
import json
import logging
import unittest
from decimal import Decimal
from pathlib import Path

from wealthpilot.contexts.wealth.application.service import (
    WealthCsvValidationError,
    build_financial_snapshot,
)

FIXTURE = Path(__file__).parents[2] / "fixtures" / "demo" / "personal_finance.csv"
HEADER = "record_type,date,account,account_type,category,description,amount,currency,liquid"


def csv_bytes(row: str, header: str = HEADER) -> bytes:
    return f"{header}\n{row}\n".encode()


class FinancialSnapshotTests(unittest.TestCase):
    def test_demo_snapshot_has_correct_deterministic_totals(self) -> None:
        raw = FIXTURE.read_bytes()
        result = build_financial_snapshot(raw)

        self.assertEqual(result["assets"], {"amount": "2000000.00", "currency": "CNY"})
        self.assertEqual(result["liabilities"], {"amount": "955000.00", "currency": "CNY"})
        self.assertEqual(result["net_worth"], {"amount": "1045000.00", "currency": "CNY"})
        self.assertEqual(result["liquid_assets"], {"amount": "200000.00", "currency": "CNY"})
        self.assertEqual(result["cash_flow"]["inflow"]["amount"], "30000.00")
        self.assertEqual(result["cash_flow"]["outflow"]["amount"], "14000.00")
        self.assertEqual(result["cash_flow"]["net"]["amount"], "16000.00")
        self.assertEqual(result["monthly_expenses"]["amount"], "14000.00")
        self.assertEqual(result["emergency_fund_months"], "14.29")
        self.assertEqual(result["investable_capital"]["amount"], "116000.00")
        self.assertEqual(result["as_of"], "2026-09-04T00:00:00Z")
        self.assertEqual(result["source"]["sha256"], hashlib.sha256(raw).hexdigest())
        json.dumps(result, ensure_ascii=False)

    def test_account_balances_reconcile_to_assets_and_liabilities(self) -> None:
        result = build_financial_snapshot(FIXTURE.read_bytes())
        assets = sum(
            Decimal(item["balance"]["amount"])
            for item in result["accounts"]
            if item["account_type"] == "ASSET"
        )
        liabilities = sum(
            Decimal(item["balance"]["amount"])
            for item in result["accounts"]
            if item["account_type"] == "LIABILITY"
        )
        self.assertEqual(assets, Decimal("2000000.00"))
        self.assertEqual(liabilities, Decimal("955000.00"))

    def assert_error(self, row: str, code: str, *, header: str = HEADER) -> None:
        with self.assertRaises(WealthCsvValidationError) as caught:
            build_financial_snapshot(csv_bytes(row, header))
        self.assertEqual(caught.exception.code, code)

    def test_rejects_wrong_header(self) -> None:
        self.assert_error(
            "BALANCE,2026-09-01,Cash,ASSET,,Demo,1.00,CNY,true",
            "INVALID_HEADER",
            header="date,record_type,account,account_type,category,description,amount,currency,liquid",
        )

    def test_rejects_unsupported_currency(self) -> None:
        self.assert_error("BALANCE,2026-09-01,Cash,ASSET,,Demo,1.00,USD,true", "UNSUPPORTED_CURRENCY")

    def test_rejects_unknown_record_type(self) -> None:
        self.assert_error("OTHER,2026-09-01,Cash,ASSET,,Demo,1.00,CNY,true", "INVALID_RECORD_TYPE")

    def test_rejects_invalid_amount_forms(self) -> None:
        for amount in ("-1.00", "0.00", "NaN", "1e3", "1.001"):
            with self.subTest(amount=amount):
                self.assert_error(
                    f"BALANCE,2026-09-01,Cash,ASSET,,Demo,{amount},CNY,true",
                    "INVALID_AMOUNT",
                )

    def test_validation_does_not_log_uploaded_content(self) -> None:
        secret_marker = "SYNTHETIC_PRIVATE_MARKER"
        handler = _ListHandler()
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            self.assert_error(
                f"BALANCE,2026-09-01,{secret_marker},ASSET,,Demo,bad,CNY,true",
                "INVALID_AMOUNT",
            )
        finally:
            root.removeHandler(handler)
        self.assertNotIn(secret_marker, " ".join(handler.messages))


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


if __name__ == "__main__":
    unittest.main()
