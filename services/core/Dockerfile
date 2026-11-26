FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

COPY packages/contracts-py /app/packages/contracts-py
COPY packages/paymatch-hashing /app/packages/paymatch-hashing
COPY services/core/pyproject.toml /app/services/core/pyproject.toml
COPY services/core/migrations /app/services/core/migrations
COPY services/core/src /app/services/core/src
COPY services/sim-world/data/demo/core_seed /app/services/sim-world/data/demo/core_seed

RUN uv pip install --system --no-cache /app/packages/contracts-py /app/packages/paymatch-hashing /app/services/core

ENV CORE_SEED_DIR=/app/services/sim-world/data/demo/core_seed

EXPOSE 8001 8003

CMD ["python", "-m", "core.entrypoints.merchant_api"]
