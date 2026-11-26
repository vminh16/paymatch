# Lệnh chung của repo. Các target còn trống sẽ được điền khi service có code.
.PHONY: install up down reset test test-e2e eval contracts

install:          ## cài toàn bộ workspace
	uv sync --all-packages

up:               ## chạy hệ thống bằng docker compose
	docker compose -f infra/docker-compose.yml up -d

down:
	docker compose -f infra/docker-compose.yml down

reset:            ## nạp lại dữ liệu sim-world + DB về trạng thái demo
	@echo "TODO: gọi sim-world /scenario/reset và chạy lại seed"

test:             ## lint + unit + bất biến + contract + agent (fake/replay)
	uv run --all-packages pytest -q

test-e2e:
	@echo "TODO: chạy tests/e2e trên docker compose"

eval:             ## 36 ca × 3 cấu hình, LLM live (chạy tay)
	@echo "TODO: chạy eval/"

contracts:        ## sinh model Python từ contracts/
	@echo "TODO: sinh packages/contracts-py từ contracts/"
