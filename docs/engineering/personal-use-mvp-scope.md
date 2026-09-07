# Personal-Use MVP Scope

Status: `CHECKPOINTS IMPLEMENTED — REAL PERSONAL FILE VALIDATION REQUIRED`

This record replaces the Demo Fast Lane as the active implementation scope. It
does not amend the Architecture repository or freeze new public contracts.

## MUST_FIX

- Persist private imports, corrections, balanced ledger entries and snapshot
  history across restart.
- Preview and explicitly confirm every import; make file and row-level import
  idempotent, including partial overlap.
- Preserve source identity, hashes, timestamps and immutable correction lineage.
- Provide verified backup/restore before accepting the personal-use milestone.
- Add a real, time-stamped A-share data provider and persist research history.
- Keep model egress minimized and deterministic risk/allocation authoritative.

## MVP_WAIVER

- Use a local SQLite database instead of the production PostgreSQL topology.
- Run API, workflow and UI in one localhost-only process instead of queues and
  independently deployed services.
- Use private `/api/v1/personal/*` application interfaces until the relevant
  public contracts are frozen.
- Use a deterministic, non-self-referential local artifact hash projection for
  integrity and traceability only.

## DEFER

- Multiple concurrent users, distributed workers, Redis/SSE and Qdrant.
- Full evidence-ledger document ingestion, deep multi-agent research and complete
  Architecture certification.
- Paper/live broker integration; the product must retain no live side effects.

## Checkpoints

1. Import → preview → correction → confirm → balanced ledger → persisted snapshot.
2. Daily transactions/overview, duplicate-safe re-import, backup and restore.
3. Real A-share data, structured research and persisted memo history.
4. Historical snapshot-bound deterministic suitability and position constraints.
