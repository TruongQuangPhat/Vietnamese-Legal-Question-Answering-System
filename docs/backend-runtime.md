# Backend Runtime

## Overview

The VnLaw-QA backend exposes the legal QA product API through FastAPI. It is a
legal research assistant API, not a general chatbot and not a replacement for
professional legal advice.

The backend wraps the existing hierarchy-aware RAG workflow behind a service
boundary. Fake mode is the default and is safe for local API contract checks.
Real mode is explicit and should be used only for manual smoke checks when the
required local services and secrets are available.

## Configuration

Runtime settings are read from environment variables by `src/api/settings.py`.
`.env.example` contains both existing project-level variables and backend API
runtime variables. It must contain placeholders only.

`AppSettings.from_env()` loads the project `.env` first and overlays process
environment values. Exported or container-injected values therefore take
precedence. Explicit environment mappings used by tests bypass local `.env`
state.

Committed YAML config under `configs/` stores non-secret runtime defaults such
as retrieval settings and provider/model defaults. Local `.env` values select
those config files, override local endpoints/service mode, and provide secrets
when real mode is used. Do not put provider API keys or tokens in
`configs/*.yml`.

Backend API settings:

```env
APP_ENV=local
LOG_LEVEL=INFO
LOG_FORMAT=json
CORS_ALLOWED_ORIGINS='["http://localhost:3000"]'

LEGAL_QA_SERVICE_MODE=fake
LEGAL_QA_RETRIEVAL_CONFIG=configs/retrieval/retrieval.yml
LEGAL_QA_CHUNKS_PATH=data/processed/legal_chunks.jsonl
LEGAL_QA_LLM_CONFIG=configs/llm/openrouter.yml
LEGAL_QA_COLLECTION_NAME=vnlaw_chunks_bgem3_v1_full
LEGAL_QA_QDRANT_URL=http://localhost:6333
LEGAL_QA_DEVICE=cpu
LEGAL_QA_MODEL=google/gemini-2.5-flash

QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=vnlaw_chunks_bgem3_v1_full
QDRANT_API_KEY=

OPENROUTER_API_KEY=
OPENROUTER_MODEL=google/gemini-2.5-flash
```

`LEGAL_QA_QDRANT_URL` and `LEGAL_QA_COLLECTION_NAME` are backend-specific
overrides. `QDRANT_URL` and `QDRANT_COLLECTION` are compatible generic names.
`QDRANT_API_KEY` is optional; `LEGAL_QA_QDRANT_API_KEY` is accepted as a
backend-specific override. Local unauthenticated Qdrant continues to work when
the key is absent. Secret values are hidden in settings representations and
must not be logged.
`QDRANT_API_KEY` is required for authenticated Qdrant Cloud and optional for
local unauthenticated Qdrant.

These variables configure the backend runtime and readiness paths. The
maintained setup/index/validation CLIs also consume `QDRANT_API_KEY` and pass
it to the shared client builder. An explicit `--qdrant-api-key` takes
precedence, but the environment is preferred to avoid shell-history and
process-list exposure. Blank values mean unauthenticated local access. The
CLIs still require `--url` and `--collection-name`; they do not consume
`QDRANT_URL`, `QDRANT_COLLECTION`, or the backend-specific key alias. See
`docs/api_deployment.md` for the manual migration checklist.

`LEGAL_QA_DEVICE` selects the local embedding device in manual real mode.
`OPENROUTER_MODEL` is the provider-level default model. `LEGAL_QA_MODEL` is an
optional Legal QA runtime LLM model override and takes precedence for the API
runtime when set. It is not an embedding model.

