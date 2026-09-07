"""Command-line wrapper for verified local database backup and restore."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .backup import backup_database, restore_database
from .sqlite_wealth import default_database_path


def main() -> None:
    parser = argparse.ArgumentParser(prog="wealthpilot-db")
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("source", nargs="?")
    backup.add_argument("destination", nargs="?")
    restore = commands.add_parser("restore")
    restore.add_argument("backup")
    restore.add_argument("target", nargs="?")
    restore.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.command == "backup":
        source = Path(args.source).expanduser() if args.source else default_database_path()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = (
            Path(args.destination).expanduser()
            if args.destination
            else source.parent / "backups" / f"wealthpilot-{stamp}.wpbackup"
        )
        result = backup_database(source, destination)
    else:
        target = Path(args.target).expanduser() if args.target else default_database_path()
        safety = None
        if target.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            safety = target.parent / "backups" / f"pre-restore-{stamp}.wpbackup"
            backup_database(target, safety)
        result = restore_database(args.backup, target, overwrite=args.overwrite or target.exists())
        result["safety_backup"] = str(safety) if safety else None
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
