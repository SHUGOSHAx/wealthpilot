# WealthPilot Personal-Use MVP Report

## Status

`CHECKPOINTS_IMPLEMENTED — REAL PERSONAL FILE VALIDATION REQUIRED`

The four product workflows are implemented and verified with synthetic fixtures,
an isolated persistent local database, a real BaoStock request, API integration
tests and browser E2E. The product is not labelled
`PERSONAL_USE_MVP_COMPLETE` until at least one user-provided export is adapted
and validated end to end.

## Real Data Sources Supported

- WealthPilot Generic CSV: real local import path with required validation,
  preview, source-file hash and optional source transaction identity.
- BaoStock: credential-free delayed public A-share security, recent market,
  profit/fundamental and valuation data. Fake data remains test-only; an
  explicitly labelled offline narrative is used if no model is configured.

## Personal Finance Capabilities

- Preview before commit; correct classification and merchant, or mark transfer,
  refund and reimbursement.
- File-level idempotency and row-level source-ID/fingerprint deduplication,
  including partial-overlap imports.
- Decimal money and two-posting balanced journal entries.
- Post-confirmation corrections through immutable reversal and replacement.
- Deterministic accounts, assets, liabilities, net worth, monthly cash flow,
  liquid assets, investable capital and basic asset allocation.

## Research Capabilities

- Real A-share lookup through the `EquityDataProvider` boundary.
- Structured, evidence-linked memo with provider/as-of/fetched-at provenance,
  limitations and deterministic research-risk signals.
- Every generative call crosses the unified Model Gateway. Invalid schemas and
  unavailable evidence citations fail closed.
- Research records persist the query, data time, memo, risk result and exact
  FinancialSnapshot content-hash/time reference.

## Personalization Capabilities

The deterministic risk engine combines net worth, liquidity, six-month reserve,
cash flow, investable capital, existing equity exposure and research risk. The
maximum position is the minimum applicable financial limit and cannot be
overridden by model output. Missing required data produces no concrete amount.

## Persistence

Private data is stored in a versioned local SQLite database outside the source
checkout. WAL, foreign keys, full synchronous writes, transactional confirmation,
restart persistence, v1-to-v2 migration and snapshot history are tested. Database
and backup files are restricted to the current OS user.

## Backup / Restore

`make backup` creates a consistent SQLite backup and compares a deterministic
logical digest with the source. `make restore BACKUP=/absolute/path` validates
integrity and equivalence and creates a safety backup before replacement.

## Privacy

- The server binds to `127.0.0.1` by default and has no broker integration.
- Secrets are environment-only and are excluded from database, repository and
  normal logs.
- Raw financial records and FinancialSnapshot data are never projected into the
  research model request. Only the user question and minimized public market
  facts cross the gateway; personalization runs locally afterward.
- Privacy negative tests reject transaction payloads, account numbers, passwords,
  token-like secrets and explicit P3 inputs.

## Run Instructions

```bash
uv sync --frozen --group dev
./scripts/run-demo.sh
```

Open <http://127.0.0.1:8000>. The default database is
`~/.local/share/wealthpilot/wealthpilot.db`; `WEALTHPILOT_DATABASE_PATH` can select
another local path.

## Remaining Limitations

- Direct Alipay, WeChat Pay and bank/card export adapters require representative
  user exports; the current real import source is the documented Generic CSV.
- BaoStock data is delayed and does not provide the complete document/page-level
  evidence ledger required for high-confidence production research.
- Without a configured cloud model, research narration is explicitly offline and
  deterministic; market data and personal risk calculation remain real/local.
- Backup containers are integrity-verified but not application-encrypted. They
  must remain on the same trusted device.
- Single-process/private API, SQLite and local execution are personal-use only.

## MVP Waivers

See `docs/engineering/mvp-waivers.md`: SQLite persistence, in-process/private API,
local hash projection, trusted-device unencrypted backup, and reduced provider
evidence depth. None waives financial correctness, privacy red lines, duplicate
posting protection, recovery, or the prohibition on live side effects.

## Next 5 Highest-value Improvements

1. Add and validate the user's highest-volume native payment/bank export adapter.
2. Encrypt backups with a user-held recovery secret or OS Keychain lifecycle.
3. Add point-in-time filings and page/block evidence for A-share research.
4. Add account-to-account transfer matching and balance-observation variance UX.
5. Add scheduled local backups and snapshot trend views after real-data validation.