Provider keys such as `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, and
`ANTHROPIC_API_KEY` are not required for fake mode. When needed for manual real
mode checks, set secrets outside version control.

`CORS_ALLOWED_ORIGINS` should be a JSON array string on Render, for example
`'["https://your-vercel-app.vercel.app"]'`. Legacy comma-separated values
remain accepted for local compatibility. Invalid JSON arrays are rejected so a
deployment cannot silently use malformed origins.

`LOG_FORMAT=json` documents the intended production convention. The current
FastAPI bootstrap does not yet apply this variable through a production
logging initializer.

## Fake Mode

Fake mode is the default:

```env
LEGAL_QA_SERVICE_MODE=fake
```

Fake mode does not require Qdrant, OpenRouter, an embedding model, a reranker,
or benchmark data. Use it for frontend integration, CORS checks, request
validation, logging checks, and API response contract checks.

## Real Mode

Real mode must be selected explicitly:

```env
LEGAL_QA_SERVICE_MODE=real
```

Before using real mode manually, confirm:

- `QDRANT_URL` (or `LEGAL_QA_QDRANT_URL`) is set.
- `QDRANT_COLLECTION` (or `LEGAL_QA_COLLECTION_NAME`) is set.
- Qdrant is running and the expected collection exists.
- `QDRANT_API_KEY` is set only when the Qdrant service requires it.
- `data/processed/legal_chunks.jsonl` exists locally.
- `LEGAL_QA_RETRIEVAL_CONFIG` points to a valid retrieval config.
- `LEGAL_QA_LLM_CONFIG` points to a valid LLM config.
- `OPENROUTER_API_KEY` is set in an uncommitted environment file or shell.
- No secrets are printed, logged, or pasted into docs.

Before workflow/client construction, real mode validates the required values
and local files. Invalid configuration fails with safe issue codes and does
not construct Qdrant, embedding, or LLM clients.

Do not use real mode in routine unit tests or default validation commands.
The committed backend image and Compose stack are fake-mode packaging
foundations, not real-mode deployment artifacts: the image does not install
the `qdrant` and `embedding` optional dependency groups or include the
processed chunks/model artifacts. See `docs/api_deployment.md` for the complete
readiness audit and blockers.

For the planned native Render Web Service, install runtime dependencies with:

```bash
python -m pip install --no-cache-dir uv && \
  uv sync --frozen --no-dev --extra qdrant --extra embedding && \
  python scripts/deployment/fetch_processed_chunks.py
```

Start one worker with Render's assigned port:

```bash
uv run python -m uvicorn src.api.app:app --host 0.0.0.0 --port $PORT
```

The build artifact fetcher requires:

```env
LEGAL_QA_CHUNKS_URL=https://huggingface.co/datasets/phattruong1802/vnlaw-qa/resolve/main/legal_chunks/v1/legal_chunks.jsonl
LEGAL_QA_CHUNKS_SHA256=95ff0129915ad4e77306fbdaa2c6eb8c7a7c58730cd21050aec429541416b30c
LEGAL_QA_CHUNKS_PATH=data/processed/legal_chunks.jsonl
```

The public artifact does not require `HF_TOKEN`. If access later becomes
private or gated, inject `HF_TOKEN` as a secret. The fetcher verifies SHA256
before atomic installation, skips an already matching file, and refuses to
replace a mismatched file unless `LEGAL_QA_CHUNKS_OVERWRITE=1` is explicitly
set.

The resulting file remains ignored by Git. Local BM25 loads it in real mode
even when dense retrieval uses Qdrant Cloud. Fetching this immutable,
checksum-pinned build artifact is deployment preparation; startup still must
not process the corpus, index data, restore snapshots, or call external LLMs.

## Run the Backend

Install dependencies:

```bash
uv sync
```

Run safely in fake mode from the repository root:

```bash
make backend-dev
```

Equivalent direct command:

```bash
LEGAL_QA_SERVICE_MODE=fake uv run python -m uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
```

Using `python -m uvicorn` ensures uvicorn runs with the project Python
environment managed by `uv`.

The app factory is also available for factory-based startup:

```bash
LEGAL_QA_SERVICE_MODE=fake uv run python -m uvicorn src.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

- `GET /health`
- `GET /api/v1/readiness`
- `GET /version`
- `POST /api/v1/legal-qa/ask`
- `GET /api/v1/conversations`
- `POST /api/v1/conversations`
- `GET /api/v1/conversations/{conversation_id}`
- `PATCH /api/v1/conversations/{conversation_id}`
- `DELETE /api/v1/conversations/{conversation_id}`
- `POST /api/v1/conversations/{conversation_id}/messages`

`GET /health` is liveness only. It returns a constant response and does not
establish Qdrant, model, corpus artifact, or provider readiness.

`GET /api/v1/readiness` returns 200 when ready and 503 otherwise. Fake mode is
ready without external dependencies. Real mode checks required configuration
and local artifact presence, then performs one read-only Qdrant
`get_collection` metadata request with a short timeout. It does not call
OpenRouter, load/download the embedding model, run retrieval/generation, or
mutate Qdrant. Responses contain only safe status codes and never secret
values or raw exception text.

Legal QA request fields:

- `question`: required, stripped, non-empty, maximum 4000 characters.
- `top_k`: optional, default `10`, minimum `1`, maximum `20`.
- `include_evidence`: optional, default `true`.
- `include_debug`: optional, default `false`.

## Fake Mode Smoke Test

Start the backend in fake mode with `make backend-dev`, then run:

```bash
curl -s http://localhost:8000/health
```

```bash
curl -s http://localhost:8000/version
```

