FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

COPY packages/contracts-py /app/packages/contracts-py
COPY packages/paymatch-hashing /app/packages/paymatch-hashing
COPY services/agent-runtime/pyproject.toml /app/services/agent-runtime/pyproject.toml
COPY services/agent-runtime/src /app/services/agent-runtime/src
COPY services/agent-runtime/prompts /app/services/agent-runtime/prompts
COPY services/agent-runtime/tests/cassettes /app/services/agent-runtime/tests/cassettes
COPY plugins /app/plugins

# Editable install: the runtime finds prompts/ and plugins/ relative to its source tree.
RUN uv pip install --system --no-cache --no-sources \
    /app/packages/contracts-py \
    /app/packages/paymatch-hashing \
    -e /app/services/agent-runtime

CMD ["python", "-m", "agent_runtime"]
