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

`core-worker` reads `ledger.outbox` read-only and tracks its cursor inside `core.outbox_cursors` (never writing to `ledger`).
Migration `004_rls_and_grants.sql` conditionally grants `USAGE` and `SELECT` on `ledger` to role `merchant` if `ledger` already exists when `core` migrations run. If `payment-gate` migrations run **after** `core` migrations, apply the read-only grant after `payment-gate` creates schema `ledger`:

```sql
GRANT USAGE ON SCHEMA ledger TO merchant;
GRANT SELECT ON ALL TABLES IN SCHEMA ledger TO merchant;
```
