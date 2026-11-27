-- Least-privilege login role `gate` owning schema `ledger` (used by local docker-compose).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gate') THEN
        CREATE ROLE gate LOGIN PASSWORD 'gate' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    ELSE
        ALTER ROLE gate WITH LOGIN PASSWORD 'gate';
    END IF;
END
$$;

CREATE SCHEMA IF NOT EXISTS ledger AUTHORIZATION gate;
