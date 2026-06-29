.PHONY: backend-dev frontend-dev test-api frontend-lint frontend-build

backend-dev:
	LEGAL_QA_SERVICE_MODE=fake uv run python -m uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

frontend-dev:
	cd apps/frontend && npm run dev

test-api:
	env UV_CACHE_DIR=/tmp/vnlaw-uv-cache uv run pytest tests/unit/api tests/unit/services -q --durations=30

frontend-lint:
	cd apps/frontend && npm run lint

frontend-build:
	cd apps/frontend && npm run build
