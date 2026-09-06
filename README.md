# WealthPilot

本仓库是 WealthPilot 的 **Implementation Repository**，保存 Engineering Planning、Implementation Decisions、Task Registry、Production Code、Tests、Evals、Migrations、Infrastructure、Deployment 和 Runbooks。

Architecture Source of Truth：<https://github.com/SHUGOSHAx/wealthpilot-arch>

所有实现必须遵循根目录的 [`ARCHITECTURE_BASELINE`](ARCHITECTURE_BASELINE)。机器校验以其中记录的 immutable Git Commit SHA 为准，不以 branch name 为准。

当前状态：`MVP Fast Lane / Runnable Demo`

## Run the MVP

Prerequisites: Python 3.12 and `uv`.

```bash
uv sync --frozen --group dev
./scripts/run-demo.sh
```

Then open <http://127.0.0.1:8000>, select **使用演示数据**, and run the
pre-filled `600519 · 贵州茅台` research question. The complete local journey is:

```text
synthetic personal-finance CSV
→ deterministic FinancialSnapshot
→ cached A-share research through Model Gateway
→ deterministic suitability and allocation limit
→ browser result
```

The included demo produces assets `¥2,000,000`, liabilities `¥955,000`, net
worth `¥1,045,000`, monthly net cash flow `¥16,000`, and a deterministic maximum
allocation for `600519` of `¥58,000` (`5.55%` of net worth).

This is a synthetic, cached, local demo. It contains no broker connection and
has **NO LIVE SIDE EFFECT**. It is not investment advice.

## Verify

```bash
uv run pytest
./scripts/verify-architecture-baseline.sh
node --check apps/web/app.js
```

## Engineering Records

- [`ARCHITECTURE_BASELINE`](ARCHITECTURE_BASELINE)
- [`docs/engineering/engineering-handoff-report.md`](docs/engineering/engineering-handoff-report.md)
- [`docs/engineering/implementation-activation.md`](docs/engineering/implementation-activation.md)
- [`docs/engineering/mvp-fast-lane.md`](docs/engineering/mvp-fast-lane.md)
- [`docs/engineering/mvp-waivers.md`](docs/engineering/mvp-waivers.md)
- [`docs/engineering/mvp-delivery-report.md`](docs/engineering/mvp-delivery-report.md)

架构、产品边界、领域模型、公开 Contract、Accepted ADR 和 Accepted Architecture Addendum 以 Architecture Repository 为权威源，本 README 不复制或替代其内容。
