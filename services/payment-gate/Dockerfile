FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

COPY packages/paymatch-hashing /app/packages/paymatch-hashing
COPY packages/contracts-py /app/packages/contracts-py
COPY services/payment-gate/pyproject.toml /app/services/payment-gate/pyproject.toml
COPY services/payment-gate/src /app/services/payment-gate/src
COPY services/payment-gate/migrations /app/services/payment-gate/migrations

RUN uv pip install --system --no-cache --no-sources \
    /app/packages/paymatch-hashing \
    /app/packages/contracts-py \
    /app/services/payment-gate

ENV GATE_PORT=8100
EXPOSE 8100

CMD ["uvicorn", "gate.adapters.http.app:app", "--host", "0.0.0.0", "--port", "8100"]
