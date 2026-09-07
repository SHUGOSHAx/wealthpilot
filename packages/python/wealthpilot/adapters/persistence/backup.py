"""Verified SQLite backup and restore helpers."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def database_digest(database_path: str | Path) -> str:
    """Hash logical schema and row content deterministically."""

    path = Path(database_path).expanduser().resolve()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("database integrity check failed")
        digest = hashlib.sha256()
        tables = connection.execute(
            """SELECT name, sql FROM sqlite_master
               WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"""
        ).fetchall()
        for table_name, schema_sql in tables:
            columns = [row[1] for row in connection.execute(f"PRAGMA table_info({_quote(table_name)})")]
            order = ", ".join(_quote(column) for column in columns)
            rows = connection.execute(
                f"SELECT * FROM {_quote(table_name)} ORDER BY {order}"  # noqa: S608
            ).fetchall()
            digest.update(
                json.dumps(
                    [table_name, schema_sql, columns, rows],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
        return digest.hexdigest()
    finally:
        connection.close()


def backup_database(source_path: str | Path, backup_path: str | Path) -> dict[str, Any]:
    source = Path(source_path).expanduser().resolve()
    destination = Path(backup_path).expanduser().resolve()
    if source == destination:
        raise ValueError("backup path must differ from source path")
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_connection = sqlite3.connect(str(source))
    destination_connection = sqlite3.connect(str(destination))
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()
    os.chmod(destination, 0o600)
    source_digest = database_digest(source)
    backup_digest = database_digest(destination)
    if source_digest != backup_digest:
        raise RuntimeError("backup equivalence verification failed")
    return {"source": str(source), "backup": str(destination), "digest": backup_digest, "verified": True}


def restore_database(
    backup_path: str | Path, target_path: str | Path, *, overwrite: bool = False
) -> dict[str, Any]:
    source = Path(backup_path).expanduser().resolve()
    target = Path(target_path).expanduser().resolve()
    if source == target:
        raise ValueError("restore target must differ from backup path")
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.exists() and not overwrite:
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        backup_connection = sqlite3.connect(str(source))
        target_connection = sqlite3.connect(str(temporary))
        try:
            backup_connection.backup(target_connection)
        finally:
            target_connection.close()
            backup_connection.close()
        expected = database_digest(source)
        actual = database_digest(temporary)
        if expected != actual:
            raise RuntimeError("restore equivalence verification failed")
        os.replace(temporary, target)
        os.chmod(target, 0o600)
        return {"backup": str(source), "target": str(target), "digest": actual, "verified": True}
    finally:
        temporary.unlink(missing_ok=True)
