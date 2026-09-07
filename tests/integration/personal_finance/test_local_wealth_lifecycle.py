from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from wealthpilot.adapters.persistence import (
    SQLiteWealthService,
    backup_database,
    database_digest,
    restore_database,
)
from wealthpilot.adapters.persistence.migrations import MIGRATIONS

BASE_HEADER = "record_type,date,account,account_type,category,description,amount,currency,liquid"
ID_HEADER = BASE_HEADER + ",source_transaction_id"


def document(*rows: str, with_ids: bool = False) -> bytes:
    return ("\n".join((ID_HEADER if with_ids else BASE_HEADER, *rows)) + "\n").encode()


BALANCE = "BALANCE,2026-09-01,Cash,ASSET,,Current balance,10000.00,CNY,true"


class LocalWealthLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "wealthpilot.db"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def count(self, table: str) -> int:
        connection = sqlite3.connect(self.database)
        try:
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            connection.close()

    def test_preview_correction_confirmation_and_idempotent_ledger(self) -> None:
        raw = document(
            BALANCE,
            "TRANSACTION,2026-09-02,Cash,ASSET,EXPENSE,Coffee shop,20.00,CNY,true,tx-001",
            "TRANSACTION,2026-09-03,Cash,ASSET,INCOME,Salary,3000.00,CNY,true,tx-002",
            with_ids=True,
        )
        with SQLiteWealthService(self.database) as service:
            self.assertEqual(service.schema_version, 2)
            preview = service.create_import_preview(raw)
            self.assertEqual(preview["status"], "PREVIEW")
            self.assertEqual(self.count("journal_entries"), 0)

            transaction_id = preview["transactions"][0]["transaction_id"]
            corrected = service.correct_transaction(
                preview["batch_id"], transaction_id,
                merchant_normalized="Demo Cafe", is_reimbursement=True,
            )
            self.assertEqual(corrected["transactions"][0]["merchant_normalized"], "Demo Cafe")
            self.assertTrue(corrected["transactions"][0]["flags"]["reimbursement"])
            self.assertEqual(len(service.correction_audit(transaction_id)), 1)

            snapshot = service.confirm_import(preview["batch_id"])
            self.assertEqual(snapshot["cash_flow"]["inflow"]["amount"], "3000.00")
            self.assertEqual(snapshot["cash_flow"]["outflow"]["amount"], "20.00")
            self.assertEqual(snapshot["monthly_expenses"]["amount"], "0.00")
            self.assertEqual(snapshot["assets"]["amount"], "12980.00")
            self.assertTrue(service.reconcile(preview["batch_id"])["balanced"])
            self.assertEqual(self.count("journal_entries"), 2)
            self.assertEqual(self.count("postings"), 4)

            self.assertEqual(service.confirm_import(preview["batch_id"]), snapshot)
            self.assertEqual(self.count("journal_entries"), 2)
            self.assertEqual(self.count("postings"), 4)

    def test_source_id_and_fallback_dedup_support_partial_overlap(self) -> None:
        first = document(
            BALANCE,
            "TRANSACTION,2026-09-02,Cash,ASSET,EXPENSE,A,10.00,CNY,true,one",
            "TRANSACTION,2026-09-03,Cash,ASSET,EXPENSE,B,20.00,CNY,true,two",
            with_ids=True,
        )
        second = document(
            BALANCE.replace("10000.00", "9990.00"),
            "TRANSACTION,2026-09-02,Cash,ASSET,EXPENSE,A changed,11.00,CNY,true,one",
            "TRANSACTION,2026-09-04,Cash,ASSET,EXPENSE,C,30.00,CNY,true,three",
            with_ids=True,
        )
        fallback_first = document(
            BALANCE.replace("10000.00", "9000.00"),
            "TRANSACTION,2026-09-05,Cash,ASSET,EXPENSE,No source id,40.00,CNY,true",
        )
        fallback_second = document(
            BALANCE.replace("10000.00", "8960.00"),
            "TRANSACTION,2026-09-05,Cash,ASSET,EXPENSE,No source id,40.00,CNY,true",
        )
        with SQLiteWealthService(self.database) as service:
            initial = service.create_import_preview(first)
            service.confirm_import(initial["batch_id"])
            partial = service.create_import_preview(second)
            self.assertEqual(partial["overlap"], "PARTIAL_OVERLAP")
            self.assertEqual(partial["duplicate_transaction_count"], 1)
            self.assertEqual(partial["new_transaction_count"], 1)
            partial_snapshot = service.confirm_import(partial["batch_id"])
            self.assertEqual(partial_snapshot["cash_flow"]["outflow"]["amount"], "60.00")

            fallback = service.create_import_preview(fallback_first)
            service.confirm_import(fallback["batch_id"])
            duplicate = service.create_import_preview(fallback_second)
            self.assertEqual(duplicate["overlap"], "DUPLICATE_ONLY")
            self.assertEqual(duplicate["new_transaction_count"], 0)
            self.assertEqual(self.count("journal_entries"), 4)

    def test_latest_balance_observation_advances_with_only_later_transactions(self) -> None:
        first = document(
            "BALANCE,2026-09-01,Cash,ASSET,,Opening balance,1000.00,CNY,true",
            "TRANSACTION,2026-09-02,Cash,ASSET,EXPENSE,Groceries,100.00,CNY,true,one",
            with_ids=True,
        )
        second = document(
            "BALANCE,2026-09-03,Cash,ASSET,,Observed balance,900.00,CNY,true",
            "TRANSACTION,2026-09-04,Cash,ASSET,EXPENSE,Transit,50.00,CNY,true,two",
            with_ids=True,
        )
        with SQLiteWealthService(self.database) as service:
            service.confirm_import(service.create_import_preview(first)["batch_id"])
            snapshot = service.confirm_import(service.create_import_preview(second)["batch_id"])
            self.assertEqual(snapshot["assets"]["amount"], "850.00")
            self.assertEqual(snapshot["cash_flow"]["outflow"]["amount"], "150.00")
            self.assertEqual(snapshot["source"]["confirmed_batch_count"], 2)

    def test_credit_card_refund_and_reimbursement_have_explicit_semantics(self) -> None:
        raw = document(
            "BALANCE,2026-09-01,Card,LIABILITY,,Card balance,500.00,CNY,false",
            "BALANCE,2026-09-01,Cash,ASSET,,Cash balance,1000.00,CNY,true",
            "TRANSACTION,2026-09-02,Card,LIABILITY,EXPENSE,Purchase,100.00,CNY,false,purchase",
            "TRANSACTION,2026-09-03,Cash,ASSET,INCOME,Merchant refund,20.00,CNY,true,refund",
            "TRANSACTION,2026-09-04,Cash,ASSET,EXPENSE,Work expense,30.00,CNY,true,reimburse",
            with_ids=True,
        )
        with SQLiteWealthService(self.database) as service:
            preview = service.create_import_preview(raw)
            refund_id = preview["transactions"][1]["transaction_id"]
            reimbursement_id = preview["transactions"][2]["transaction_id"]
            service.correct_transaction(preview["batch_id"], refund_id, is_refund=True)
            service.correct_transaction(
                preview["batch_id"], reimbursement_id, is_reimbursement=True
            )
            snapshot = service.confirm_import(preview["batch_id"])
            self.assertEqual(snapshot["liabilities"]["amount"], "600.00")
            self.assertEqual(snapshot["assets"]["amount"], "990.00")
            self.assertEqual(snapshot["cash_flow"]["inflow"]["amount"], "20.00")
            self.assertEqual(snapshot["cash_flow"]["outflow"]["amount"], "130.00")
            self.assertEqual(snapshot["monthly_expenses"]["amount"], "80.00")
            connection = sqlite3.connect(self.database)
            direction = connection.execute(
                """SELECT p.direction FROM postings p
                   JOIN journal_entries j ON j.id = p.journal_entry_id
                   WHERE j.transaction_id = ? AND p.account_name = 'Liability:Card'""",
                (preview["transactions"][0]["transaction_id"],),
            ).fetchone()[0]
            connection.close()
            self.assertEqual(direction, "CREDIT")

    def test_confirmed_correction_appends_reversal_and_replacement(self) -> None:
        raw = document(
            BALANCE,
            "TRANSACTION,2026-09-02,Cash,ASSET,EXPENSE,Internal transfer,100.00,CNY,true,move-1",
            with_ids=True,
        )
        with SQLiteWealthService(self.database) as service:
            preview = service.create_import_preview(raw)
            transaction_id = preview["transactions"][0]["transaction_id"]
            first_snapshot = service.confirm_import(preview["batch_id"])
            self.assertEqual(first_snapshot["cash_flow"]["outflow"]["amount"], "100.00")

            connection = sqlite3.connect(self.database)
            original = connection.execute(
                """SELECT p.account_name, p.direction, p.amount FROM postings p
                   JOIN journal_entries j ON j.id = p.journal_entry_id
                   WHERE j.transaction_id = ? AND j.entry_kind = 'ORIGINAL' ORDER BY p.id""",
                (transaction_id,),
            ).fetchall()
            connection.close()

            corrected_snapshot = service.correct_confirmed_transaction(
                preview["batch_id"], transaction_id,
                merchant_normalized="Own account transfer", is_transfer=True,
            )
            self.assertEqual(corrected_snapshot["cash_flow"]["outflow"]["amount"], "0.00")
            self.assertEqual(self.count("journal_entries"), 3)
            self.assertEqual(self.count("postings"), 6)
            self.assertTrue(service.reconcile(preview["batch_id"])["balanced"])
            self.assertEqual(len(service.financial_snapshot_history()), 2)

            connection = sqlite3.connect(self.database)
            unchanged = connection.execute(
                """SELECT p.account_name, p.direction, p.amount FROM postings p
                   JOIN journal_entries j ON j.id = p.journal_entry_id
                   WHERE j.transaction_id = ? AND j.entry_kind = 'ORIGINAL' ORDER BY p.id""",
                (transaction_id,),
            ).fetchall()
            connection.close()
            self.assertEqual(unchanged, original)

            repeated = service.create_import_preview(raw)
            self.assertEqual(repeated["status"], "CONFIRMED")
            self.assertTrue(repeated["transactions"][0]["flags"]["transfer"])
            self.assertEqual(service.confirm_import(repeated["batch_id"]), corrected_snapshot)
            self.assertEqual(self.count("journal_entries"), 3)

    def test_restart_and_verified_backup_restore_preserve_history(self) -> None:
        raw = document(
            BALANCE,
            "TRANSACTION,2026-09-02,Cash,ASSET,INCOME,Salary,3000.00,CNY,true",
        )
        with SQLiteWealthService(self.database) as service:
            preview = service.create_import_preview(raw)
            expected = service.confirm_import(preview["batch_id"])

        with SQLiteWealthService(self.database) as reopened:
            self.assertEqual(reopened.latest_financial_snapshot(), expected)
            self.assertTrue(reopened.reconcile()["balanced"])

        backup = self.root / "backup.db"
        restored = self.root / "restored.db"
        backup_result = backup_database(self.database, backup)
        restore_result = restore_database(backup, restored)
        self.assertTrue(backup_result["verified"])
        self.assertTrue(restore_result["verified"])
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(restored.stat().st_mode & 0o777, 0o600)
        self.assertEqual(database_digest(self.database), database_digest(restored))
        with SQLiteWealthService(restored) as restored_service:
            self.assertEqual(restored_service.latest_financial_snapshot(), expected)

    def test_existing_v1_database_migrates_to_latest_without_data_loss(self) -> None:
        version, name, sql = MIGRATIONS[0]
        connection = sqlite3.connect(self.database)
        connection.executescript(
            """CREATE TABLE schema_migrations (
                   version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL
               );"""
            + sql
        )
        connection.execute(
            "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
            (version, name, "2026-09-01T00:00:00Z"),
        )
        connection.execute(
            """INSERT INTO import_batches
               (id, source_sha256, status, record_count, created_at)
               VALUES ('legacy', 'legacy-hash', 'PREVIEW', 1, '2026-09-01T00:00:00Z')"""
        )
        connection.commit()
        connection.close()

        with SQLiteWealthService(self.database) as service:
            self.assertEqual(service.schema_version, 2)
            row = service._connection.execute(
                "SELECT id, source_kind FROM import_batches WHERE id = 'legacy'"
            ).fetchone()
            self.assertEqual(tuple(row), ("legacy", "GENERIC_CSV"))
            self.assertIsNotNone(
                service._connection.execute(
                    "SELECT name FROM sqlite_master WHERE name = 'research_records'"
                ).fetchone()
            )


if __name__ == "__main__":
    unittest.main()
