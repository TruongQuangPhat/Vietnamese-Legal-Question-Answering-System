# API Deployment Readiness

## Purpose and current status

VnLaw-QA is a Vietnamese legal research assistant, not legal advice. The
current product is a fake-mode Legal QA chat MVP with a real-workflow adapter;
it is not production-ready.

The repository has useful deployment foundations, but real mode is not yet
deployable from the committed containers or Compose stack. Do not describe the
system as production-ready until deployment and security review, dependency
and artifact packaging, readiness checks, and a controlled real-mode smoke
have been completed.

This document records the repository state as audited without calling Qdrant,
OpenRouter, embedding inference, or evaluation workflows.

## What already exists

- FastAPI application under `src/api` with:
  - `GET /health`;
  - `GET /version`;
  - `POST /api/v1/legal-qa/ask`;
  - the lightweight `/api/v1/conversations` contract.
- Typed API schemas, dependency injection, sanitized ask failures, safe request
  metadata, and deterministic fake mode.
- Explicit `LEGAL_QA_SERVICE_MODE=fake|real`; fake is the default.
- A real-mode adapter for coverage-aware dense plus local BM25 retrieval,
  evidence selection, strict generation, citation validation, and fallback.
- Configurable CORS origins.
- Next.js frontend clients using `NEXT_PUBLIC_API_BASE_URL`.
- Backend and frontend Dockerfiles and a fake-mode `docker-compose.yml`.
- Unit tests around API settings, routes, services, conversation context, and
  fake dependencies.

Fake mode is only for UI/API contract smoke. Its deterministic stub answer and
evidence do not establish legal correctness, retrieval quality, provider
connectivity, or real multi-turn quality.

## Readiness summary

| Area | Current state | Deployment consequence |
| --- | --- | --- |
| Service mode | Fake is safe by default; real wiring exists | Real startup and one request still need controlled validation |
| Qdrant | URL, collection, timeout, and vector contract exist | No API-key/TLS-specific setting is wired; service must remain private or client support must be added |
| Embedding and sparse retrieval | Real mode constructs BGE-M3 and loads the complete chunks JSONL | Model dependencies/cache and processed chunks are absent from the backend image |
| LLM provider | OpenRouter URL/model config and `OPENROUTER_API_KEY` lookup exist | Provider credential, egress, timeout/error behavior, and real response remain unverified |
| Health | `/health` returns a constant `{"status":"ok"}` | It is liveness only; there is no dependency-aware readiness endpoint |
| Version | Static API name/version is exposed | It has no build or revision identity |
| CORS | Comma-separated explicit origins are supported; local origin is default | Deployed frontend origins must be supplied explicitly |
| Frontend API URL | One public base URL is used by both clients | It is embedded during `next build`; localhost fallback is unsafe for an omitted production setting |
| Containers | Fake-mode images and Compose stack build the MVP | Committed stack does not package or configure real mode |
| Conversation storage | Process-local in-memory repository | Not durable, not shared across workers, and not user-specific |
| API security | Input bounds and sanitized errors exist | Authentication, authorization, rate limiting, trusted proxy policy, and abuse controls are not implemented |
| Observability | Safe completion/failure metadata is logged | Production logging configuration, metrics, tracing, and alerting are not established |

## Runtime configuration

### Backend process environment

Current API settings:

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
LEGAL_QA_MODEL=google/gemini-2.5-flash

OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=google/gemini-2.5-flash
```

Real mode requires, at minimum:

- `LEGAL_QA_SERVICE_MODE=real`;
- a reachable Qdrant URL and existing compatible collection, selected through
  `LEGAL_QA_QDRANT_URL` and `LEGAL_QA_COLLECTION_NAME` or retrieval config;
- readable retrieval config, LLM config, and complete processed chunks JSONL;
- installed Qdrant and embedding optional dependencies;
- available BGE-M3 model files and sufficient CPU/RAM or a supported device;
- `OPENROUTER_API_KEY` and outbound HTTPS access to the selected provider.

`LEGAL_QA_MODEL` overrides the API runtime generation model.
`OPENROUTER_MODEL` is the provider-level fallback. `LEGAL_QA_DEVICE` selects
the query embedding device, not the LLM.

Important current behavior: `AppSettings.from_env()` reads the process
environment directly. It does not load `.env` before deciding
`LEGAL_QA_SERVICE_MODE`. The real workflow loads the project `.env` only after
real mode has already been selected. Therefore, export/inject backend settings
through the process or container environment; do not assume an un-sourced
`.env` alone selects real mode. This should be hardened before deployment.

### Frontend environment

```env
NEXT_PUBLIC_API_BASE_URL=https://api.example.invalid
```

This value is public and must never contain a secret. It is read by browser
code and embedded during the Next.js image build. Build each frontend image
with the final browser-reachable HTTPS API origin. Setting a different runtime
container environment value does not reliably replace the already compiled
client value.

The current code falls back to `http://localhost:8000` when the setting is
missing or blank. That is convenient locally but should become a production
configuration error or be replaced by a deliberate same-origin proxy design.

