# WealthPilot MVP Fast Lane

## Product outcome

The MVP demonstrates one local, synthetic vertical slice:

```text
synthetic personal-finance CSV
→ deterministic account/transaction parsing
→ deterministic FinancialSnapshot and cash-flow summary
→ A-share symbol/question
→ cached public demo research
→ unified Model Gateway
→ structured research narrative
→ deterministic suitability and maximum-allocation calculation
→ browser presentation
```

The default demo symbol is `600519` (贵州茅台). Research data is cached demo
data with an explicit `as_of` value; it is not a live quote or investment
recommendation.

## Hard boundaries

- Money, balance, assets, liabilities, net worth, cash flow, suitability and
  maximum allocation are computed by deterministic Python code using Decimal.
- Model output supplies narrative research only. It cannot mutate the ledger or
  determine authoritative financial/risk values.
- All model behavior is accessed through the Model Gateway abstraction. The
  default adapter is deterministic and offline.
- Only synthetic finance data is committed. Raw transaction descriptions never
  enter model requests or ordinary logs.
- No broker adapter, order submission or live-trading side effect exists. Every
  research response carries `no_live_side_effect=true`.
- `wealthpilot-arch` remains read-only.

## Local interfaces

The Fast Lane endpoints live under `/api/v1/demo`. They are private demo
interfaces, not a new frozen public Architecture contract:

- `GET /api/v1/demo/health`
- `GET /api/v1/demo/sample-csv`
- `POST /api/v1/demo/import`
- `GET /api/v1/demo/symbols`
- `POST /api/v1/demo/research`

The browser UI is served by the same local FastAPI process.

## Definition of done

1. A fresh locked install succeeds.
2. Unit, security and API integration tests pass.
3. The application starts locally and health responds.
4. Browser E2E uploads the supplied CSV, renders the exact snapshot, researches
   `600519`, and renders a deterministic suitability/allocation result.
5. Secret/privacy scans find no credential or raw finance leakage in model
   capture, logs or responses.
