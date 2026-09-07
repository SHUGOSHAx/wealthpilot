"""Local persistence for immutable research decisions and snapshot references."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sqlite_wealth import SQLiteWealthService, default_database_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class SQLiteResearchStore:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = database_path or default_database_path()
        # Reuse the migration authority before opening this adapter connection.
        with SQLiteWealthService(self.database_path):
            pass
        self._connection = sqlite3.connect(str(self.database_path), timeout=30)
        self._connection.row_factory = sqlite3.Row

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteResearchStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def save(
        self,
        *,
        query: str,
        snapshot: dict[str, Any],
        memo: dict[str, Any],
        risk: dict[str, Any],
    ) -> dict[str, Any]:
        record_id = str(uuid.uuid4())
        created_at = _now()
        snapshot_json = _canonical(snapshot)
        self._connection.execute(
            """INSERT INTO research_records
               (id, query, symbol, snapshot_content_sha256, snapshot_as_of,
                provider, provider_as_of, memo_json, risk_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record_id,
                query,
                memo["symbol"],
                hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest(),
                snapshot["as_of"],
                memo["data_provider"],
                memo["as_of"],
                _canonical(memo),
                _canonical(risk),
                created_at,
            ),
        )
        self._connection.commit()
        return {
            "research_id": record_id,
            "query": query,
            "snapshot_reference": {
                "content_sha256": hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest(),
                "as_of": snapshot["as_of"],
            },
            "memo": {**memo, **risk},
            "created_at": created_at,
        }

    def history(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM research_records ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
        return [
            {
                "research_id": row["id"],
                "query": row["query"],
                "snapshot_reference": {
                    "content_sha256": row["snapshot_content_sha256"],
                    "as_of": row["snapshot_as_of"],
                },
                "memo": {**json.loads(row["memo_json"]), **json.loads(row["risk_json"])},
                "created_at": row["created_at"],
            }
            for row in rows
        ]