## Fake mode and real mode

### Fake mode

```env
LEGAL_QA_SERVICE_MODE=fake
```

Use fake mode for local UI/API contract smoke, request validation, CORS checks,
and deterministic tests. It must not call Qdrant, OpenRouter, embedding
models, rerankers, corpus pipelines, or evaluation workflows.

### Real mode

```env
LEGAL_QA_SERVICE_MODE=real
```

Real mode constructs:

1. a Qdrant async client and BGE-M3 query embedder;
2. dense retrieval from the existing named vector `dense`;
3. local BM25 from `data/processed/legal_chunks.jsonl`;
4. coverage-aware fusion and evidence selection;
5. an OpenRouter generation client with citation and fallback guards.

Real mode must use the existing collection read-only. Deployment must not
recreate collections, upsert points, re-index, or re-embed the corpus.

## Qdrant assumptions and gaps

- Expected collection: `vnlaw_chunks_bgem3_v1_full`.
- Expected points: 40,389.
- Dense vector: `dense`, dimension 1024, cosine distance.
- The Qdrant collection must already exist and match this contract.
- The API request path performs retrieval only; it should have no index-write
  authority.
- `build_qdrant_client()` currently accepts URL and timeout only. It does not
  pass a Qdrant API key. A secured remote Qdrant deployment therefore needs a
  narrowly scoped client/settings change or a private trusted network; do not
  expose an unauthenticated Qdrant port publicly.
- Readiness currently does not verify collection existence, schema, point
  count, or connectivity.

## OpenRouter assumptions and gaps

- The implemented real provider is OpenRouter through its OpenAI-compatible
  chat-completions API.
- `OPENROUTER_API_KEY` is read only when a generation request is made.
- Provider base URL and model are non-secret configuration.
- The request timeout is currently fixed at 30 seconds in API real-workflow
  construction.
- There is no deployment-level startup validation for a missing key and no
  readiness probe for provider configuration.
- Provider failures are sanitized by the API, but retry, circuit-breaker,
  concurrency, and cost controls are not deployment-hardened.

Other key names in `.env.example`, such as `OPENAI_API_KEY` and
`ANTHROPIC_API_KEY`, are not used by the current API real workflow.

## Health, readiness, and version status

`GET /health` is a deterministic process liveness endpoint. It must not be used
as proof that real Legal QA can serve requests. `GET /version` returns static
application metadata.

There is no separate readiness endpoint. A deployment-ready implementation
should distinguish:

- liveness: the API process can answer without external calls;
- readiness: required config/artifacts are present, real-mode dependencies can
  be initialized, and Qdrant is reachable with the expected collection
  contract;
- provider validation: avoid billable generation calls in routine readiness
  probes; validate credential presence/configuration without logging values.

Readiness must be bounded by short timeouts, return sanitized reasons, remain
read-only, and never trigger model downloads, indexing, or LLM generation.

## CORS and frontend origin notes

`CORS_ALLOWED_ORIGINS` is parsed as a comma-separated list. The default permits
only `http://localhost:3000`. Set exact HTTPS frontend origins for each
deployment. Do not use wildcard origins in production.

The frontend calls the API directly from the browser, so the configured API
URL must be browser-reachable; Docker service names are not valid public
browser destinations. HTTPS frontend deployments should use an HTTPS API to
avoid mixed-content failures.

## Container and Compose gaps

The existing files are intentionally fake-mode foundations:

- `docker/backend/Dockerfile` installs default dependencies only. It does not
  install the `qdrant` and `embedding` optional dependency groups.
- The backend image copies `src` and `configs`, but not the processed chunks
  file and not a model cache.
- `docker-compose.yml` fixes `LEGAL_QA_SERVICE_MODE=fake`, defines no Qdrant
  service or external Qdrant connection, injects no real-mode configuration,
  and builds the frontend against localhost.
- The Compose health check reaches liveness only.
- The containers do not define a non-root runtime user or production resource
  limits.

Do not add the legal corpus or model cache to the image casually. Prefer
explicit, read-only artifact mounts or a controlled artifact distribution
mechanism, with integrity/version checks and least-privilege access.

## Conversation persistence limitation

The conversation API repository is process-local and in memory. It disappears
on restart and is not shared across workers or replicas. There is no durable
server-side chat history unless a database-backed implementation is added.
There is also no authenticated user ownership boundary.

Frontend `localStorage` remains the rich UI source of truth and backend sync is
best-effort. Backend messages do not preserve the full evidence payload needed
for UI restoration. Multi-worker or autoscaled deployment would make current
conversation endpoints inconsistent; deploy a single worker only for
contract/demo use, or implement durable user-scoped persistence before relying
on server-side history.

Conversation context is retrieval-query assistance only. It is not legal
evidence, must not be cited, and raw context or prepared retrieval queries must
not be exposed in normal metadata or logs.

