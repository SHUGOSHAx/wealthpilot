# WealthPilot

本仓库是 WealthPilot 的 **Implementation Repository**，保存 Engineering Planning、Implementation Decisions、Task Registry、Production Code、Tests、Evals、Migrations、Infrastructure、Deployment 和 Runbooks。

Architecture Source of Truth：<https://github.com/SHUGOSHAx/wealthpilot-arch>

所有实现必须遵循根目录的 [`ARCHITECTURE_BASELINE`](ARCHITECTURE_BASELINE)。机器校验以其中记录的 immutable Git Commit SHA 为准，不以 branch name 为准。

当前状态：`Personal-Use MVP checkpoints implemented / real personal file validation required`

## Run the MVP

Prerequisites: Python 3.12 and `uv`.

```bash
uv sync --frozen --group dev
./scripts/run-demo.sh
```

Then open <http://127.0.0.1:8000>. Data is stored outside the repository at
`~/.local/share/wealthpilot/wealthpilot.db` by default. Override it with
`WEALTHPILOT_DATABASE_PATH` when needed.

```text
CSV → ImportPreview → correction → explicit confirmation
→ balanced local ledger → persisted FinancialSnapshot/history
→ real BaoStock A-share data → Model Gateway
→ deterministic suitability/allocation → persisted research history
```

The current real-data import adapter is the WealthPilot Generic CSV. Required
columns are `record_type,date,account,account_type,category,description,amount,currency,liquid`.
Optional `source_transaction_id` improves deduplication. Adding `asset_class`
(`CASH`, `EQUITY`, `FIXED_INCOME`, `REAL_ESTATE`, `OTHER`) enables complete
asset-allocation and equity-headroom calculations. See
`tests/fixtures/demo/personal_finance.csv` for an importable first-run sample.

BaoStock is a credential-free, delayed public-data source—not a real-time quote.
The application contains no broker connection and has **NO LIVE SIDE EFFECT**.
It is not investment advice.

Optional cloud-model configuration is read only from the environment:

```bash
export WEALTHPILOT_MODEL_BASE_URL=https://your-provider.example/v1
export WEALTHPILOT_MODEL_NAME=your-model
export WEALTHPILOT_MODEL_API_KEY=your-secret
```

Without these values, finance remains fully usable and research uses an explicit
offline narrative fallback; it never pretends a cloud model ran.

## Backup and restore

```bash
make backup
make restore BACKUP=/absolute/path/to/wealthpilot-*.wpbackup
```

Restore creates a safety backup of the current database first. Current backup
containers are integrity-verified but not encrypted; keep them on your trusted
device and read the recorded waiver before copying them elsewhere.

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
- [`docs/engineering/personal-use-mvp-scope.md`](docs/engineering/personal-use-mvp-scope.md)
- [`docs/engineering/personal-use-mvp-report.md`](docs/engineering/personal-use-mvp-report.md)
- [`docs/engineering/mvp-delivery-report.md`](docs/engineering/mvp-delivery-report.md)

架构、产品边界、领域模型、公开 Contract、Accepted ADR 和 Accepted Architecture Addendum 以 Architecture Repository 为权威源，本 README 不复制或替代其内容。
