.PHONY: backend-dev frontend-dev test-api frontend-lint frontend-build backend-image backend-container frontend-image frontend-container

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

backend-image:
	docker build -f docker/backend/Dockerfile -t vnlaw-qa-backend:local .

backend-container:
	docker run --rm -p 8000:8000 -e LEGAL_QA_SERVICE_MODE=fake vnlaw-qa-backend:local

frontend-image:
	docker build -f docker/frontend/Dockerfile -t vnlaw-qa-frontend:local --build-arg NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 .

frontend-container:
	docker run --rm -p 3000:3000 vnlaw-qa-frontend:local
