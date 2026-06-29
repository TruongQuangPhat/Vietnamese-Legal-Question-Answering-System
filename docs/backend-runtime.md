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

Backend API settings:

```env
APP_ENV=local
LOG_LEVEL=INFO
CORS_ALLOWED_ORIGINS=http://localhost:3000

LEGAL_QA_SERVICE_MODE=fake
LEGAL_QA_RETRIEVAL_CONFIG=configs/retrieval/retrieval.yml
LEGAL_QA_CHUNKS_PATH=data/processed/legal_chunks.jsonl
LEGAL_QA_LLM_CONFIG=configs/llm/openrouter.yml
LEGAL_QA_COLLECTION_NAME=vnlaw_chunks_bgem3_v1_full
LEGAL_QA_QDRANT_URL=http://localhost:6333
LEGAL_QA_DEVICE=cpu
LEGAL_QA_MODEL=BAAI/bge-m3
```

`QDRANT_URL` remains the general project-level Qdrant URL used by older scripts
and workflows. `LEGAL_QA_QDRANT_URL` is the backend Legal QA runtime override
used by API settings.

Provider keys such as `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, and
`ANTHROPIC_API_KEY` are not required for fake mode. When needed for manual real
mode checks, set secrets outside version control.

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

- Qdrant is running and reachable.
- The expected collection exists.
- `data/processed/legal_chunks.jsonl` exists locally.
- `LEGAL_QA_RETRIEVAL_CONFIG` points to a valid retrieval config.
- `LEGAL_QA_LLM_CONFIG` points to a valid LLM config.
- `OPENROUTER_API_KEY` is set in an uncommitted environment file or shell.
- No secrets are printed, logged, or pasted into docs.

Do not use real mode in routine unit tests or default validation commands.

## Run the Backend

Install dependencies:

```bash
uv sync
```

Run safely in fake mode:

```bash
LEGAL_QA_SERVICE_MODE=fake uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000
```

The app factory is also available for factory-based startup:

```bash
LEGAL_QA_SERVICE_MODE=fake uv run uvicorn src.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

## API Endpoints

- `GET /health`
- `GET /version`
- `POST /api/v1/legal-qa/ask`

Legal QA request fields:

- `question`: required, stripped, non-empty, maximum 4000 characters.
- `top_k`: optional, default `10`, minimum `1`, maximum `20`.
- `include_evidence`: optional, default `true`.
- `include_debug`: optional, default `false`.

## Fake Mode Smoke Test

Start the backend in fake mode, then run:

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
- The version route returns deterministic API metadata.
- The ask route returns the stable Legal QA response contract with stub data.
- No Qdrant, OpenRouter, embedding model, reranker, or evaluation workflow is
  called.

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