```bash
curl -s -X POST http://localhost:8000/api/v1/legal-qa/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Người lao động được quyền đơn phương chấm dứt hợp đồng lao động khi nào?",
    "top_k": 10,
    "include_evidence": true,
    "include_debug": false
  }'
```

Expected fake-mode behavior:

- The health route returns `{"status":"ok"}`.
- The readiness route returns `ready=true` without external calls.
- The version route returns deterministic API metadata.
- The ask route returns the stable Legal QA response contract with stub data.
- No Qdrant, OpenRouter, embedding model, reranker, or evaluation workflow is
  called.

## Backend Container

Build the backend image from the repository root:

```bash
make backend-image
```

Run the image in fake mode:

```bash
make backend-container
```

Equivalent direct commands:

```bash
docker build -f docker/backend/Dockerfile -t vnlaw-qa-backend:local .
docker run --rm -p 8000:8000 -e LEGAL_QA_SERVICE_MODE=fake vnlaw-qa-backend:local
```

Smoke check the running container:

```bash
curl -s http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

The backend Dockerfile defaults `LEGAL_QA_SERVICE_MODE` to `fake` and starts the
API with:

```bash
python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

Fake-mode containers do not require Qdrant, OpenRouter, embedding models,
rerankers, or legal corpus data. Real mode requires additional runtime setup and
is not part of this container packaging workflow.

## Fake-Mode Compose Stack

Run the backend and frontend together from the repository root with
`docker-compose.yml`:

```bash
make stack-up
```

Equivalent direct command:

```bash
docker compose -f docker-compose.yml up --build
```

The stack publishes:

- Backend API: `http://localhost:8000`
- Frontend UI: `http://localhost:3000`

Smoke checks:

```bash
curl -s http://localhost:8000/health
curl -I http://localhost:3000
```

Expected backend response:

```json
{"status":"ok"}
```

Shut down the stack:

```bash
make stack-down
```

Equivalent direct command:

```bash
docker compose -f docker-compose.yml down
```

The Compose stack runs `LEGAL_QA_SERVICE_MODE=fake`, does not mount `.env`, and
does not require Qdrant, OpenRouter, embedding models, rerankers, or legal
corpus data. The frontend build argument `NEXT_PUBLIC_API_BASE_URL` remains
`http://localhost:8000` because browser requests originate from the host
machine, not from inside the Docker network. Do not put secrets in
`NEXT_PUBLIC_*` variables.

## Real Mode Manual Smoke Checklist

Use this only when intentionally checking real local services.

1. Confirm Qdrant is running locally.
2. Confirm the configured collection name exists.
3. Confirm the processed chunks path and config paths exist.
4. Export `OPENROUTER_API_KEY` from a private shell or uncommitted `.env`.
5. Set `LEGAL_QA_SERVICE_MODE=real`.
6. Start the backend manually.
7. Send one low-risk legal research question.
8. Confirm the response preserves the API contract.
9. Confirm citations refer only to selected citable child evidence.
10. Stop the backend after the check.

Do not run full benchmarks, strict generation evaluation, corpus indexing,
embedding inference, reranking inference, or Qdrant writes as part of this
manual smoke checklist.

## Safety Notes

- Do not commit `.env`.
- Do not commit real API keys.
- Do not paste provider raw responses into docs, issues, logs, or reports.
- Do not log raw legal questions, raw prompts, chain-of-thought, secrets,
  tracebacks, or full evidence text.
- Keep fake mode as the default for routine development and tests.
- Real mode can call external services and should be treated as a manual,
  intentional operation.
- The API supports legal research only and does not provide professional legal
  advice.
- The system is not production-ready until deployment/security review and a
  controlled real-mode smoke are complete.

### Conversation storage boundary

Conversation API storage is process-local and in memory. It is not durable,
not shared across workers or replicas, and disappears on process restart.
There is no durable server-side chat history unless database-backed storage is
implemented. Frontend localStorage remains the rich UI source of truth and
backend synchronization remains best-effort.

## Troubleshooting

- If the frontend cannot call the backend, check `CORS_ALLOWED_ORIGINS`.
- If real mode starts without the expected collection, check
  `LEGAL_QA_COLLECTION_NAME` and `LEGAL_QA_QDRANT_URL`.
- If real mode cannot generate an answer, confirm `OPENROUTER_API_KEY` is set in
  the shell or an uncommitted environment file.
- If request validation fails, confirm `question` is non-empty after trimming and
  no longer than 4000 characters.
- If fake mode tries to reach Qdrant or OpenRouter, verify
  `LEGAL_QA_SERVICE_MODE=fake` and clear any cached app/service process.
