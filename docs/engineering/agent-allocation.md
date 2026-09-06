# M00/M01 Agent Allocation

## Allocation rules

Agent count changes throughput, not ownership or dependencies. Each task still has one owner, one reviewer and one worktree. An Agent temporarily assigned to a Stream follows that task's Stream ownership; it does not gain permission to edit another Stream's core files.

Execution authorization is currently pending Technical Director re-review. The three task-level `READY` entries are candidate assignments only; no Developer Agent starts implementation while the `CHANGES_REQUIRED` decision remains active.

Permanent exclusive surfaces:

- Repository-root manifests, `kernel/`, `contracts/`, OpenAPI snapshots and root CI: designated Stream A sub-owner only.
- Compose core and Alembic `env.py`: designated Stream C coordinator only.
- Wealth ledger/domain: designated Stream B owner only.
- FastAPI composition, SSE, Web and vertical E2E: designated Stream D owner/integrator only.

No allocation allows two live branches to edit the same exclusive surface.

## Three Developer Agents

### Stable assignment

| Agent | Primary assignment | Secondary/review duty |
|---|---|---|
| Agent 1 | Stream A Platform: root, kernel/contracts, CI, Gateway, Privacy, Harness | Reviews Stream B deterministic boundaries; never reviews own Platform task. |
| Agent 2 | Stream B Wealth: synthetic oracle, parser, ledger/snapshot, import workflow | Product/contract consumer review where it did not author fixtures. |
| Agent 3 | Combined Stream C + D: Compose, config, migrations/persistence, Worker; later API/SSE/Web/E2E | Reviews root/runtime assumptions; Stream A reviews its public consumers. |

### Candidate Batch 0 (pending Technical Director authorization)

All three can start in parallel only after the corrected plan passes Technical Director re-review:

| Agent | Task | Temporary lane |
|---|---|---|
| Agent 1 | `M00-WP0001-T01` | Stream A repository-root owner |
| Agent 2 | `M01-WP0104-T01` | Stream B fixture producer |
| Agent 3 | `M00-WP0002-T01` | Temporary Stream A contract-fixture lane; fixture paths only |

Review rotation:

- Agent 3 reviews Agent 1 as Stream C.
- Agent 1 reviews Agent 2 as contracts owner.
- Agent 2 reviews Agent 3's fixture payloads as a consumer; if a formal Stream D sign-off is required, Agent 2 performs that review role for this task only.

The temporary contract-fixture assignment ends after merge. Agent 3 then returns to C+D and may not edit `contracts/` or OpenAPI snapshots.

### Execution shape

- Agent 1 is the bottleneck on `Contract → Gateway/Privacy/Harness`; do not run multiple Platform-core tasks concurrently in its worktree.
- Agent 2 can prepare parser and ledger in separate sequential tasks as soon as kernel/contracts merge, then owns the producer workflow.
- Agent 3 runs Runtime in M00/M01, then switches to Product Integration only after persistence/worker tasks merge. This prevents the same Agent from concurrently editing migration and API composition.
- For `M01-WP0104-T04`, Agent 3 owns the migration and Agent 2 reviews domain mapping.
- For `M01-WP0104-T09/T10/T11`, Agent 3 integrates; Agents 1 and 2 review privacy/harness and financial evidence respectively.

Expected trade-off: the plan is safe but the Platform critical path is mostly serial. Do not hide that constraint by letting Agent 2/3 patch `kernel/`, `contracts/`, Harness or Gateway.

## Four Developer Agents

### Stable assignment

| Agent | Assignment | Core tasks |
|---|---|---|
| Agent A | Stream A Platform | WP-0001/0002/0004, WP-0101/0102/0103 Platform core |
| Agent B | Stream B Wealth | WP-0104 fixture/parser/ledger/workflow producer |
| Agent C | Stream C Runtime/Persistence | WP-0003, Harness/wealth persistence, Celery worker |
| Agent D | Stream D Product Integration | API, SSE, Web and vertical E2E |

### Candidate Batch 0 (pending Technical Director authorization)

