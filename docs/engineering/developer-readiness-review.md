# WealthPilot Developer Execution Readiness Review

## Decision

`APPROVED`

AI Developer Team 获准执行本文件列出的首批 Task。授权范围严格限于 M00/M01；所有 `BLOCKED_BY_DEPENDENCY` 与 `BLOCKED_BY_ARCHITECTURE` Task 仍不得开工。

## Review Basis

- Effective Architecture Commit：`4ad0b9fa6f3b4a20a8f3ea480724c2fbe3098c14`
- Architecture Baseline Tag / Commit：`architecture-baseline-1` / `66085f16bf479018dc0e139262eb283f57945bf3`
- Accepted Addendum Tag / Commit：`walking-skeleton-contract-addendum-1` / `4ad0b9fa6f3b4a20a8f3ea480724c2fbe3098c14`
- Walking Skeleton Schema：`1.0.0`
- Schema SHA-256：`5b22d0a3e668244896483132d795794687b4b90379228c5815c0f32a1f7a1577`

复审覆盖 `AGENTS.md`、`ARCHITECTURE_BASELINE`、Implementation Activation、Engineering Handoff、Task Registry、Dependency DAG、Execution Plan 与 Agent Allocation，并对照上述不可变 Architecture Commit、Accepted Addendum 和 Schema Hash。

## Re-review Result

上一轮五项定点问题均已关闭：

1. `M01-WP0104-T10` 已将非法模型输出冻结为 `MODEL_STRUCTURED_OUTPUT_INVALID`、`retryable=false`、`run.failed`，且无下游 Artifact 或财务影响；人工分类、预览修订和恢复路径明确不属于 M01。
2. `M01-WP0104-T10` 已分别冻结旧版本、篡改哈希和不可提交预览的精确 HTTP/ErrorResponse 映射。
3. `M01-WP0104-T06` 已明确只实现六个 non-SSE operation；SSE transport 仍由 T07 独占。
4. `M01-WP0104-T02` 已冻结 Addendum 覆盖的 parser-to-public error mapping；未冻结的 encoding、bounds、malformed CSV 失败保持内部语义，Developer 无权扩写 public error code。
5. `M01-WP0101-T05` 已增加对 `M01-WP0104-T06` 的 hard dependency；Registry、DAG 和 Execution Plan 均规定同一 Stream D owner 串行修改 API surface。T05 继续保持 `BLOCKED_BY_ARCHITECTURE`。

## Readiness Findings

### Scope and Task Readiness

- Registry 共 39 个唯一 Task，仅包含 M00/M01 与 `WP-0001..WP-0004`、`WP-0101..WP-0104`。
- 状态为 3 个 `READY`、35 个 `BLOCKED_BY_DEPENDENCY`、1 个 `BLOCKED_BY_ARCHITECTURE`。
- 三个 `READY` Task 均具有 goal、owned/allowed/forbidden paths、dependencies、input contracts、acceptance criteria、required tests、owner stream 和 reviewer stream。其空 dependency list 表示 root producer，无隐含前置 Task。
- Task ID 与 DAG 节点完全一致；无重复 ID、未知依赖、依赖环或 merge-order 倒置。

### Architecture Compliance

- Contract、public error mapping、schema/version、state/event 与 M01/M02 边界均由 Effective Architecture Commit 和 Accepted Addendum 固定；Task 未授权 Developer 自行改变 Contract。
- `kernel → contracts/ports → application → adapters/apps` 的依赖方向、bounded context 写边界及 AGENTS.md 禁止项已通过 owned/allowed/forbidden paths 落入 Task 约束。
- Public Model Gateway health contract 未冻结，因此 T05 维持 Architecture Block，不会由 Developer 推断 response body。

### Parallel Safety

- 当前三个 `READY` Task 的 owned paths 互不重叠，可并行执行。
- 对所有 Task 的依赖闭包进行路径审计后，不存在无依赖关系的 owned-path 重叠。
- Contract、fixture、persistence、Harness、API、SSE 与 Web 均按 producer-first 依赖启动；consumer 不得在 producer contract 合并前开工。
- 高冲突 surface 均有唯一 owner。API 路径按 T06 → T07 以及 T06 → Architecture-unblocked T05 的前置关系串行化；实际 merge 继续遵守 Registry 的 dependency 与 merge order。

### Walking Skeleton and Quality Gates

Task DAG 能够闭合为完整纵向路径：

```text
Synthetic CSV
→ Web/API import boundary
→ Worker
→ Harness
→ Privacy Gate
→ Model Gateway
→ ImportPreview
→ Confirmation
→ Ledger
→ FinancialSnapshot
→ SSE/Web projection
```

该路径最终由 T09–T11 的八项 Walking Skeleton E2E 与 M01 conformance evidence 收口，不是仅交付横向 infrastructure。CI、architecture test、contract/cross-language conformance、privacy zero-leak、runtime/integration 与 browser E2E 均已进入 Task DAG，并具有独立 owner/reviewer 或最终 certification gate。

## Authorized Execution Batch

以下三个 Task 可立即并行开工：

| Task | Developer Stream | Reviewer Stream | Merge prerequisite |
|---|---|---|---|
| `M00-WP0001-T01` | Stream A — Platform / repository-root owner | Stream C — Runtime / Persistence | 无 Task dependency；开工和 review 必须校验 Effective Architecture Commit、Baseline 与 clean locked install。`.DS_Store` 等本机元数据不得进入提交。 |
| `M00-WP0002-T01` | Stream A — Platform / contract-fixture owner | Stream D — Product Integration | 无 Task dependency；fixture 必须严格通过 Schema `1.0.0` 与固定 SHA-256 校验，不得改变或扩展 public contract。 |
| `M01-WP0104-T01` | Stream B — Wealth Domain / fixture producer | Stream A — Platform / contracts owner | 无 Task dependency；仅使用 synthetic data，oracle 必须满足冻结的 Money、UTC、hash、privacy canary 与 reconciliation invariant。 |

Batch 内三个 Task 的 merge order 均为 `1`，相互之间没有 hard dependency；各自通过 required tests 和独立 reviewer 后可合并。合并动作不得顺带修改其他 Task surface。后续 Task 只有在其 Registry dependencies 全部合并、Developer 从满足依赖的 merge commit 建立独立 branch/worktree 后，才可按 DAG 进入下一授权批次。

本次批准不授权 `M01-WP0101-T05`、任何其他 blocked Task、M02、Architecture 修改或新 Milestone。
