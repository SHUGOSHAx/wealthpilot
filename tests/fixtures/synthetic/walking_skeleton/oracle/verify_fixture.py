#!/usr/bin/env python3
"""Verify the deterministic M01 synthetic fixture without production imports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


EXPECTED_SCHEMA_SHA256 = "5b22d0a3e668244896483132d795794687b4b90379228c5815c0f32a1f7a1577"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SchemaFailure(AssertionError):
    pass


def validate(instance: Any, schema: dict[str, Any], root: dict[str, Any], path: str = "$") -> None:
    """Validate the Draft 2020-12 keywords used by the three selected defs."""
    if "$ref" in schema:
        prefix = "#/$defs/"
        ref = schema["$ref"]
        if not ref.startswith(prefix):
            raise SchemaFailure(f"{path}: unsupported reference {ref}")
        validate(instance, root["$defs"][ref[len(prefix):]], root, path)
        return

    if "oneOf" in schema:
        matches = 0
        for candidate in schema["oneOf"]:
            try:
                validate(instance, candidate, root, path)
                matches += 1
            except SchemaFailure:
                pass
        if matches != 1:
            raise SchemaFailure(f"{path}: expected exactly one oneOf match, got {matches}")
        return

    expected_type = schema.get("type")
    checks = {
        "object": lambda value: isinstance(value, dict),
        "array": lambda value: isinstance(value, list),
        "string": lambda value: isinstance(value, str),
        "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
        "boolean": lambda value: isinstance(value, bool),
        "null": lambda value: value is None,
    }
    if expected_type and (expected_type not in checks or not checks[expected_type](instance)):
        raise SchemaFailure(f"{path}: expected {expected_type}, got {type(instance).__name__}")
    if "const" in schema and instance != schema["const"]:
        raise SchemaFailure(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaFailure(f"{path}: {instance!r} is outside the closed enum")

    if isinstance(instance, dict):
        properties = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(instance)
        if missing:
            raise SchemaFailure(f"{path}: missing required fields {sorted(missing)}")
        if schema.get("additionalProperties") is False:
            extra = set(instance) - set(properties)
            if extra:
                raise SchemaFailure(f"{path}: undeclared fields {sorted(extra)}")
        for key, value in instance.items():
            if key in properties:
                validate(value, properties[key], root, f"{path}.{key}")
    elif isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            raise SchemaFailure(f"{path}: too few items")
        if "items" in schema:
            for index, value in enumerate(instance):
                validate(value, schema["items"], root, f"{path}[{index}]")
    elif isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            raise SchemaFailure(f"{path}: string shorter than minLength")
        if len(instance) > schema.get("maxLength", len(instance)):
            raise SchemaFailure(f"{path}: string longer than maxLength")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            raise SchemaFailure(f"{path}: value does not match {schema['pattern']!r}")
        if schema.get("format") == "uuid":
            try:
                parsed = uuid.UUID(instance)
            except ValueError as error:
                raise SchemaFailure(f"{path}: invalid UUID") from error
            if str(parsed) != instance:
                raise SchemaFailure(f"{path}: UUID is not canonical lowercase")
        elif schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(instance.replace("Z", "+00:00"))
            except ValueError as error:
                raise SchemaFailure(f"{path}: invalid RFC 3339 timestamp") from error
    elif isinstance(instance, int) and not isinstance(instance, bool):
        if instance < schema.get("minimum", instance):
            raise SchemaFailure(f"{path}: value is below minimum")


def money(value: dict[str, str]) -> Decimal:
    assert value["currency"] == "CNY"
    return Decimal(value["amount"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", type=Path, required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[5]
    oracle_dir = Path(__file__).resolve().parent
    bank_dir = oracle_dir.parent / "bank"
    privacy_dir = repo / "tests/fixtures/security/privacy/walking_skeleton"

    assert sha256(args.schema) == EXPECTED_SCHEMA_SHA256, "architecture schema hash drift"
    schema = json.loads(args.schema.read_text(encoding="utf-8"))

    manifest = json.loads((oracle_dir / "fixture_manifest.json").read_text(encoding="utf-8"))
    assert manifest["architecture_schema_sha256"] == EXPECTED_SCHEMA_SHA256
    for relative_path, expected_hash in manifest["files"].items():
        assert sha256(repo / relative_path) == expected_hash, f"fixture hash drift: {relative_path}"

    source = bank_dir / "generic_bank.csv"
    duplicate = bank_dir / "generic_bank.duplicate.csv"
    assert source.read_bytes() == duplicate.read_bytes(), "duplicate fixture is not byte-identical"
    source_hash = f"sha256:{sha256(source)}"

    request = json.loads((oracle_dir / "import_request.json").read_text(encoding="utf-8"))
    preview = json.loads((oracle_dir / "import_preview.json").read_text(encoding="utf-8"))
    snapshot = json.loads((oracle_dir / "financial_snapshot.json").read_text(encoding="utf-8"))
    ledger = json.loads((oracle_dir / "ledger_oracle.json").read_text(encoding="utf-8"))
    for name, payload in (("ImportRequest", request), ("ImportPreview", preview), ("FinancialSnapshot", snapshot)):
        validate(payload, schema["$defs"][name], schema)

    assert preview["source_file_reference"]["source_hash"] == source_hash
    assert preview["metadata"]["content_hash"] == preview["preview_hash"]
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == len(preview["items"])
    for csv_row, item in zip(rows, preview["items"]):
        assert csv_row["occurred_at"] == item["occurred_at"]
        assert csv_row["direction"] == item["direction"]
        assert Decimal(csv_row["amount"]) == money(item["amount"])
        assert csv_row["currency"] == item["amount"]["currency"]
        assert csv_row["description"] == item["description"]

    summary = preview["summary"]
    statuses = {status: 0 for status in ("READY", "NEEDS_CONFIRMATION", "SKIPPED", "CONFLICT")}
    inflow = Decimal("0")
    outflow = Decimal("0")
    for item in preview["items"]:
        statuses[item["status"]] += 1
        if item["status"] != "SKIPPED":
            if item["direction"] == "INFLOW":
                inflow += money(item["amount"])
            else:
                outflow += money(item["amount"])
    assert summary["total_count"] == len(preview["items"]) == sum(statuses.values())
    assert summary["ready_count"] == statuses["READY"]
    assert summary["needs_confirmation_count"] == statuses["NEEDS_CONFIRMATION"]
    assert summary["skipped_count"] == statuses["SKIPPED"]
    assert summary["conflict_count"] == statuses["CONFLICT"]
    assert money(summary["inflow_total"]) == inflow
    assert money(summary["outflow_total"]) == outflow
    assert preview["commit_eligible"] is (len(preview["items"]) > 0 and statuses == {"READY": len(preview["items"]), "NEEDS_CONFIRMATION": 0, "SKIPPED": 0, "CONFLICT": 0})

    debit_total = Decimal("0")
    credit_total = Decimal("0")
    target_balance = Decimal(ledger["opening_balance"])
    posting_count = 0
    for entry in ledger["entries"]:
        entry_debit = sum((Decimal(p["amount"]) for p in entry["postings"] if p["side"] == "DEBIT"), Decimal("0"))
        entry_credit = sum((Decimal(p["amount"]) for p in entry["postings"] if p["side"] == "CREDIT"), Decimal("0"))
        assert entry_debit == entry_credit, f"unbalanced entry: {entry['journal_entry_id']}"
        debit_total += entry_debit
        credit_total += entry_credit
        posting_count += len(entry["postings"])
        for posting in entry["postings"]:
            if posting["account"] == "TARGET_BANK_ASSET":
                target_balance += Decimal(posting["amount"]) * (1 if posting["side"] == "DEBIT" else -1)
    expected = ledger["expected"]
    assert len(ledger["entries"]) == expected["journal_entry_count"]
    assert posting_count == expected["posting_count"] == snapshot["calculation_metadata"]["posting_count"]
    assert debit_total == credit_total == Decimal(expected["debit_total"]) == Decimal(expected["credit_total"])
    assert target_balance == Decimal(expected["target_account_ending_balance"])

    assets = sum((money(position["value"]) for position in snapshot["assets"]), Decimal("0"))
    liabilities = sum((money(position["value"]) for position in snapshot["liabilities"]), Decimal("0"))
    assert assets == money(snapshot["total_assets"])
    assert liabilities == money(snapshot["total_liabilities"])
    assert assets - liabilities == money(snapshot["net_worth"]) == target_balance
    assert money(snapshot["account_balances"][0]["balance"]) == target_balance

    canary_manifest = json.loads((privacy_dir / "canary_manifest.json").read_text(encoding="utf-8"))
    canary_text = (privacy_dir / canary_manifest["source_file"]).read_text(encoding="utf-8")
    public_oracles = json.dumps([request, preview, snapshot], ensure_ascii=False)
    for canary in canary_manifest["canaries"]:
        assert canary["raw_value"] in canary_text
        assert canary["raw_value"] not in public_oracles
        assert canary["must_not_cross_model_gateway"] is True
        assert canary["safe_alias"].startswith("SYNTHETIC_")

    print("M01-WP0104-T01 fixture verification passed")
    print(f"  schema sha256: {EXPECTED_SCHEMA_SHA256}")
    print(f"  source sha256: {source_hash}")
    print(f"  rows: {len(rows)}, postings: {posting_count}")
    print(f"  debit = credit: {debit_total} CNY")
    print(f"  snapshot net worth: {target_balance} CNY")
    print(f"  privacy canaries: {len(canary_manifest['canaries'])}")


if __name__ == "__main__":
    main()
