"""SQLite-backed local personal-finance import, ledger, and snapshot service."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import unicodedata
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from wealthpilot.adapters.persistence.migrations import LATEST_SCHEMA_VERSION, MIGRATIONS
from wealthpilot.contexts.wealth.application.service import (
    _Record,
    _decode,
    _money,
    _parse_rows,
)
from wealthpilot.kernel.money import CNY, format_decimal


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_database_path() -> Path:
    """Return a user-local database path outside the source checkout."""

    configured = os.environ.get("WEALTHPILOT_DATABASE_PATH")
    if configured:
        return Path(configured).expanduser()
    data_home = os.environ.get("XDG_DATA_HOME")
    root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return root / "wealthpilot" / "wealthpilot.db"


def _connect(path: str | Path) -> sqlite3.Connection:
    if str(path) != ":memory:":
        resolved = Path(path).expanduser().resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    if str(path) != ":memory:":
        os.chmod(resolved, 0o600)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    if str(path) != ":memory:":
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
    return connection


def _apply_migrations(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
    unknown = [version for version in applied if version > LATEST_SCHEMA_VERSION]
    if unknown:
        raise RuntimeError("database schema is newer than this application")
    for version, name, sql in MIGRATIONS:
        if version in applied:
            continue
        safe_name = name.replace("'", "''")
        safe_timestamp = _now().replace("'", "''")
        try:
            connection.executescript(
                f"""BEGIN IMMEDIATE;
                {sql}
                INSERT INTO schema_migrations(version, name, applied_at)
                VALUES ({version}, '{safe_name}', '{safe_timestamp}');
                COMMIT;"""
            )
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def _normalized_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _sha256_fields(*values: str) -> str:
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _transaction_identity(record: _Record) -> tuple[str, str, str]:
    fallback = _sha256_fields(
        record.date.isoformat(),
        _normalized_text(record.account),
        record.account_type,
        record.category,
        _normalized_text(record.description),
        format_decimal(record.amount),
        CNY,
    )
    if record.source_transaction_id:
        stable = _sha256_fields(
            _normalized_text(record.account),
            _normalized_text(record.source_transaction_id),
        )
        return f"sid:{stable}", fallback, "SOURCE_ID"
    return f"fp:{fallback}", fallback, "FINGERPRINT"


def _classify(description: str, direction: str) -> str:
    text = _normalized_text(description)
    rules = (
        (("salary", "payroll", "工资", "薪资"), "工资收入"),
        (("rent", "房租", "物业"), "住房"),
        (("restaurant", "coffee", "meal", "餐饮", "咖啡", "外卖"), "餐饮"),
        (("taxi", "metro", "rail", "交通", "地铁", "打车"), "交通"),
        (("hospital", "pharmacy", "医疗", "药房"), "医疗"),
        (("tuition", "course", "学费", "课程"), "教育"),
    )
    for keywords, label in rules:
        if any(keyword in text for keyword in keywords):
            return label
    return "其他收入" if direction == "INCOME" else "其他"


class SQLiteWealthService:
    """Transactional local-first application facade backed by SQLite."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = database_path if database_path is not None else default_database_path()
        self._connection = _connect(self.database_path)
        _apply_migrations(self._connection)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> SQLiteWealthService:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def schema_version(self) -> int:
        row = self._connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        return int(row[0] or 0)

    def create_import_preview(
        self,
        csv_bytes: bytes,
        *,
        source_kind: str = "GENERIC_CSV",
        source_filename: str | None = None,
    ) -> dict[str, Any]:
        records = _parse_rows(_decode(csv_bytes))
        source_hash = hashlib.sha256(csv_bytes).hexdigest()
        existing = self._connection.execute(
            "SELECT id FROM import_batches WHERE source_sha256 = ?", (source_hash,)
        ).fetchone()
        if existing:
            return self.get_import_preview(existing["id"])

        batch_id = str(uuid.uuid4())
        created_at = _now()
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._connection.execute(
                """INSERT INTO import_batches
                   (id, source_sha256, status, record_count, created_at, source_kind, source_filename)
                   VALUES (?, ?, 'PREVIEW', ?, ?, ?, ?)""",
                (
                    batch_id,
                    source_hash,
                    len(records),
                    created_at,
                    source_kind.strip().upper() or "GENERIC_CSV",
                    Path(source_filename).name if source_filename else None,
                ),
            )
            for row_number, record in enumerate(records, start=2):
                if record.record_type == "BALANCE":
                    self._insert_balance(batch_id, row_number, record)
                else:
                    self._insert_transaction(batch_id, row_number, record, created_at)
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return self.get_import_preview(batch_id)

    def _insert_balance(self, batch_id: str, row_number: int, record: _Record) -> None:
        self._connection.execute(
            """INSERT INTO import_balance_observations
               (id, batch_id, row_number, observed_on, account_name, account_type,
                amount, currency, liquid, asset_class)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), batch_id, row_number, record.date.isoformat(), record.account,
                record.account_type, format_decimal(record.amount), CNY, int(record.liquid),
                record.asset_class or "UNKNOWN",
            ),
        )

    def _insert_transaction(
        self, batch_id: str, row_number: int, record: _Record, created_at: str
    ) -> None:
        stable_identity, fingerprint, identity_reason = _transaction_identity(record)
        duplicate = self._connection.execute(
            """SELECT t.id
               FROM normalized_transactions t
               JOIN import_batches b ON b.id = t.batch_id
               WHERE t.stable_identity = ?
                 AND (b.status = 'CONFIRMED' OR t.batch_id = ?)
                 AND t.duplicate_of_transaction_id IS NULL
               ORDER BY t.created_at, t.row_number
               LIMIT 1""",
            (stable_identity, batch_id),
        ).fetchone()
        self._connection.execute(
            """INSERT INTO normalized_transactions
               (id, batch_id, row_number, stable_identity, source_transaction_id,
                fallback_fingerprint, transaction_date, account_name, account_type,
                original_category, category, classification, merchant_original, merchant_normalized,
                amount, currency, liquid, duplicate_of_transaction_id, duplicate_reason,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), batch_id, row_number, stable_identity,
                record.source_transaction_id, fingerprint, record.date.isoformat(), record.account,
                record.account_type, record.category, record.category,
                _classify(record.description, record.category), record.description,
                record.description.strip(), format_decimal(record.amount), CNY, int(record.liquid),
                duplicate["id"] if duplicate else None, identity_reason if duplicate else None,
                created_at,
            ),
        )

    def get_import_preview(self, batch_id: str) -> dict[str, Any]:
        batch = self._connection.execute(
            "SELECT * FROM import_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if not batch:
            raise KeyError("import batch not found")
        rows = self._connection.execute(
            """SELECT id, transaction_date, account_name, account_type, category, classification,
                      merchant_normalized, amount, currency, is_transfer, is_refund,
                      is_reimbursement, duplicate_of_transaction_id, duplicate_reason
               FROM normalized_transactions WHERE batch_id = ? ORDER BY row_number""",
            (batch_id,),
        ).fetchall()
        transactions = [
            {
                "transaction_id": row["id"],
                "date": row["transaction_date"],
                "account": row["account_name"],
                "account_type": row["account_type"],
                "category": row["classification"],
                "direction": "INFLOW" if row["category"] == "INCOME" else "OUTFLOW",
                "merchant_normalized": row["merchant_normalized"],
                "amount": {"amount": row["amount"], "currency": row["currency"]},
                "flags": {
                    "transfer": bool(row["is_transfer"]),
                    "refund": bool(row["is_refund"]),
                    "reimbursement": bool(row["is_reimbursement"]),
                },
                "duplicate": row["duplicate_of_transaction_id"] is not None,
                "duplicate_reason": row["duplicate_reason"],
            }
            for row in rows
        ]
        duplicate_count = sum(item["duplicate"] for item in transactions)
        new_count = len(transactions) - duplicate_count
        overlap = (
            "PARTIAL_OVERLAP"
            if duplicate_count and new_count
            else "DUPLICATE_ONLY" if duplicate_count else "NONE"
        )
        return {
            "batch_id": batch["id"],
            "status": batch["status"],
            "source_sha256": batch["source_sha256"],
            "source_kind": batch["source_kind"],
            "source_filename": batch["source_filename"],
            "record_count": batch["record_count"],
            "new_transaction_count": new_count,
            "duplicate_transaction_count": duplicate_count,
            "overlap": overlap,
            "transactions": transactions,
        }

    def correct_transaction(
        self,
        batch_id: str,
        transaction_id: str,
        *,
        category: str | None = None,
        merchant_normalized: str | None = None,
        is_transfer: bool | None = None,
        is_refund: bool | None = None,
        is_reimbursement: bool | None = None,
    ) -> dict[str, Any]:
        batch = self._connection.execute(
            "SELECT status FROM import_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if not batch:
            raise KeyError("import batch not found")
        if batch["status"] != "PREVIEW":
            raise ValueError("confirmed imports are immutable")
        row = self._connection.execute(
            "SELECT * FROM normalized_transactions WHERE id = ? AND batch_id = ?",
            (transaction_id, batch_id),
        ).fetchone()
        if not row:
            raise KeyError("transaction not found")
        updates: dict[str, object] = {}
        if category is not None:
            cleaned_category = category.strip()
            if not cleaned_category or len(cleaned_category) > 80:
                raise ValueError("category must be 1-80 characters")
            updates["classification"] = cleaned_category
        if merchant_normalized is not None:
            cleaned = merchant_normalized.strip()
            if not cleaned or len(cleaned) > 256:
                raise ValueError("merchant_normalized must be 1-256 characters")
            updates["merchant_normalized"] = cleaned
        for key, value in (
            ("is_transfer", is_transfer),
            ("is_refund", is_refund),
            ("is_reimbursement", is_reimbursement),
        ):
            if value is not None:
                if not isinstance(value, bool):
                    raise TypeError(f"{key} must be bool")
                updates[key] = int(value)
        if not updates:
            raise ValueError("at least one correction is required")
        self._validate_correction_flags(row, updates)
        changes = {
            key: {"from": row[key], "to": value}
            for key, value in updates.items()
            if row[key] != value
        }
        if changes:
            assignments = ", ".join(f"{key} = ?" for key in updates)
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    f"UPDATE normalized_transactions SET {assignments} WHERE id = ?",  # noqa: S608
                    (*updates.values(), transaction_id),
                )
                self._connection.execute(
                    """INSERT INTO transaction_corrections
                       (id, transaction_id, changed_at, changes_json) VALUES (?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()), transaction_id, _now(),
                        json.dumps(changes, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    ),
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return self.get_import_preview(batch_id)

    def confirm_import(self, batch_id: str) -> dict[str, Any]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            batch = self._connection.execute(
                "SELECT * FROM import_batches WHERE id = ?", (batch_id,)
            ).fetchone()
            if not batch:
                raise KeyError("import batch not found")
            if batch["status"] == "CONFIRMED":
                snapshot = self._snapshot_for_batch(batch_id)
                self._connection.execute("COMMIT")
                return snapshot

            transactions = self._connection.execute(
                """SELECT * FROM normalized_transactions
                   WHERE batch_id = ? AND duplicate_of_transaction_id IS NULL
                   ORDER BY row_number""",
                (batch_id,),
            ).fetchall()
            for transaction in transactions:
                self._post_transaction(batch_id, transaction)
            reconciliation = self._reconcile_in_transaction(batch_id)
            if not reconciliation["balanced"]:
                raise RuntimeError("ledger reconciliation failed")
            confirmed_at = _now()
            self._connection.execute(
                "UPDATE import_batches SET status = 'CONFIRMED', confirmed_at = ? WHERE id = ?",
                (confirmed_at, batch_id),
            )
            payload = self._build_persisted_snapshot(batch_id)
            self._persist_snapshot(batch_id, payload, confirmed_at)
            self._connection.execute("COMMIT")
            return payload
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def _post_transaction(
        self,
        batch_id: str,
        transaction: sqlite3.Row,
        *,
        entry_kind: str = "ORIGINAL",
        reverses_journal_entry_id: str | None = None,
    ) -> str:
        journal_id = str(uuid.uuid4())
        description = transaction["merchant_normalized"]
        self._connection.execute(
            """INSERT INTO journal_entries
               (id, batch_id, transaction_id, entry_date, description, entry_kind,
                reverses_journal_entry_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                journal_id, batch_id, transaction["id"], transaction["transaction_date"],
                description, entry_kind, reverses_journal_entry_id, _now(),
            ),
        )
        account = f"{transaction['account_type'].title()}:{transaction['account_name']}"
        if transaction["is_transfer"]:
            counterpart = "Transfers:Clearing"
        elif transaction["is_refund"]:
            counterpart = "Expenses:Refund"
        elif transaction["is_reimbursement"]:
            counterpart = "Expenses:Reimbursement"
        else:
            counterpart = f"{transaction['category'].title()}:{transaction['classification']}"
        account_direction = "DEBIT" if transaction["category"] == "INCOME" else "CREDIT"
        counterpart_direction = "CREDIT" if account_direction == "DEBIT" else "DEBIT"
        amount = format_decimal(Decimal(transaction["amount"]))
        for posting_account, direction in (
            (account, account_direction),
            (counterpart, counterpart_direction),
        ):
            self._connection.execute(
                """INSERT INTO postings
                   (id, journal_entry_id, account_name, direction, amount, currency)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), journal_id, posting_account, direction, amount, CNY),
            )
        return journal_id

    def _reverse_journal_entry(
        self, batch_id: str, transaction: sqlite3.Row, journal_entry_id: str
    ) -> str:
        reversal_id = str(uuid.uuid4())
        self._connection.execute(
            """INSERT INTO journal_entries
               (id, batch_id, transaction_id, entry_date, description, entry_kind,
                reverses_journal_entry_id, created_at)
               VALUES (?, ?, ?, ?, ?, 'REVERSAL', ?, ?)""",
            (
                reversal_id, batch_id, transaction["id"], transaction["transaction_date"],
                f"Reversal: {transaction['merchant_normalized']}", journal_entry_id, _now(),
            ),
        )
        postings = self._connection.execute(
            """SELECT account_name, direction, amount, currency FROM postings
               WHERE journal_entry_id = ? ORDER BY id""",
            (journal_entry_id,),
        ).fetchall()
        if len(postings) != 2:
            raise RuntimeError("active journal entry must contain exactly two postings")
        for posting in postings:
            direction = "CREDIT" if posting["direction"] == "DEBIT" else "DEBIT"
            self._connection.execute(
                """INSERT INTO postings
                   (id, journal_entry_id, account_name, direction, amount, currency)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), reversal_id, posting["account_name"], direction,
                    posting["amount"], posting["currency"],
                ),
            )
        return reversal_id

    def _build_persisted_snapshot(self, batch_id: str) -> dict[str, Any]:
        batch = self._connection.execute(
            "SELECT * FROM import_batches WHERE id = ? AND status = 'CONFIRMED'", (batch_id,)
        ).fetchone()
        if not batch:
            raise RuntimeError("snapshot requires a confirmed import")
        balance_rows = self._connection.execute(
            """SELECT * FROM (
                   SELECT o.*,
                          ROW_NUMBER() OVER (
                              PARTITION BY o.account_name, o.account_type
                              ORDER BY o.observed_on DESC, b.confirmed_at DESC, o.row_number DESC
                          ) AS rank
                   FROM import_balance_observations o
                   JOIN import_batches b ON b.id = o.batch_id
                   WHERE b.status = 'CONFIRMED'
               ) WHERE rank = 1 ORDER BY account_name"""
        ).fetchall()
        transactions = self._connection.execute(
            """SELECT t.* FROM normalized_transactions t
               JOIN journal_entries j ON j.transaction_id = t.id
               JOIN import_batches b ON b.id = t.batch_id
               WHERE b.status = 'CONFIRMED' AND t.duplicate_of_transaction_id IS NULL
                 AND j.entry_kind IN ('ORIGINAL', 'REPLACEMENT')
                 AND NOT EXISTS (
                     SELECT 1 FROM journal_entries r
                     WHERE r.entry_kind = 'REVERSAL' AND r.reverses_journal_entry_id = j.id
                 )
               ORDER BY t.row_number""",
        ).fetchall()
        account_totals: dict[tuple[str, str, bool], Decimal] = {}
        account_observed_on: dict[tuple[str, str, bool], str] = {}
        account_asset_class: dict[tuple[str, str, bool], str] = {}
        for row in balance_rows:
            key = (row["account_name"], row["account_type"], bool(row["liquid"]))
            account_totals[key] = account_totals.get(key, Decimal("0")) + Decimal(row["amount"])
            account_observed_on[key] = row["observed_on"]
            account_asset_class[key] = row["asset_class"]

        # A balance row is an end-of-day observation. Confirmed transactions
        # after that observation advance the account to the snapshot as-of date.
        # Transactions on the observation date are assumed already reflected.
        for row in transactions:
            matching = [
                key for key in account_totals
                if key[0] == row["account_name"] and key[1] == row["account_type"]
            ]
            for key in matching:
                if row["transaction_date"] <= account_observed_on[key]:
                    continue
                amount = Decimal(row["amount"])
                increases = row["category"] == "INCOME"
                if row["account_type"] == "LIABILITY":
                    increases = not increases
                account_totals[key] += amount if increases else -amount
        assets = sum(
            (amount for (_, kind, _), amount in account_totals.items() if kind == "ASSET"),
            Decimal("0"),
        )
        liabilities = sum(
            (amount for (_, kind, _), amount in account_totals.items() if kind == "LIABILITY"),
            Decimal("0"),
        )
        liquid_assets = sum(
            (
                amount for (_, kind, liquid), amount in account_totals.items()
                if kind == "ASSET" and liquid
            ),
            Decimal("0"),
        )
        dates = [row["observed_on"] for row in balance_rows] + [
            row["transaction_date"] for row in transactions
        ]
        as_of_date = max(dates)
        reporting_month = as_of_date[:7]
        included = [
            row for row in transactions
            if not row["is_transfer"] and row["transaction_date"].startswith(reporting_month)
        ]
        inflow = sum(
            (Decimal(row["amount"]) for row in included if row["category"] == "INCOME"),
            Decimal("0"),
        )
        outflow = sum(
            (Decimal(row["amount"]) for row in included if row["category"] == "EXPENSE"),
            Decimal("0"),
        )
        offsets = sum(
            (
                Decimal(row["amount"]) for row in included
                if row["category"] == "INCOME"
                and (row["is_refund"] or row["is_reimbursement"])
            ),
            Decimal("0"),
        )
        reimbursable_outflow = sum(
            (
                Decimal(row["amount"]) for row in included
                if row["category"] == "EXPENSE" and row["is_reimbursement"]
            ),
            Decimal("0"),
        )
        monthly_expenses = max(Decimal("0"), outflow - reimbursable_outflow - offsets)
        emergency_months = (
            (liquid_assets / monthly_expenses).quantize(Decimal("0.01"))
            if monthly_expenses else None
        )
        as_of = f"{as_of_date}T00:00:00Z"
        confirmed_batch_count = self._connection.execute(
            "SELECT COUNT(*) FROM import_batches WHERE status = 'CONFIRMED'"
        ).fetchone()[0]
        allocation: dict[str, Decimal] = {}
        for key, amount in account_totals.items():
            if key[1] == "ASSET":
                asset_class = account_asset_class[key]
                allocation[asset_class] = allocation.get(asset_class, Decimal("0")) + amount
        snapshot = {
            "schema_version": "0.1.0-mvp",
            "as_of": as_of,
            "source": {
                "sha256": batch["source_sha256"],
                "record_count": batch["record_count"],
                "scope": "ALL_CONFIRMED_IMPORTS",
                "confirmed_batch_count": confirmed_batch_count,
            },
            "accounts": [
                {
                    "name": name,
                    "account_type": kind,
                    "balance": _money(amount),
                    "liquid": liquid,
                    "asset_class": account_asset_class[(name, kind, liquid)],
                }
                for (name, kind, liquid), amount in sorted(account_totals.items())
            ],
            "assets": _money(assets),
            "liabilities": _money(liabilities),
            "net_worth": _money(assets - liabilities),
            "liquid_assets": _money(liquid_assets),
            "cash_flow": {
                "inflow": _money(inflow), "outflow": _money(outflow), "net": _money(inflow - outflow),
                "refunds_and_reimbursements": _money(offsets),
                "reimbursable_outflow": _money(reimbursable_outflow),
            },
            "monthly_expenses": _money(monthly_expenses),
            "emergency_fund_months": (
                format_decimal(emergency_months) if emergency_months is not None else None
            ),
            "reserved_goals": _money(Decimal("0")),
            "investable_capital": _money(
                max(Decimal("0"), liquid_assets - monthly_expenses * Decimal("6"))
            ),
            "asset_allocation": {key: _money(value) for key, value in sorted(allocation.items())},
            "data_quality": {
                "status": "CONFIRMED_RECONCILED", "currency": CNY,
                "cash_flow_month": reporting_month,
            },
        }
        if "UNKNOWN" not in allocation:
            snapshot["existing_equity_exposure"] = _money(allocation.get("EQUITY", Decimal("0")))
        return snapshot

    def _persist_snapshot(self, batch_id: str, payload: dict[str, Any], created_at: str) -> None:
        revision = self._connection.execute(
            "SELECT COALESCE(MAX(revision), 0) + 1 FROM financial_snapshots WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()[0]
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self._connection.execute(
            """INSERT INTO financial_snapshots
               (id, batch_id, revision, as_of, payload_json, content_sha256, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), batch_id, revision, payload["as_of"], encoded,
                hashlib.sha256(encoded.encode("utf-8")).hexdigest(), created_at,
            ),
        )

    def _snapshot_for_batch(self, batch_id: str) -> dict[str, Any]:
        row = self._connection.execute(
            """SELECT payload_json FROM financial_snapshots WHERE batch_id = ?
               ORDER BY revision DESC LIMIT 1""",
            (batch_id,),
        ).fetchone()
        if not row:
            raise RuntimeError("confirmed batch has no snapshot")
        return json.loads(row["payload_json"])

    def latest_financial_snapshot(self) -> dict[str, Any] | None:
        row = self._connection.execute(
            """SELECT payload_json FROM financial_snapshots
               ORDER BY created_at DESC, rowid DESC LIMIT 1"""
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def financial_snapshot_history(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT payload_json FROM financial_snapshots ORDER BY created_at, rowid"
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def correct_confirmed_transaction(
        self,
        batch_id: str,
        transaction_id: str,
        *,
        category: str | None = None,
        merchant_normalized: str | None = None,
        is_transfer: bool | None = None,
        is_refund: bool | None = None,
        is_reimbursement: bool | None = None,
    ) -> dict[str, Any]:
        """Correct a committed transaction through immutable reversal/replacement entries."""

        self._connection.execute("BEGIN IMMEDIATE")
        try:
            batch = self._connection.execute(
                "SELECT status FROM import_batches WHERE id = ?", (batch_id,)
            ).fetchone()
            if not batch:
                raise KeyError("import batch not found")
            if batch["status"] != "CONFIRMED":
                raise ValueError("use correct_transaction before confirmation")
            transaction = self._connection.execute(
                """SELECT * FROM normalized_transactions
                   WHERE id = ? AND batch_id = ? AND duplicate_of_transaction_id IS NULL""",
                (transaction_id, batch_id),
            ).fetchone()
            if not transaction:
                raise KeyError("committed transaction not found")
            active = self._connection.execute(
                """SELECT j.id FROM journal_entries j
                   WHERE j.transaction_id = ? AND j.entry_kind IN ('ORIGINAL', 'REPLACEMENT')
                     AND NOT EXISTS (
                         SELECT 1 FROM journal_entries r
                         WHERE r.entry_kind = 'REVERSAL' AND r.reverses_journal_entry_id = j.id
                     )
                   ORDER BY j.created_at DESC LIMIT 1""",
                (transaction_id,),
            ).fetchone()
            if not active:
                raise RuntimeError("transaction has no active journal entry")

            updates = self._validated_correction_updates(
                transaction,
                category=category,
                merchant_normalized=merchant_normalized,
                is_transfer=is_transfer,
                is_refund=is_refund,
                is_reimbursement=is_reimbursement,
            )
            self._reverse_journal_entry(batch_id, transaction, active["id"])
            assignments = ", ".join(f"{key} = ?" for key in updates)
            self._connection.execute(
                f"UPDATE normalized_transactions SET {assignments} WHERE id = ?",  # noqa: S608
                (*updates.values(), transaction_id),
            )
            updated = self._connection.execute(
                "SELECT * FROM normalized_transactions WHERE id = ?", (transaction_id,)
            ).fetchone()
            self._post_transaction(
                batch_id, updated, entry_kind="REPLACEMENT", reverses_journal_entry_id=active["id"]
            )
            changes = {
                key: {"from": transaction[key], "to": value}
                for key, value in updates.items() if transaction[key] != value
            }
            self._connection.execute(
                """INSERT INTO transaction_corrections
                   (id, transaction_id, changed_at, changes_json) VALUES (?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), transaction_id, _now(),
                    json.dumps(changes, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                ),
            )
            reconciliation = self._reconcile_in_transaction(batch_id)
            if not reconciliation["balanced"]:
                raise RuntimeError("ledger reconciliation failed after correction")
            payload = self._build_persisted_snapshot(batch_id)
            self._persist_snapshot(batch_id, payload, _now())
            self._connection.execute("COMMIT")
            return payload
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _validated_correction_updates(
        row: sqlite3.Row,
        *,
        category: str | None,
        merchant_normalized: str | None,
        is_transfer: bool | None,
        is_refund: bool | None,
        is_reimbursement: bool | None,
    ) -> dict[str, object]:
        updates: dict[str, object] = {}
        if category is not None:
            cleaned_category = category.strip()
            if not cleaned_category or len(cleaned_category) > 80:
                raise ValueError("category must be 1-80 characters")
            updates["classification"] = cleaned_category
        if merchant_normalized is not None:
            cleaned = merchant_normalized.strip()
            if not cleaned or len(cleaned) > 256:
                raise ValueError("merchant_normalized must be 1-256 characters")
            updates["merchant_normalized"] = cleaned
        for key, value in (
            ("is_transfer", is_transfer),
            ("is_refund", is_refund),
            ("is_reimbursement", is_reimbursement),
        ):
            if value is not None:
                if not isinstance(value, bool):
                    raise TypeError(f"{key} must be bool")
                updates[key] = int(value)
        if not updates:
            raise ValueError("at least one correction is required")
        if all(row[key] == value for key, value in updates.items()):
            raise ValueError("correction does not change the transaction")
        SQLiteWealthService._validate_correction_flags(row, updates)
        return updates

    @staticmethod
    def _validate_correction_flags(row: sqlite3.Row, updates: dict[str, object]) -> None:
        direction = row["category"]
        transfer = bool(updates.get("is_transfer", row["is_transfer"]))
        refund = bool(updates.get("is_refund", row["is_refund"]))
        reimbursement = bool(updates.get("is_reimbursement", row["is_reimbursement"]))
        if sum((transfer, refund, reimbursement)) > 1:
            raise ValueError("transfer, refund, and reimbursement flags are mutually exclusive")
        if refund and direction != "INCOME":
            raise ValueError("refund transactions must use INCOME category")

    def list_transactions(self) -> list[dict[str, Any]]:
        """Return committed, non-duplicate transactions without raw source text."""

        rows = self._connection.execute(
            """SELECT t.*, b.confirmed_at
               FROM normalized_transactions t
               JOIN import_batches b ON b.id = t.batch_id
               WHERE b.status = 'CONFIRMED' AND t.duplicate_of_transaction_id IS NULL
               ORDER BY t.transaction_date DESC, t.created_at DESC"""
        ).fetchall()
        return [
            {
                "transaction_id": row["id"],
                "batch_id": row["batch_id"],
                "date": row["transaction_date"],
                "account": row["account_name"],
                "account_type": row["account_type"],
                "category": row["classification"],
                "direction": "INFLOW" if row["category"] == "INCOME" else "OUTFLOW",
                "merchant_normalized": row["merchant_normalized"],
                "amount": {"amount": row["amount"], "currency": row["currency"]},
                "flags": {
                    "transfer": bool(row["is_transfer"]),
                    "refund": bool(row["is_refund"]),
                    "reimbursement": bool(row["is_reimbursement"]),
                },
                "confirmed_at": row["confirmed_at"],
            }
            for row in rows
        ]

    def reconcile(self, batch_id: str | None = None) -> dict[str, Any]:
        return self._reconcile_in_transaction(batch_id)

    def _reconcile_in_transaction(self, batch_id: str | None) -> dict[str, Any]:
        where = "WHERE j.batch_id = ?" if batch_id else ""
        params: tuple[str, ...] = (batch_id,) if batch_id else ()
        rows = self._connection.execute(
            f"""SELECT j.id,
                       SUM(CASE WHEN p.direction = 'DEBIT' THEN CAST(p.amount AS NUMERIC) ELSE 0 END) debit,
                       SUM(CASE WHEN p.direction = 'CREDIT' THEN CAST(p.amount AS NUMERIC) ELSE 0 END) credit,
                       COUNT(p.id) posting_count
                FROM journal_entries j JOIN postings p ON p.journal_entry_id = j.id
                {where} GROUP BY j.id""",  # noqa: S608
            params,
        ).fetchall()
        imbalanced = [row["id"] for row in rows if Decimal(str(row["debit"])) != Decimal(str(row["credit"]))]
        bad_counts = [row["id"] for row in rows if row["posting_count"] != 2]
        duplicate_postings = self._connection.execute(
            f"""SELECT COUNT(*) FROM (
                    SELECT p.journal_entry_id, p.direction, p.account_name, COUNT(*) count
                    FROM postings p JOIN journal_entries j ON j.id = p.journal_entry_id
                    {where}
                    GROUP BY p.journal_entry_id, p.direction, p.account_name HAVING count > 1
                )""",  # noqa: S608
            params,
        ).fetchone()[0]
        return {
            "balanced": not imbalanced and not bad_counts and duplicate_postings == 0,
            "journal_entry_count": len(rows),
            "imbalanced_entry_ids": imbalanced,
            "invalid_posting_count_entry_ids": bad_counts,
            "duplicate_posting_groups": duplicate_postings,
        }

    def correction_audit(self, transaction_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """SELECT changed_at, changes_json FROM transaction_corrections
               WHERE transaction_id = ? ORDER BY changed_at, id""",
            (transaction_id,),
        ).fetchall()
        return [
            {"changed_at": row["changed_at"], "changes": json.loads(row["changes_json"])}
            for row in rows
        ]
