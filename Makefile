# Lệnh chung của repo. Các target còn trống sẽ được điền khi service có code.
.PHONY: install up down reset test test-db test-e2e eval contracts mock

install:          ## cài toàn bộ workspace
	uv sync --all-packages

up:               ## chạy hệ thống bằng docker compose
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

reset:            ## nạp lại dữ liệu sim-world + DB về trạng thái demo
	uv run python -m core.persistence.migrator
	uv run python -m core.persistence.seeder
	curl -fsS -X POST "$${SIM_URL:-http://localhost:8200/sim}/scenario:reset" \
		-H "Content-Type: application/json" \
		-d '{"dataset":"demo","seed":42}' >/dev/null || true

test:             ## lint + unit + bất biến + contract + agent (fake/replay)
	uv run --all-packages pytest -q

test-db:          ## chỉ chạy DB tests (testcontainers Postgres 16)
	uv run --all-packages pytest -m db -q

test-e2e:
	@echo "TODO: chạy tests/e2e trên docker compose"

eval:             ## 36 ca × 3 cấu hình, LLM live (chạy tay)
	@echo "TODO: chạy eval/"

contracts:        ## sinh model Python từ contracts/
	rm -rf packages/contracts-py/src/paymatch_contracts/schemas \
		packages/contracts-py/src/paymatch_contracts/events \
		packages/contracts-py/src/paymatch_contracts/merchant.py \
		packages/contracts-py/src/paymatch_contracts/internal.py \
		packages/contracts-py/src/paymatch_contracts/gate.py
	uv run datamodel-codegen \
		--input contracts/schemas \
		--input-file-type jsonschema \
		--output packages/contracts-py/src/paymatch_contracts/schemas \
		--output-model-type pydantic_v2.BaseModel \
		--target-python-version 3.12 \
		--use-standard-collections \
		--use-union-operator \
		--use-title-as-name \
		--field-constraints \
		--use-annotated \
		--use-type-alias \
		--allow-population-by-field-name \
		--formatters builtin \
		--disable-timestamp \
		--custom-file-header "# generated — do not edit"
	uv run datamodel-codegen \
		--input contracts/events \
		--input-file-type jsonschema \
		--output packages/contracts-py/src/paymatch_contracts/events \
		--output-model-type pydantic_v2.BaseModel \
		--target-python-version 3.12 \
		--use-standard-collections \
		--use-union-operator \
		--use-title-as-name \
		--field-constraints \
		--use-annotated \
		--use-type-alias \
		--allow-population-by-field-name \
		--allow-remote-refs \
		--formatters builtin \
		--disable-timestamp \
		--custom-file-header "# generated — do not edit"
	uv run datamodel-codegen \
		--input contracts/openapi/core-merchant.yaml \
		--input-file-type openapi \
		--output packages/contracts-py/src/paymatch_contracts/merchant.py \
		--output-model-type pydantic_v2.BaseModel \
		--target-python-version 3.12 \
		--use-standard-collections \
		--use-union-operator \
		--use-title-as-name \
		--field-constraints \
		--use-annotated \
		--use-type-alias \
		--allow-population-by-field-name \
		--allow-remote-refs \
		--formatters builtin \
		--disable-timestamp \
		--custom-file-header "# generated — do not edit"
	uv run datamodel-codegen \
		--input contracts/openapi/core-internal.yaml \
		--input-file-type openapi \
		--output packages/contracts-py/src/paymatch_contracts/internal.py \
		--output-model-type pydantic_v2.BaseModel \
		--target-python-version 3.12 \
		--use-standard-collections \
		--use-union-operator \
		--use-title-as-name \
		--field-constraints \
		--use-annotated \
		--use-type-alias \
		--allow-population-by-field-name \
		--allow-remote-refs \
		--formatters builtin \
		--disable-timestamp \
		--custom-file-header "# generated — do not edit"
	uv run datamodel-codegen \
		--input contracts/openapi/gate.yaml \
		--input-file-type openapi \
		--output packages/contracts-py/src/paymatch_contracts/gate.py \
		--output-model-type pydantic_v2.BaseModel \
		--target-python-version 3.12 \
		--use-standard-collections \
		--use-union-operator \
		--use-title-as-name \
		--field-constraints \
		--use-annotated \
		--use-type-alias \
		--allow-population-by-field-name \
		--allow-remote-refs \
		--formatters builtin \
		--disable-timestamp \
		--custom-file-header "# generated — do not edit"
	uv run python -c 'import json, pathlib; root = pathlib.Path("contracts/schemas"); out = pathlib.Path("packages/contracts-py/src/paymatch_contracts/__init__.py"); entries = [(p.stem.replace("-", "_").replace(".", "_"), json.loads(p.read_text())["title"]) for p in sorted(root.glob("*.schema.json"))]; lines = ["# generated — do not edit", "", "from __future__ import annotations", ""] + [f"from .schemas.{mod} import {cls}" for mod, cls in entries] + ["", "__all__ = ["] + [f"    \"{cls}\"," for _, cls in sorted(entries, key=lambda x: x[1])] + ["]", ""]; out.write_text("\n".join(lines), encoding="utf-8")'
	uv run python -c 'import json, pathlib; root = pathlib.Path("contracts/events"); out = pathlib.Path("packages/contracts-py/src/paymatch_contracts/events/__init__.py"); entries = [(p.stem.replace("-", "_").replace(".", "_"), json.loads(p.read_text())["title"]) for p in sorted(root.glob("*.schema.json"))]; lines = ["# generated — do not edit", "", "from __future__ import annotations", ""] + [f"from .{mod} import {cls}" for mod, cls in entries] + ["", "__all__ = ["] + [f"    \"{cls}\"," for _, cls in sorted(entries, key=lambda x: x[1])] + ["]", ""]; out.write_text("\n".join(lines), encoding="utf-8")'

mock:             ## chạy Prism mock server cho frontend trên core-merchant.yaml (cổng 8001)
	npx @stoplight/prism-cli mock -p 8001 contracts/openapi/core-merchant.yaml
