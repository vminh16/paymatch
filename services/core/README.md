# PayMatch `core` Service

System of record for PayMatch (`ingest`, `merchant`, `risk`, `control`, `tools`).

## Processes (same image, separate entrypoints & ports)

| Process | Entrypoint | Port | Prefix |
|---|---|---|---|
| `merchant-api` | `python -m core.entrypoints.merchant_api` | `8001` | `/m` |
| `internal-api` | `python -m core.entrypoints.internal_api` | `8003` | `/internal` |
| `core-worker` | `python -m core.entrypoints.worker` | — | — |

## Migrations & Demo Seed

```sh
# Apply numbered SQL migrations (schemas core, risk, control + roles merchant/staff + RLS)
uv run python -m core.persistence.migrator

# Reset and load demo seed from services/sim-world/data/demo/core_seed/
uv run python -m core.persistence.seeder
```

### Cross-schema read-only grant on `ledger`

`core-worker` (DB role `worker`) reads `ledger.outbox` (and optionally `ledger.payment_intents`) read-only and tracks receipts in `core.outbox_receipts` (never writing to `ledger`).
Both migration orders are handled automatically:
- If `payment-gate` creates schema `ledger` **before** `core` migrations run, `005`/`006` grant `USAGE` on `ledger` and narrow `SELECT` on `ledger.outbox` and `ledger.payment_intents` to `worker`.
- If `payment-gate` migrations run **after** `core` migrations, `payment-gate` grants `USAGE` on `ledger` and `SELECT` on `ledger.outbox` to `worker` when the role exists (and `core-worker` isolates any missing table/grant via a savepoint so Core outbox dispatch and scheduling continue).

If provisioning manually, only grant the narrow tables needed:

```sql
GRANT USAGE ON SCHEMA ledger TO worker;
GRANT SELECT ON TABLE ledger.outbox, ledger.payment_intents TO worker;
```

## Known limitations

- **Cross-alert lock scope (N3):** `_handle_cross_alert_published` acquires invoice row locks before Gate cancel HTTP I/O; transient cancel failures are logged and rely on Payment Gate re-evaluating at execution time.
- **Correspondence fetch-then-filter:** `inbox` and `chat_messages` tools fetch a page/thread from `sim-world` and filter to invoice/vendor relevance inside Core before returning to bots.
- **Untyped evidence paths:** Finding `evidence[].ref_id` validation verifies exact typed-ID presence anywhere in the cited `tool_call` output rather than binding each `EvidenceRef.kind` to a tool-specific JSON path.
- **Lease wait-past-expiry (I4):** Job lease mutation predicates evaluate `clock_timestamp()` during the SQL row scan prior to acquiring a contended row lock rather than re-evaluating after lock acquisition.
- **Shared RLS role (`merchant`):** `merchant-api` and `internal-api` use separate login roles (`merchant_api`, `internal_api`) but assume the same tenant-scoped `merchant` RLS role after authentication.