- Agent A owns `M00-WP0001-T01`.
- Agent B owns `M01-WP0104-T01`.
- Agent D temporarily executes `M00-WP0002-T01` in the contract-fixture lane, with Agent A as semantic reviewer and Agent B as downstream-consumer reviewer. Because the registry names Stream D as the formal reviewer for that task, final approval must come from a reviewer other than the author; Agent C can perform the Stream D review role after checking the sequence/idempotency cases.
- Agent C uses the remaining time for read-only preparation only; `M00-WP0003-T01` remains dependency-blocked until WP-0001 completes.

### Execution shape

- M00: A runs contract/quality, C runs runtime, B remains available for oracle review, D prepares no production consumer until contracts merge.
- M01: A can serialize Gateway, Privacy and Harness core while C owns persistence/worker, B owns Wealth producers, and D owns consumers.
- The strongest parallel point is after M00 certification: A (Gateway/Privacy/Harness core), B (parser/ledger), C (Harness persistence/Worker), and D (test harness preparation against frozen fixtures). D still cannot implement consumer behavior before its producer dependencies merge.

Expected trade-off: clean Stream separation and straightforward reviews, but Gateway/Privacy/Harness share one Platform Agent and remain partially serial.

## Five Developer Agents

### Stable assignment

| Agent | Assignment | Exclusive ownership |
|---|---|---|
| Agent A1 | Stream A repository/kernel/contracts/CI owner | Root manifests, `kernel/`, `contracts/`, OpenAPI, root CI |
| Agent A2 | Stream A Gateway/Privacy/Harness implementation owner | `platform/model_gateway`, `platform/privacy`, `platform/harness` (not root/contracts) |
| Agent B | Stream B Wealth owner | Wealth parser, ledger/snapshot, application workflow |
| Agent C | Stream C Runtime/Persistence coordinator | Compose, config, Alembic `env.py`, migrations, persistence, Worker |
| Agent D | Stream D Product integrator | FastAPI, SSE, Web and E2E |

### Candidate Batch 0 (pending Technical Director authorization)

- A1: `M00-WP0001-T01`.
- A2: `M00-WP0002-T01` as contract-fixture owner, reviewed by D.
- B: `M01-WP0104-T01`, reviewed by A1.
- C and D do read-only preparation until their dependencies become satisfied; they do not start blocked implementation tasks.

### Execution shape

- A1 completes repository, contracts and quality gates; A2 begins Gateway/Privacy/Harness only after M00 certification.
- A1 reviews A2's public-boundary and architecture conformance; A2 reviews A1 only where it did not author the underlying contract/root surface.
- B and C split domain semantics from SQL migrations: B owns ports/domain; C owns mappings/revisions.
- D begins API only after `M01-WP0104-T05`, then owns the serial API→SSE→Web→E2E path.
- During M01 integration, A2 is Harness/Gateway/Privacy reviewer, B is deterministic finance reviewer, C is transaction/restart reviewer and D is integrator. No Agent approves its own task.

Expected trade-off: best throughput without increasing core-file collisions. A fifth Agent is useful only because Stream A is split into two explicitly non-overlapping sub-owners; adding more agents to the same root/contracts/Harness files would reduce safety.

## Review matrix

| Produced surface | Required independent review |
|---|---|
| Root/baseline/locks | Stream C reproducibility and supply-chain review |
| Contract fixtures/models/OpenAPI | Stream D consumer review; Stream B review for wealth payload invariants |
| Kernel Money/time/hash | Stream B deterministic finance review |
| Compose/config/migrations | Stream A security/architecture review; owning domain reviews mapping semantics |
| Gateway/Privacy/Harness | Stream D integration review plus Stream A security reviewer distinct from author where possible |
| Wealth parser/ledger/snapshot/workflow | Stream A privacy/contracts review and Stream C persistence review |
| API/SSE/Web | Stream A contract review and Stream B business-output review |
| Walking Skeleton E2E (`T09..T11`) | Stream A privacy/harness, Stream B financial oracle, Stream C transaction/restart |

## Branch/worktree convention

Use `task/<lowercase-task-id>-<short-slug>`, for example:

```text
task/m00-wp0001-t01-repo-bootstrap
task/m01-wp0101-t04-gateway-policy
task/m01-wp0104-t05-import-workflow
```

Each worktree starts from the exact merge commit satisfying all listed dependencies. Draft work on a blocked task is not merge-authorized and must not invent missing inputs. `M01-WP0101-T05` must not receive an implementation branch until Architecture freezes the public health response contract.
