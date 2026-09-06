# M00/M01 Execution Plan

## Planning decision

This plan converts only `WP-0001..WP-0004` and `WP-0101..WP-0104`. It does not authorize M02–M12, full ledger/import support, or any Live Trading path. The immutable authority is `wealthpilot-arch@4ad0b9fa6f3b4a20a8f3ea480724c2fbe3098c14`; Architecture `main` must not be substituted.

`merge_order` in the registry is a merge wave, not permission to bypass dependencies. Within a wave, only tasks with satisfied dependencies may merge. Every branch rebases on the producer commit it declares; no consumer branch may add a public field, enum, event or error code.

## Batch 0 — Candidate First Execution Batch (pending re-review)

These are the only tasks currently `READY` by Definition of Ready. `READY` is not execution authorization: the Technical Director's `CHANGES_REQUIRED` decision remains in force until this corrected plan passes re-review.

| Task | Owner | Branch suggestion | Reviewer | Why safe now |
|---|---|---|---|---|
| `M00-WP0001-T01` | Stream A repository-root owner | `task/m00-wp0001-t01-repo-bootstrap` | Stream C | Addendum explicitly authorizes repository/bootstrap implementation; it is the sole root-manifest branch. |
| `M00-WP0002-T01` | Stream A contract-fixture owner | `task/m00-wp0002-t01-contract-fixtures` | Stream D | Addendum §8.2 explicitly authorizes Walking Skeleton contract fixtures; the task edits only fixture paths. |
| `M01-WP0104-T01` | Stream B fixture producer | `task/m01-wp0104-t01-synthetic-oracle` | Stream A contracts | It freezes synthetic test data/internal CSV layout against already-approved public payloads and writes no production or contract code. |

After Technical Director authorization, three Developer Agents can safely start in parallel. Their write sets are disjoint: root manifests, contract fixtures, and synthetic/oracle fixtures. Before that authorization, no Developer Agent starts implementation. The two Platform-labelled tasks must still be treated as separate temporary owner lanes; only `M00-WP0001-T01` may edit root manifests, and only `M00-WP0002-T01` may define the canonical contract fixture corpus.

Merge order for Batch 0:

1. Merge `M00-WP0002-T01` after Stream D verifies every valid/invalid fixture against the exact schema hash.
2. Merge `M01-WP0104-T01` after the contracts reviewer verifies no public field was invented and the oracle balances.
3. Merge `M00-WP0001-T01` after Stream C repeats frozen installs and negative baseline checks. It may merge first operationally if ready; no downstream task starts until its checks pass.

## Batch 1 — Repository completion

| Task | Start condition | Integration result |
|---|---|---|
| `M00-WP0001-T02` | `M00-WP0001-T01` merged | Completes WP-0001 and opens the general M00 dependency gate. |

This batch remains single-owner because it still touches bootstrap/repository-boundary documentation. No other agent edits root manifests.

## Batch 2 — M00 parallel foundations

Start after `M00-WP0001-T02`, while consuming the already-merged Batch 0 fixtures:

| Parallel lane | Tasks | Merge order |
|---|---|---|
| Contract/kernel | `M00-WP0002-T02` | Kernel values first. |
| Runtime | `M00-WP0003-T01` | Compose core only. |
| Architecture quality | `M00-WP0004-T02` | Static rules and planted failures. |

Integration point: kernel tests, Compose health and architecture tests all pass independently. No CI workflow is edited yet.

## Batch 3 — Contract producer, runtime configuration, safe observability

| Parallel lane | Tasks | Dependencies/merge notes |
|---|---|---|
| Contract producer | `M00-WP0002-T03` | After kernel and canonical fixtures; sole `contracts/` owner. |
| Runtime configuration | `M00-WP0003-T02` | After Compose; no secret values. |
| Observability | `M00-WP0004-T03` | After kernel plus architecture tests; no Privacy Gate implementation. |

The contract producer must merge before any generated client, API, Harness or Wealth consumer.

## Batch 4 — Code generation and persistence baseline

| Parallel lane | Tasks | Merge notes |
|---|---|---|
| Contract generation | `M00-WP0002-T04` | Generates TypeScript and the unique OpenAPI component snapshot. |
| Migration coordinator | `M00-WP0003-T03` | Sole owner of Alembic `env.py`; creates no domain tables. |
| Runtime verification | `M00-WP0003-T04` | Starts only after Compose, config and Alembic are merged. |

`M00-WP0002-T05` follows code generation and produces the cross-language conformance gate.

## Batch 5 — M00 blocking gates

1. `M00-WP0002-T05` — contract conformance.
2. `M00-WP0004-T01` — root CI wiring after the commands exist.
3. `M00-WP0004-T04` — clean-environment M00 certification after contract, runtime, CI, architecture and observability gates are green.

M01 production tasks remain dependency-blocked until `M00-WP0004-T04` merges. Static fixtures from Batch 0 are the only approved exception because Addendum §8.2 authorizes them directly.

## Batch 6 — M01 parallel producers

After M00 certification, allocate independent worktrees to these lanes:

