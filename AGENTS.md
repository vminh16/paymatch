# AGENTS.md

PayMatch: a multi-agent AI accounting team that checks supplier invoices before payment for small store chains on MoMo Doanh Nghiệp. Team of 3, deadline 03/12/2026: a demo that runs correctly beats more features.

## Docs are the spec

Read the relevant doc before writing code; code follows the docs.

- Scope and v1 boundaries: `docs/01-requirements/problem-definition.md`
- Service boundaries and the decision log: `docs/02-architecture/architecture.md`
- Repo layout, required tests, naming: `docs/02-architecture/repo-and-testing.md`
- Endpoints, ports, error codes, events, shared schemas: `docs/05-api/`
- Agents, guardrails, reason codes, tools: `docs/03-agents/`
- Sample data and the e-invoice XML format: `docs/04-data/`

Once `contracts/` holds OpenAPI/JSON Schema, it is the source of truth for APIs.

## Rules

- **Follow the spec.** Take endpoint, field, enum, status, reason code, tool and event names exactly from docs/contracts. Need something new? Add it to the docs (and `contracts/`) first, then code it. If code and docs disagree, stop and ask.
- **Contract first.** Edit `contracts/`, run `make contracts`, then change code. `packages/contracts-py` is generated; leave it untouched.
- **Values come from config, seed data or manifests.** Limits, thresholds, timeouts, URLs, keys, model names and bot/tool lists live in env, seed, `PlatformLimits`, `ModelConfig` or bot manifests. Logic works for any tenant and any invoice; demo scenarios live in `sim-world` data.
- **Simplest correct change.** Smallest diff that fully solves the task. Add an abstraction only when two real call sites need it.
- **Think architecture first.** Decide which service and which layer a change belongs to, and keep the boundaries:
  - services talk over HTTP per the contracts; shared code lives only in `packages/`;
  - hexagonal: `domain/` is pure Python with no I/O; I/O sits in `adapters/` behind a port;
  - `agent-runtime` has no DB credentials and only calls `internal-api`;
  - only Payment Gate moves money; colour, amounts and pay decisions are computed by code, the LLM only proposes.
- **Use what exists.** Reach for the chosen frameworks before writing your own: FastAPI, Pydantic, LangGraph prebuilt ReAct, httpx, pytest; React + Vite, TanStack Query, shadcn/ui, Tailwind, Motion. Ask before adding a dependency, with the reason.
- **Clean code.** Short single-purpose functions, clear names, comments only for *why*. Identifiers in English; Vietnamese only in display strings and docs.
- **Tests ship with code.** New logic gets a test. The safety invariants in repo-and-testing.md §4 always have tests. Agent tests use a fake LLM or Replay. Run `make test` and show its output before reporting done.
- **Decision changed → docs changed.** Add a row to the decision table in architecture.md and update every affected doc in the same change.

## Commands

See the `Makefile` (`make install`, `make up`, `make test`, `make contracts`).
