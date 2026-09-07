# Personal-Use MVP Waivers

These implementation records do not amend `wealthpilot-arch`. None waives
financial correctness, duplicate posting, privacy red lines, recoverability, or
the prohibition on live side effects.

## MVP-WAIVER-001 — SQLite local persistence

- issue: production topology uses PostgreSQL; personal-use runs one local SQLite file.
- architecture expectation: PostgreSQL owns ledger, snapshots and audit records.
- temporary implementation: SQLite with versioned migrations, foreign keys, WAL,
  full synchronous writes, transactional confirmation and integrity checks.
- reason: single-user local operation with minimal dependencies.
- risk: limited concurrent-write and operational tooling compared with PostgreSQL.
- scope: PERSONAL_LOCAL only.
- must_fix_before: multi-user, distributed worker or production deployment.

## MVP-WAIVER-002 — In-process runtime and private API

- issue: queues, workers, Redis/SSE and frozen Research APIs are not present.
- architecture expectation: separate runtime components and versioned public contracts.
- temporary implementation: one localhost FastAPI process with private
  `/api/v1/personal/*` interfaces.
- reason: reliable local workflow before distributed operation.
- risk: long research calls occupy one request worker and private payloads may evolve.
- scope: PERSONAL_LOCAL only; the API is not a compatibility promise.
- must_fix_before: remote clients or distributed task execution.

## MVP-WAIVER-003 — Local artifact hash projection

- issue: the accepted canonical Artifact hash has an unresolved self-reference.
- architecture expectation: one frozen canonical projection.
- temporary implementation: SHA-256 over raw import bytes and separately over
  canonical JSON snapshot content.
- reason: deterministic integrity and trace support without ambiguous recursion.
- risk: hashes are not interoperable with a future canonical Artifact hash.
- scope: import deduplication, backup verification and local trace only.
- must_fix_before: cross-system artifact exchange, security approval or any live use.

## MVP-WAIVER-004 — Unencrypted local backup container

- issue: the verified SQLite backup is not yet encrypted by the application.
- architecture expectation: encrypted logical backup with Secret Store/Keychain material.
- temporary implementation: consistent SQLite backup, logical digest comparison,
  integrity validation, atomic restore and automatic pre-restore safety backup.
- reason: encryption needs a user-held recovery-secret/Keychain lifecycle; inventing
  one would risk unrecoverable data loss.
- risk: anyone who obtains the `.wpbackup` file can read its contents.
- scope: backups retained on the same trusted personal device only.
- must_fix_before: cloud sync, sharing, removable-media storage or production release.

## MVP-WAIVER-005 — Public provider evidence depth

- issue: BaoStock supplies useful public history and fundamentals but not the full
  authoritative document/page evidence chain.
- architecture expectation: Evidence Ledger with document version, page/block and
  point-in-time availability semantics.
- temporary implementation: provider query IDs, source, as-of, fetched-at, disclosed
  available-at when supplied, quality status and explicit limitations.
- reason: real A-share research is useful before full document ingestion exists.
- risk: provider data may be delayed, revised or incomplete.
- scope: personal research support; never order approval or live trading.
- must_fix_before: high-confidence Decision Memo or production research certification.
