FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

COPY services/sim-world/pyproject.toml /app/services/sim-world/pyproject.toml
COPY services/sim-world/src /app/services/sim-world/src
COPY services/sim-world/data /app/services/sim-world/data

RUN uv pip install --system --no-cache /app/services/sim-world

ENV SIM_PORT=8200
ENV SIM_DATA_DIR=/app/services/sim-world/data
ENV SIM_DATASET=demo
ENV DEMO_MODE=true

EXPOSE 8200

CMD ["uvicorn", "sim_world.app:app", "--host", "0.0.0.0", "--port", "8200"]
