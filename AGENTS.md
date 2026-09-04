# WealthPilot Implementation Repository Instructions

## Architecture

所有 Agent 必须遵守根目录的 `ARCHITECTURE_BASELINE` 及其固定的 Effective Architecture Commit。

Agent 不得：

- 自行改变产品边界；
- 自行改变公开 Contract；
- 自行改变 Domain Boundary；
- 绕过 Accepted ADR 或 Accepted Architecture Addendum；
- 把 Implementation Convenience 当作 Architecture Decision。

如果实现需要改变 Architecture，必须创建 `Architecture Issue / RFC Candidate`，说明问题、影响、相关架构依据、推荐方向和阻塞范围，并等待 Architect 接受。不得在 Implementation 中偷偷改变架构语义。

## Engineering Tasks

后续 Developer Agent 必须基于明确、已授权的 Task 工作。Task 必须提供：

- Task ID；
- Work Package；
- Goal；
- Architecture References；
- Dependencies；
- Owned Paths；
- Allowed Paths；
- Forbidden Paths；
- Input Contracts；
- Expected Outputs；
- Acceptance Criteria；
- Required Tests。

没有正式 Task，不进行大规模 Feature Development。标记为 `READY_FOR_PLANNING` 的 Work Package 仍需 Planner 创建完整 Task 后，Developer 才能实施。

## AI Agent Safety

AI Agent：

- 不得自行扩大 Scope；
- 不得自行创建未批准业务语义；
- 不得绕过 Test、CI 或 Review；
- 不得写入真实用户数据或凭据；
- 不得删除安全 Gate；
- 不得为了让测试通过而降低 Architecture Constraint；
- 不得把 P2/P3 原文、Secret、Broker 凭据或签名密钥写入代码、日志、Fixture 或普通文档；
- 不得启动、实现或模拟任何实盘交易能力。

## Repository Boundary

- `wealthpilot` 保存 Implementation Source of Truth，包括工程计划、实现决策、任务、代码、测试、评测、迁移、基础设施、部署和 Runbook。
- `wealthpilot-arch` 保存 Architecture Source of Truth，包括产品、架构、领域、公开 Contract、Roadmap、Acceptance Criteria、Accepted ADR 和 Accepted Addendum。

未经明确 Architecture RFC 流程和用户授权，Implementation Agent 不得修改 Architecture Repository。

## Current Authorization

当前只授权 M00 Engineering Foundation、M01 Gateway / Harness / Walking Skeleton 的 Planning，以及不依赖未冻结未来 Contract 的 Developer Tasks。M02–M12 大规模实施、Live Trading、Agent 自行定义公开 Contract 均未授权。
