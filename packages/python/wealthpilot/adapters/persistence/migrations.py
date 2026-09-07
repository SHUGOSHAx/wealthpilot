"""Ordered SQLite schema migrations for the local-first wealth store."""

from __future__ import annotations

MIGRATIONS: tuple[tuple[int, str, str], ...] = (
    (
        1,
        "local_personal_finance",
        """
        CREATE TABLE import_batches (
            id TEXT PRIMARY KEY,
            source_sha256 TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL CHECK (status IN ('PREVIEW', 'CONFIRMED')),
            record_count INTEGER NOT NULL CHECK (record_count > 0),
            created_at TEXT NOT NULL,
            confirmed_at TEXT
        );

        CREATE TABLE import_balance_observations (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
            row_number INTEGER NOT NULL,
            observed_on TEXT NOT NULL,
            account_name TEXT NOT NULL,
            account_type TEXT NOT NULL CHECK (account_type IN ('ASSET', 'LIABILITY')),
            amount TEXT NOT NULL,
            currency TEXT NOT NULL CHECK (currency = 'CNY'),
            liquid INTEGER NOT NULL CHECK (liquid IN (0, 1)),
            UNIQUE(batch_id, row_number)
        );

        CREATE TABLE normalized_transactions (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
            row_number INTEGER NOT NULL,
            stable_identity TEXT NOT NULL,
            source_transaction_id TEXT,
            fallback_fingerprint TEXT NOT NULL,
            transaction_date TEXT NOT NULL,
            account_name TEXT NOT NULL,
            account_type TEXT NOT NULL CHECK (account_type IN ('ASSET', 'LIABILITY')),
            original_category TEXT NOT NULL CHECK (original_category IN ('INCOME', 'EXPENSE')),
            category TEXT NOT NULL CHECK (category IN ('INCOME', 'EXPENSE')),
            merchant_original TEXT NOT NULL,
            merchant_normalized TEXT NOT NULL,
            amount TEXT NOT NULL,
            currency TEXT NOT NULL CHECK (currency = 'CNY'),
            liquid INTEGER NOT NULL CHECK (liquid IN (0, 1)),
            is_transfer INTEGER NOT NULL DEFAULT 0 CHECK (is_transfer IN (0, 1)),
            is_refund INTEGER NOT NULL DEFAULT 0 CHECK (is_refund IN (0, 1)),
            is_reimbursement INTEGER NOT NULL DEFAULT 0 CHECK (is_reimbursement IN (0, 1)),
            duplicate_of_transaction_id TEXT REFERENCES normalized_transactions(id),
            duplicate_reason TEXT CHECK (duplicate_reason IN ('SOURCE_ID', 'FINGERPRINT')),
            created_at TEXT NOT NULL,
            UNIQUE(batch_id, row_number)
        );

        CREATE INDEX idx_normalized_transactions_identity
            ON normalized_transactions(stable_identity);
        CREATE INDEX idx_normalized_transactions_batch
            ON normalized_transactions(batch_id);

        CREATE TABLE transaction_corrections (
            id TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL REFERENCES normalized_transactions(id) ON DELETE CASCADE,
            changed_at TEXT NOT NULL,
            changes_json TEXT NOT NULL
        );

        CREATE TABLE journal_entries (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL REFERENCES import_batches(id),
            transaction_id TEXT NOT NULL REFERENCES normalized_transactions(id),
            entry_date TEXT NOT NULL,
            description TEXT NOT NULL,
            entry_kind TEXT NOT NULL DEFAULT 'ORIGINAL'
                CHECK (entry_kind IN ('ORIGINAL', 'REVERSAL', 'REPLACEMENT')),
            reverses_journal_entry_id TEXT REFERENCES journal_entries(id),
            created_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX idx_journal_original_transaction
            ON journal_entries(transaction_id) WHERE entry_kind = 'ORIGINAL';
        CREATE UNIQUE INDEX idx_journal_revision
            ON journal_entries(reverses_journal_entry_id, entry_kind)
            WHERE reverses_journal_entry_id IS NOT NULL;

        CREATE TABLE postings (
            id TEXT PRIMARY KEY,
            journal_entry_id TEXT NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
            account_name TEXT NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('DEBIT', 'CREDIT')),
            amount TEXT NOT NULL,
            currency TEXT NOT NULL CHECK (currency = 'CNY'),
            UNIQUE(journal_entry_id, direction, account_name)
        );

        CREATE TABLE financial_snapshots (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL REFERENCES import_batches(id),
            revision INTEGER NOT NULL,
            as_of TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(batch_id, revision)
        );

        CREATE INDEX idx_financial_snapshots_as_of
            ON financial_snapshots(as_of, created_at);
        """,
    ),
    (
        2,
        "personal_classification_and_research_history",
        """
        ALTER TABLE import_batches ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'GENERIC_CSV';
        ALTER TABLE import_batches ADD COLUMN source_filename TEXT;
        ALTER TABLE normalized_transactions ADD COLUMN classification TEXT NOT NULL DEFAULT '其他';
        ALTER TABLE import_balance_observations ADD COLUMN asset_class TEXT NOT NULL DEFAULT 'UNKNOWN';

        CREATE TABLE research_records (
            id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            symbol TEXT NOT NULL,
            snapshot_content_sha256 TEXT NOT NULL,
            snapshot_as_of TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_as_of TEXT NOT NULL,
            memo_json TEXT NOT NULL,
            risk_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX idx_research_records_created_at
            ON research_records(created_at);
        """,
    ),
)

LATEST_SCHEMA_VERSION = MIGRATIONS[-1][0]
