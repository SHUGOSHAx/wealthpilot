# MVP Fast Lane Waivers

These waivers are implementation records, not Architecture decisions. They do
not modify `wealthpilot-arch` or authorize production/live behavior.

## MVP-WAIVER-001 — private demo API

The end-to-end research endpoint is implemented under `/api/v1/demo` before a
future public Research contract is frozen. It is local-only, explicitly
unstable, and must not be treated as a public compatibility promise.

## MVP-WAIVER-002 — in-process runtime

API, deterministic wealth calculation, research orchestration, offline Model
Gateway and risk calculation run in one local process. Production queues,
PostgreSQL, Redis, checkpoint recovery and SSE are deferred.

## MVP-WAIVER-003 — cached research

The demo uses versioned cached research facts for a small A-share allowlist. It
does not claim live market data, complete evidence coverage, point-in-time
backtesting or suitability for trading.

## MVP-WAIVER-004 — artifact canonical hash clarification

The accepted Walking Skeleton contract has an unresolved self-reference between
`ImportPreview.preview_hash` and `metadata.content_hash`. The MVP private demo
payload does not claim conformance to that canonical Artifact hash. Source-file
SHA-256 remains deterministic; public-contract certification stays deferred.

## MVP-WAIVER-005 — no durable ledger

The MVP parses a synthetic upload and calculates an immutable response in
memory. Durable double-entry persistence, migrations, reconciliation and resume
semantics remain future work. No model or research component can write
authoritative financial state.