| Lane | Initial task | Follow-on task(s) | Owned core |
|---|---|---|---|
| Gateway | `M01-WP0101-T01` | `T02`, then `T03`, then `T04` | `platform/model_gateway` and model adapters |
| Privacy | `M01-WP0102-T01` | `T02`; `T03` waits for Gateway `T04` | `platform/privacy` |
| Harness/runtime | `M01-WP0103-T01` | `T02` in Stream C; `T03` waits for Gateway/Privacy | `platform/harness`, then platform persistence |
| Wealth | `M01-WP0104-T02` and `T03` in separate branches | `T04` in Stream C after ledger + Harness persistence | wealth parser, ledger/snapshot, wealth persistence |

Producer-first order is mandatory:

```text
accepted schema → canonical fixture → contract producer → domain/runtime producer → API/SSE consumer → Web consumer
```

The parser and ledger branches may run concurrently because they share only immutable inputs and own different subtrees. `M01-WP0104-T04` is created by the migration coordinator and reviewed by the ledger owner; the ledger branch must not create its own migration.

## Batch 7 — Gateway, Privacy and Harness convergence

Merge in this dependency order:

1. Gateway: `M01-WP0101-T02 → T03 → T04`.
2. Privacy: `M01-WP0102-T01 → T02`, then `T03` after Gateway `T04`.
3. Harness: `M01-WP0103-T01 → T02`; `T03` after Gateway `T04` and Privacy `T03`; then `T04 → T05`.
4. Wealth persistence: `M01-WP0104-T04` after Harness persistence and ledger domain.

The integration green point is:

- Fake and mock-HTTP provider contract tests pass;
- Privacy Gate has a zero-leak report;
- Harness survives restart/duplicate delivery with no repeated side effect;
- wealth persistence commits/rolls back atomically.

## Batch 8 — Walking Skeleton producer integration

`M01-WP0104-T05` is the single producer-side vertical orchestration task. It starts only after Gateway, Privacy, Harness worker, parser, ledger and persistence tasks are merged.

Its merge gate requires:

- five frozen Task types and approved state transitions;
- privacy-minimized model classification only;
- immutable preview plus checkpoint before waiting for input;
- exact preview version/hash confirmation;
- balanced ledger and persisted FinancialSnapshot before `run.completed`.

No API or Web branch may compensate for an incomplete producer.

## Batch 9 — Serial consumers

The consumer path is intentionally serialized:

1. `M01-WP0104-T06` — FastAPI operations and runtime conformance against the contract-owner OpenAPI snapshot.
2. `M01-WP0104-T07` — SSE replay/live handoff consuming the persisted Event registry.
3. `M01-WP0104-T08` — generated-client Web UI consuming API and SSE.

This serialization protects the frozen OpenAPI snapshot and prevents Web/SSE teams from guessing producer behavior.

## Batch 10 — Walking Skeleton integration and exit

1. `M01-WP0104-T09` runs `happy_path_import_to_snapshot` and `unconfirmed_import_has_no_financial_effect` through the browser.
2. `M01-WP0104-T10` runs duplicate-file, exact preview-error mapping, privacy and invalid-model gates. Old version is `409/IMPORT_PREVIEW_VERSION_MISMATCH`; tampered hash is `409/IMPORT_PREVIEW_HASH_MISMATCH`; empty/conflicted/pending-confirmation preview is `422/IMPORT_PREVIEW_NOT_COMMIT_ELIGIBLE`. Invalid model output terminates with `MODEL_STRUCTURED_OUTPUT_INVALID`, `retryable=false`, `run.failed`, no downstream Artifact/financial effect and no M01 manual-input or preview-revision path.
3. `M01-WP0104-T11` runs worker-restart and SSE-resume gates, then publishes `m01-conformance.json`.

M01 exits only when the Handoff's eight E2E tests, contract/integration/privacy/architecture suites and quantitative gates all pass without real data or cloud keys.

## Architecture-blocked side branch

`M01-WP0101-T05` remains `BLOCKED_BY_ARCHITECTURE` because `GET /api/v1/model-gateway/health` has a path but no frozen response/error field schema. It is not a Walking Skeleton dependency. To unblock it:

1. Architect publishes an additive contract/schema at an immutable commit.
2. Implementation baseline records that contract version.
3. Contract fixture and generated OpenAPI tasks are created/updated by the contract owner.
4. `M01-WP0104-T06` must already be merged; this is a hard dependency that serializes `/apps/api` ownership under the same Stream D owner.
5. Only then may the endpoint task become `READY`.

Parser-to-public error mapping is also closed: empty file is `422/VALIDATION_FILE_EMPTY`, unsupported type is `422/VALIDATION_FILE_TYPE_UNSUPPORTED`, and only Addendum-covered JSON/field/enum/UTC/Money violations use `400/VALIDATION_REQUEST_INVALID`. Encoding, bounds or malformed CSV failures outside those triggers remain internal parser failures until Architecture freezes a public mapping; T06 must not invent or broaden an ErrorResponse code.

## Merge discipline

- One task, one short-lived branch/worktree, one implementation owner.
- Contract, root, Compose, Alembic `env.py`, OpenAPI and root CI owners are unique.
- A branch modifies only `owned_paths` plus explicitly listed `allowed_paths`; any other need returns to the Planner as a change task.
- A reviewer must rerun the task's required tests from a clean checkout and verify the exact architecture/schema hash.
- Squash merge in the registry's dependency order; after each producer merge, consumers rebase and regenerate rather than copying types.
- Defects found by integration tasks return to the owning task/branch; integration branches do not patch core files.