## Security and secret notes

- Keep provider credentials in a secret manager or injected process
  environment. Never use `NEXT_PUBLIC_*`, committed YAML, images, logs, docs,
  or reports for secrets.
- Do not log raw legal questions, prompts, conversation context, retrieval
  queries, full provider responses, chain-of-thought, authorization headers, or
  API keys.
- Qdrant should be private, authenticated where supported, and read-only from
  the API workload.
- Public deployment still needs authentication/authorization decisions, rate
  limiting, request/body limits at the proxy, trusted proxy/header handling,
  TLS termination, and dependency/resource limits.
- Swagger/OpenAPI exposure and error/log retention require an explicit
  deployment policy.
- A valid citation ID is necessary but does not prove semantic legal
  faithfulness or replace qualified legal review.

## Protected data paths

Deployment work must not mutate:

```text
data/raw/
data/interim/
data/reports/
data/processed/legal_chunks.jsonl
data/eval/
artifacts/reports/evaluation/
```

Mount `data/processed/legal_chunks.jsonl` read-only when real mode needs it.
Deployment startup and readiness must not crawl, clean, parse, embed, index, or
write evaluation artifacts.

## Known real-mode blockers

1. Define and validate production runtime configuration, including consistent
   `.env`/process-environment semantics and fail-fast real-mode checks.
2. Add a read-only, dependency-aware readiness contract separate from
   liveness.
3. Package/install real-mode dependency groups and provide the chunks/model
   artifacts without embedding protected data into source control.
4. Support secured Qdrant credentials/TLS requirements and verify the existing
   collection contract without mutation.
5. Make frontend production API URL configuration fail safely instead of
   silently targeting localhost.
6. Provide a real-mode container/deployment configuration; current Compose is
   fake-only.
7. Complete API security decisions and resource/concurrency controls.
8. Resolve process-local conversation behavior before multi-worker or
   multi-replica use, or explicitly exclude server-side history from the
   initial deployment.
9. Run a controlled real-mode smoke only after the above environment is
   reviewed and explicitly approved.

## Recommended implementation order

1. Harden backend runtime settings and startup validation. Keep fake mode the
   default, define required real-mode inputs, add secure Qdrant connection
   settings, and make configuration failures explicit without contacting
   providers.
2. Add separate liveness and read-only readiness behavior with targeted tests.
3. Harden frontend production API URL handling and document its build-time
   contract.
4. Build a real-mode backend image/deployment foundation with optional
   dependencies and read-only artifact mounts; retain the current fake-mode
   Compose workflow.
5. Add the minimum approved public-API security controls.
6. Perform deployment/security review, then execute one controlled low-risk
   real-mode smoke with citation and fallback checks.

The next implementation task should combine backend runtime configuration
hardening with the readiness contract, because container work cannot be
validated safely until required inputs and health semantics are explicit.

## Safe validation commands

These checks do not call real services:

```bash
git diff --check

grep -R "localhost\|127.0.0.1" -n \
  src apps/frontend docs README.md PROJECT_CONTEXT.md 2>/dev/null || true

grep -R \
  "OPENROUTER_API_KEY\|OPENAI_API_KEY\|ANTHROPIC_API_KEY\|HF_TOKEN" \
  -n src tests apps/frontend README.md PROJECT_CONTEXT.md AGENTS.md docs \
  apps/frontend/README.md 2>/dev/null || true

git diff --name-only -- \
  data/raw data/interim data/reports \
  data/processed/legal_chunks.jsonl data/eval
git diff --name-only -- artifacts/reports/evaluation

git status --short \
  .env apps/frontend/.env.local apps/frontend/.next \
  apps/frontend/node_modules .venv
```

For later code changes, run targeted API/service tests, Ruff, format checks,
`uv lock --check`, frontend lint/build when applicable, and
`docker compose config` plus image builds when Docker files change.

## Controlled real-mode smoke checklist

Do not execute this checklist without explicit approval and a reviewed
environment.

- [ ] Deployment/security review completed.
- [ ] Exact Qdrant endpoint, authentication, TLS, collection, and read-only
      access confirmed.
- [ ] Collection/vector contract and expected corpus version confirmed without
      writes.
- [ ] Processed chunks mounted read-only and integrity checked.
- [ ] Embedding dependency and model artifact/device availability confirmed.
- [ ] OpenRouter key injected from a secret store; value is not printed.
- [ ] CORS and final frontend API URL match the deployed HTTPS origins.
- [ ] Liveness and readiness pass with bounded, non-billable checks.
- [ ] Logs are sanitized and raw context/retrieval queries are absent.
- [ ] One low-risk Vietnamese legal research question is approved.
- [ ] Response contract, selected child evidence, citations, and fallback
      behavior are inspected.
- [ ] No Qdrant write, indexing, corpus mutation, or evaluation artifact write
      occurs.
- [ ] Provider usage is stopped/revoked after the smoke if credentials were
      temporary.
