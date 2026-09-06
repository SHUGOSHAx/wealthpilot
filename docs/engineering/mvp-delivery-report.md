# WealthPilot MVP Delivery Report

## Decision

`DELIVERED`

The MVP Fast Lane vertical slice is runnable locally and has been independently
reviewed at the wealth, research/risk/privacy, and web UI boundaries before the
integrated Technical Director gate.

## Delivered journey

```text
Synthetic CSV
→ strict parser
→ deterministic FinancialSnapshot
→ Web/API
→ cached 600519 research
→ unified offline Model Gateway
→ structured narrative memo
→ deterministic suitability/risk engine
→ Web result
```

The supplied demo fixture yields:

- Assets: CNY 2,000,000
- Liabilities: CNY 955,000
- Net worth: CNY 1,045,000
- Monthly inflow/outflow/net: CNY 30,000 / 14,000 / 16,000
- Liquid assets: CNY 200,000
- Investable capital: CNY 116,000
- `600519` deterministic result: `SUITABLE`
- Maximum allocation: CNY 58,000, or 5.55% of net worth

The maximum amount is the minimum of the implemented deterministic constraints:
investable capital, six-month reserve headroom, a 10% single-security cap, and
the security risk-weight cap. Missing required inputs return no concrete amount.

## Safety gate

- Authoritative money, snapshot, suitability, and allocation fields are produced
  by deterministic Decimal-based code.
- Model output is narrative-only and passes through one Model Gateway abstraction.
- Privacy tests prove that raw transactions/account details and P2/P3 fields fail
  closed before Model Gateway invocation.
- Only synthetic finance data is committed.
- The research catalog is cached and clearly dated; it is not real-time data.
- No broker/order adapter exists. API and UI both state `NO LIVE SIDE EFFECT`.
- The Architecture repository was not modified.

## Verification evidence

- Full Python suite: 27 tests passed.
- Unit coverage: CSV/snapshot arithmetic, validation, research orchestration,
  deterministic risk limits, adverse model-output isolation.
- Security coverage: aggregate allowlist plus P2/P3/raw-record rejection.
- Integration coverage: health, sample import, exact snapshot, exact research
  result, invalid-input redaction, static web shell.
- Browser E2E: desktop and 390×844 mobile journeys completed; no browser console
  errors or warnings were observed.
- JavaScript syntax check and architecture-baseline verifier passed.

## Deferred work

Production persistence, queues/workers, SSE, durable ledger/confirmation,
real-time research sources, vendor model credentials, broker integrations, and
full Architecture certification remain outside this MVP. The exact temporary
deviations are recorded in `mvp-waivers.md`; none is promoted to an Architecture
decision.
