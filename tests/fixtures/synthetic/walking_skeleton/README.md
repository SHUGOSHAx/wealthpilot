# M01 Walking Skeleton synthetic fixture

This fixture set is wholly synthetic. It does not describe a real person, bank,
account, merchant, or transaction. Stable UUIDs, timestamps, amounts, and names
exist only to make the M01 walking-skeleton tests deterministic.

## Internal CSV layout

`bank/generic_bank.csv` uses one deliberately narrow, internal M01 test layout:

```text
occurred_at,direction,amount,currency,description,category_hint
```

- `occurred_at` is already-normalized UTC (`Z`) for this fixture.
- `direction` is `INFLOW` or `OUTFLOW`; it is not ledger debit/credit.
- `amount` is a positive canonical decimal string and `currency` is `CNY`.
- `description` is local P2 display text. It must not cross the model boundary
  without minimization/redaction.
- `category_hint` is an internal rule hint (`INCOME`, `EXPENSE`, or empty). An
  empty hint represents a deliberately ambiguous merchant row for model
  classification.
- `source_row_number` in the oracle is the 1-based physical CSV line number,
  including the header as line 1.

This is not a public CSV contract and makes no claim of compatibility with a
real bank export. `generic_bank.duplicate.csv` is byte-for-byte identical to
the source fixture so duplicate-file hash behavior can be tested.

## Oracle

The public payload oracles contain only fields frozen by Walking Skeleton
Contract Addendum 1 schema `1.0.0`. The internal ledger oracle models two
postings per READY transaction and proves exact CNY debit/credit balance.

Run the complete fixture verification from the implementation repository root:

```bash
python3 tests/fixtures/synthetic/walking_skeleton/oracle/verify_fixture.py \
  --schema ../wealthpilot-arch/docs/contracts/schemas/walking-skeleton-contract-addendum-1.schema.json
```

The verifier checks the fixed architecture Schema SHA-256, fixture hashes,
duplicate determinism, relevant JSON Schema constraints, preview totals,
privacy canary isolation, balanced postings, and snapshot reconciliation.
