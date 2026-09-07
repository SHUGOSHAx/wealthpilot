"""Synthetic CSV ingestion and deterministic FinancialSnapshot construction.

This module deliberately has no logging and no model dependency.  Raw P2 financial
rows are parsed in memory and only aggregate P1 facts leave the service.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Final

from wealthpilot.kernel.money import CNY, Money, format_decimal

MAX_FILE_BYTES: Final = 1_048_576
MAX_ROWS: Final = 10_000
MAX_TEXT_LENGTH: Final = 256
EXPECTED_HEADER: Final = (
    "record_type",
    "date",
    "account",
    "account_type",
    "category",
    "description",
    "amount",
    "currency",
    "liquid",
)
OPTIONAL_SOURCE_ID_HEADER: Final = EXPECTED_HEADER + ("source_transaction_id",)
PERSONAL_HEADER: Final = OPTIONAL_SOURCE_ID_HEADER + ("asset_class",)
_AMOUNT_PATTERN: Final = re.compile(r"^(?:0|[1-9][0-9]{0,13})(?:\.[0-9]{1,2})?$")
_TWO_PLACES: Final = Decimal("0.01")


class WealthCsvValidationError(ValueError):
    """A safe validation error that never includes uploaded field contents."""

    def __init__(self, code: str, *, row_number: int | None = None) -> None:
        self.code = code
        self.row_number = row_number
        suffix = f" at row {row_number}" if row_number is not None else ""
        super().__init__(f"{code}{suffix}")


@dataclass(frozen=True, slots=True)
class _Record:
    record_type: str
    date: date
    account: str
    account_type: str
    category: str
    description: str
    amount: Decimal
    liquid: bool
    source_transaction_id: str | None = None
    asset_class: str | None = None


def _fail(code: str, row_number: int | None = None) -> None:
    raise WealthCsvValidationError(code, row_number=row_number)


def _decode(csv_bytes: bytes) -> str:
    if not isinstance(csv_bytes, bytes):
        raise TypeError("csv_bytes must be bytes")
    if not csv_bytes:
        _fail("EMPTY_FILE")
    if len(csv_bytes) > MAX_FILE_BYTES:
        _fail("FILE_TOO_LARGE")
    if b"\x00" in csv_bytes:
        _fail("INVALID_ENCODING")
    try:
        return csv_bytes.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        _fail("INVALID_ENCODING")
    raise AssertionError("unreachable")


def _parse_date(value: str, row_number: int) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail("INVALID_DATE", row_number)
    if parsed.isoformat() != value:
        _fail("INVALID_DATE", row_number)
    return parsed


def _parse_amount(value: str, row_number: int) -> Decimal:
    if not _AMOUNT_PATTERN.fullmatch(value):
        _fail("INVALID_AMOUNT", row_number)
    try:
        amount = Decimal(value)
    except InvalidOperation:
        _fail("INVALID_AMOUNT", row_number)
    if not amount.is_finite() or amount <= 0:
        _fail("INVALID_AMOUNT", row_number)
    return amount.quantize(_TWO_PLACES)


def _parse_rows(text: str) -> list[_Record]:
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
    except StopIteration:
        _fail("EMPTY_FILE")
    except csv.Error:
        _fail("MALFORMED_CSV")
    parsed_header = tuple(header)
    if parsed_header not in {EXPECTED_HEADER, OPTIONAL_SOURCE_ID_HEADER, PERSONAL_HEADER}:
        _fail("INVALID_HEADER")
    has_source_id = parsed_header in {OPTIONAL_SOURCE_ID_HEADER, PERSONAL_HEADER}
    has_asset_class = parsed_header == PERSONAL_HEADER

    records: list[_Record] = []
    try:
        for row_number, row in enumerate(reader, start=2):
            if not row or all(not value.strip() for value in row):
                continue
            while len(row) < len(parsed_header):
                row.append("")
            if row_number - 1 > MAX_ROWS:
                _fail("TOO_MANY_ROWS")
            if len(row) != len(parsed_header):
                _fail("INVALID_COLUMN_COUNT", row_number)
            if any(len(value) > MAX_TEXT_LENGTH for value in row):
                _fail("FIELD_TOO_LONG", row_number)

            values = [value.strip() for value in row]
            record_type, day, account, account_type, category, description, amount, currency, liquid = values[:9]
            source_transaction_id = values[9] if has_source_id and values[9] else None
            asset_class = values[10].upper() if has_asset_class and values[10] else None
            if record_type not in {"BALANCE", "TRANSACTION"}:
                _fail("INVALID_RECORD_TYPE", row_number)
            if account_type not in {"ASSET", "LIABILITY"}:
                _fail("INVALID_ACCOUNT_TYPE", row_number)
            if not account or not description:
                _fail("REQUIRED_TEXT_MISSING", row_number)
            if currency != CNY:
                _fail("UNSUPPORTED_CURRENCY", row_number)
            if liquid not in {"true", "false"}:
                _fail("INVALID_LIQUID_FLAG", row_number)
            if record_type == "BALANCE" and category:
                _fail("INVALID_BALANCE_CATEGORY", row_number)
            if record_type == "BALANCE" and asset_class not in {
                None, "CASH", "EQUITY", "FIXED_INCOME", "REAL_ESTATE", "OTHER"
            }:
                _fail("INVALID_ASSET_CLASS", row_number)
            if record_type == "TRANSACTION" and category not in {"INCOME", "EXPENSE"}:
                _fail("INVALID_TRANSACTION_CATEGORY", row_number)

            records.append(
                _Record(
                    record_type=record_type,
                    date=_parse_date(day, row_number),
                    account=account,
                    account_type=account_type,
                    category=category,
                    description=description,
                    amount=_parse_amount(amount, row_number),
                    liquid=liquid == "true",
                    source_transaction_id=source_transaction_id,
                    asset_class=asset_class,
                )
            )
    except csv.Error:
        _fail("MALFORMED_CSV")

    if not records:
        _fail("NO_RECORDS")
    if not any(record.record_type == "BALANCE" for record in records):
        _fail("NO_BALANCES")
    return records


def _money(value: Decimal) -> dict[str, str]:
    return Money(value, CNY).to_dict()


def build_financial_snapshot(csv_bytes: bytes) -> dict[str, object]:
    """Build a JSON-serializable FinancialSnapshot from a validated MVP CSV.

    No uploaded source text, account name, or transaction description is emitted
    outside this return value or logged.  Every financial aggregate is calculated
    with :class:`Decimal`; no LLM or non-deterministic service is involved.
    """

    records = _parse_rows(_decode(csv_bytes))
    source_hash = hashlib.sha256(csv_bytes).hexdigest()

    balances: dict[tuple[str, str, bool], Decimal] = defaultdict(Decimal)
    inflow = Decimal("0")
    outflow = Decimal("0")
    monthly_outflow: dict[tuple[int, int], Decimal] = defaultdict(Decimal)

    for record in records:
        if record.record_type == "BALANCE":
            balances[(record.account, record.account_type, record.liquid)] += record.amount
        elif record.category == "INCOME":
            inflow += record.amount
        else:
            outflow += record.amount
            monthly_outflow[(record.date.year, record.date.month)] += record.amount

    assets = sum(
        (amount for (_, account_type, _), amount in balances.items() if account_type == "ASSET"),
        start=Decimal("0"),
    )
    liabilities = sum(
        (amount for (_, account_type, _), amount in balances.items() if account_type == "LIABILITY"),
        start=Decimal("0"),
    )
    liquid_assets = sum(
        (
            amount
            for (_, account_type, liquid), amount in balances.items()
            if account_type == "ASSET" and liquid
        ),
        start=Decimal("0"),
    )
    latest_month = max(monthly_outflow, default=None)
    monthly_expenses = monthly_outflow[latest_month] if latest_month else Decimal("0")
    emergency_months = (
        (liquid_assets / monthly_expenses).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        if monthly_expenses > 0
        else None
    )
    as_of_date = max(record.date for record in records)
    as_of = datetime.combine(as_of_date, datetime.min.time(), tzinfo=timezone.utc)

    account_items = [
        {
            "name": name,
            "account_type": account_type,
            "balance": _money(amount),
            "liquid": liquid,
            "asset_class": next(
                (
                    record.asset_class or "UNKNOWN"
                    for record in records
                    if record.record_type == "BALANCE" and record.account == name
                ),
                "UNKNOWN",
            ),
        }
        for (name, account_type, liquid), amount in sorted(balances.items())
    ]

    allocation: dict[str, Decimal] = defaultdict(Decimal)
    for item in account_items:
        if item["account_type"] == "ASSET":
            allocation[str(item["asset_class"])] += Decimal(str(item["balance"]["amount"]))
    snapshot = {
        "schema_version": "0.1.0-mvp",
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "source": {
            "sha256": source_hash,
            "record_count": len(records),
        },
        "accounts": account_items,
        "assets": _money(assets),
        "liabilities": _money(liabilities),
        "net_worth": _money(assets - liabilities),
        "liquid_assets": _money(liquid_assets),
        "cash_flow": {
            "inflow": _money(inflow),
            "outflow": _money(outflow),
            "net": _money(inflow - outflow),
        },
        "monthly_expenses": _money(monthly_expenses),
        "emergency_fund_months": format_decimal(emergency_months) if emergency_months is not None else None,
        "reserved_goals": _money(Decimal("0")),
        "investable_capital": _money(max(Decimal("0"), liquid_assets - monthly_expenses * Decimal("6"))),
        "asset_allocation": {key: _money(value) for key, value in sorted(allocation.items())},
        "data_quality": {
            "status": "DEMO_VALIDATED",
            "currency": CNY,
            "latest_expense_month": (
                f"{latest_month[0]:04d}-{latest_month[1]:02d}" if latest_month else None
            ),
        },
    }
    if "UNKNOWN" not in allocation:
        snapshot["existing_equity_exposure"] = _money(allocation.get("EQUITY", Decimal("0")))
    return snapshot
