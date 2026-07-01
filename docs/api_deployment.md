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
  - `GET /api/v1/readiness`;
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
| Service mode | Fake is safe by default; real config is validated before workflow construction | Real startup and one request still need controlled validation |
| Qdrant | URL, collection, optional API key, timeout, and vector contract exist | TLS/custom CA policy and deployed connectivity remain to be validated |
| Embedding and sparse retrieval | Real mode constructs BGE-M3 and loads the complete chunks JSONL | Model dependencies/cache and processed chunks are absent from the backend image |
| LLM provider | OpenRouter URL/model config and `OPENROUTER_API_KEY` lookup exist | Provider credential, egress, timeout/error behavior, and real response remain unverified |
| Health | `/health` is liveness; `/api/v1/readiness` validates config and optionally reads Qdrant collection metadata | Readiness deliberately does not validate LLM availability or load the embedding model |
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

QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=vnlaw_chunks_bgem3_v1_full
QDRANT_API_KEY=

OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=google/gemini-2.5-flash
```

Real mode requires, at minimum:

- `LEGAL_QA_SERVICE_MODE=real`;
- a reachable Qdrant URL and existing compatible collection, selected through
  `LEGAL_QA_QDRANT_URL`/`LEGAL_QA_COLLECTION_NAME` or the compatible
  `QDRANT_URL`/`QDRANT_COLLECTION` names;
- readable retrieval config, LLM config, and complete processed chunks JSONL;
- installed Qdrant and embedding optional dependencies;
- available BGE-M3 model files and sufficient CPU/RAM or a supported device;
- `OPENROUTER_API_KEY` and outbound HTTPS access to the selected provider.

`LEGAL_QA_MODEL` overrides the API runtime generation model.
`OPENROUTER_MODEL` is the provider-level fallback. `LEGAL_QA_DEVICE` selects
the query embedding device, not the LLM.

`AppSettings.from_env()` loads the project `.env` and then overlays process
environment values, so an exported/container value has precedence. Tests can
pass an explicit environment mapping and bypass local `.env` state.

Before the real workflow is constructed, validation requires the Qdrant URL,
collection, OpenRouter key, retrieval config, LLM config, and processed chunks
file. Failures contain safe issue codes only. Validation does not connect to
Qdrant, call OpenRouter, or load an embedding model.

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
- `QDRANT_API_KEY` is optional. `LEGAL_QA_QDRANT_API_KEY` is accepted as a
  backend-specific override. When configured, the value is passed to the
  Qdrant client and is never returned by readiness or included in settings
  representations. Local unauthenticated Qdrant remains supported.
- Real-mode readiness reads collection metadata with a short timeout. It
  verifies connectivity and collection availability only; it does not fully
  validate vector schema, point count, payload integrity, or corpus version.

## Qdrant Cloud migration audit

This section is an audit and manual checklist. No migration, snapshot,
embedding, indexing, upsert, retrieval, or Qdrant mutation was run while
preparing it.

### Current source and target facts

The local source collection was reported as:

```text
URL: http://localhost:6333
collection: vnlaw_chunks_bgem3_v1_full
status: green
optimizer_status: ok
points_count: 40,389
indexed_vectors_count: 40,012
named vector: dense
vector size: 1,024
distance: Cosine
segments_count: 4
on_disk_payload: true
update queue: empty
```

The input corpus is `data/processed/legal_chunks.jsonl` with 40,389 validated
rows. One legal chunk maps to one deterministic Qdrant point. The difference
between `points_count` and `indexed_vectors_count` does not by itself prove
missing points; verify collection status, point count, sampled vectors, and
optimizer state after migration.

The Qdrant Cloud cluster is reachable but currently has no collections. The
target collection must remain:

```text
vnlaw_chunks_bgem3_v1_full
```

Do not substitute the default
`vnlaw_chunks_bgem3_v1` from
`configs/indexing/embedding_indexing.yml`.

### Existing repository workflows

| Purpose | Existing entrypoint | Actual behavior |
| --- | --- | --- |
| Create/validate collection schema and payload indexes | `scripts/indexing/setup_qdrant_collection.py` | Calls `ensure_collection`; creates the named dense-vector schema and missing payload indexes, but never upserts points |
| Embed and upsert chunks | `scripts/indexing/index_qdrant_chunks.py` | Loads BGE-M3 for a real run and calls `IndexingService`, which batches `upsert(..., wait=True)` with deterministic UUIDv5 point IDs |
| Validate an existing index | `scripts/indexing/validate_qdrant_index.py` | Reads collection schema/count, samples points/vectors, and checks payload filters; retrieval sanity can be disabled to avoid loading BGE-M3 |

All three entrypoints call the shared
`src.indexing.qdrant_collection.build_qdrant_client`. The builder supports an
optional API key, but these three CLI entrypoints currently pass only URL and
timeout. They also do not read `QDRANT_URL`, `QDRANT_COLLECTION`, or
`QDRANT_API_KEY`; URL and collection must be supplied with CLI flags.

Therefore, the maintained indexing path does **not** currently support
authenticated Qdrant Cloud. The backend runtime and readiness paths do support
`QDRANT_API_KEY`, but that does not make the indexing CLIs authenticated.
Do not embed a key in a URL or command argument as a workaround. A separate
small code change and mock-only tests are required before using these CLIs
against Qdrant Cloud.

No repository script implements Qdrant collection snapshot creation, download,
upload, recovery, or the Qdrant Migration Tool.

### Environment variables

Local unauthenticated Qdrant:

```env
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=vnlaw_chunks_bgem3_v1_full
QDRANT_API_KEY=
```

Qdrant Cloud:

```env
QDRANT_URL=https://your-cluster.example.cloud.qdrant.io
QDRANT_COLLECTION=vnlaw_chunks_bgem3_v1_full
QDRANT_API_KEY=
```

Inject the Cloud key from a private shell, Render secret environment setting,
or another secret manager. Never commit it, print it, paste it into docs, put
it in a URL, or use a `NEXT_PUBLIC_*` variable.

The backend also accepts `LEGAL_QA_QDRANT_URL`,
`LEGAL_QA_COLLECTION_NAME`, and `LEGAL_QA_QDRANT_API_KEY` as higher-priority
aliases. The indexing CLIs do not currently consume either naming family.

### Safe connectivity and metadata verification

The following commands are read-only but were **not run** during this audit.
They use environment placeholders only.

List Cloud collections:

```bash
curl --fail --silent --show-error \
  -H "api-key: $QDRANT_API_KEY" \
  "$QDRANT_URL/collections"
```

Inspect the target Cloud collection:

```bash
curl --fail --silent --show-error \
  -H "api-key: $QDRANT_API_KEY" \
  "$QDRANT_URL/collections/vnlaw_chunks_bgem3_v1_full"
```

Inspect the local source:

```bash
curl --fail --silent --show-error \
  http://localhost:6333/collections/vnlaw_chunks_bgem3_v1_full
```

After migration, inspect the Cloud response and require:

- collection name `vnlaw_chunks_bgem3_v1_full`;
- status acceptable and eventually `green`;
- named vector `dense`;
- vector size `1024`;
- distance `Cosine`;
- `points_count == 40389`;
- no unexpected sparse vector;
- these payload indexes in `payload_schema`:
  - `law_id` (`keyword`);
  - `chunk_kind` (`keyword`);
  - `level` (`keyword`);
  - `metadata.is_empty_or_repealed` (`bool`);
  - `metadata.is_source_unit_repealed` (`bool`);
  - `source_domain` (`keyword`);
  - `article_number` (`keyword`).

Point count and schema are necessary but not sufficient. A later approved
validation should sample payloads and vectors and compare deterministic
`chunk_id`/point IDs. `indexed_vectors_count` may lag `points_count` while
optimization runs, so record it and optimizer status rather than treating
temporary inequality as automatic data loss.

The maintained validator is appropriate after API-key wiring. This is a
read-only schema/payload/vector check with retrieval sanity disabled:

```bash
# NOT RUN; currently blocked for Qdrant Cloud because the CLI does not pass
# QDRANT_API_KEY to the shared client builder.
uv run --extra qdrant python scripts/indexing/validate_qdrant_index.py \
  --config configs/indexing/embedding_indexing.yml \
  --url "$QDRANT_URL" \
  --collection-name "$QDRANT_COLLECTION" \
  --dense-vector-name dense \
  --dense-dimension 1024 \
  --expected-distance Cosine \
  --expected-min-points 40389 \
  --sample-limit 10 \
  --skip-retrieval-sanity \
  --output /tmp/vnlaw_qdrant_cloud_validation.json
```

### Preferred option: manual snapshot transfer

Qdrant documents collection snapshots as a way to move a self-hosted
collection to Qdrant Cloud without recomputing embeddings or rebuilding the
index. A collection snapshot includes its configuration, points, payloads, and
pre-built index. Qdrant Cloud Free clusters support manual snapshots and
restores through the API.

This is the preferred path if all of the following are confirmed first:

- source and target Qdrant versions satisfy snapshot compatibility; Qdrant
  requires the same minor version, with the target patch version at least the
  source patch version;
- the snapshot and its temporary restore footprint fit Cloud disk and memory
  limits with headroom;
- the target collection is absent;
- the local collection is quiescent and healthy;
- the rotated Cloud API key is available only through a secret environment
  variable.

Manual high-level checklist (**NOT RUN**):

1. Record local and Cloud Qdrant versions, source collection metadata, payload
   indexes, and counts.
2. Stop all writes to the local source collection.
3. Request a local collection snapshot with
   `POST /collections/vnlaw_chunks_bgem3_v1_full/snapshots`.
4. Download the generated snapshot to a protected temporary location and
   record its byte size and checksum. Do not commit it.
5. Confirm the Cloud target collection is absent and the cluster has enough
   free disk/RAM for upload, extraction, and optimization.
6. Upload the snapshot to the Cloud collection snapshot endpoint with
   `priority=snapshot`. Qdrant creates the absent collection during recovery.
7. Wait for recovery/optimization to finish; do not start Render traffic.
8. Run the read-only metadata, count, payload-index, and sampled-point checks.
9. Remove temporary snapshot files after verification according to the
   approved retention policy.

Reference mutation commands, provided only for a separately approved manual
operation:

```bash
# NOT RUN: create a local collection snapshot.
curl --fail --silent --show-error -X POST \
  http://localhost:6333/collections/vnlaw_chunks_bgem3_v1_full/snapshots

# NOT RUN: upload and recover an already downloaded snapshot into Cloud.
curl --fail --silent --show-error -X POST \
  -H "api-key: $QDRANT_API_KEY" \
  -H "Content-Type: multipart/form-data" \
  -F "snapshot=@/private/path/to/collection.snapshot" \
  "$QDRANT_URL/collections/vnlaw_chunks_bgem3_v1_full/snapshots/upload?priority=snapshot"
```

Cloud restore from an external URL is not supported because outbound traffic
from Qdrant Cloud is blocked; use uploaded snapshot data. Startup snapshot
restore is also unavailable in Qdrant Cloud.

Official references:

- [Qdrant snapshots and restore](https://qdrant.tech/documentation/operations/snapshots/)
- [Qdrant migration and recovery options](https://qdrant.tech/documentation/migration-recovery-options/)
- [Qdrant Cloud free-cluster resources](https://qdrant.tech/documentation/cloud/create-cluster/)

### Fallback option: rebuild and upsert

Rebuild is slower and more operationally risky because it loads BGE-M3,
recomputes all 40,389 embeddings, transfers every payload, and builds the
Cloud index. Use it only if snapshot compatibility/capacity fails or an
explicit rebuild is preferred.

The manual order would be:

1. Add `QDRANT_API_KEY` support to all three indexing CLI client-construction
   calls and cover present/absent-key behavior with mocks.
2. Verify processed-corpus validation and immutable input hashes.
3. Create the empty Cloud collection with `dense`, size 1024, Cosine, no
   sparse vector, and the seven payload indexes.
4. Run a small explicitly bounded pilot and validate it.
5. Run the full resumable indexing command with a private checkpoint and
   report outside protected data paths.
6. Reconcile counts, inspect failed chunk IDs, and retry only failed batches.
7. Run read-only schema, sampled payload/vector, filter, and count validation.
8. Enable backend traffic only after all checks pass.

Likely maintained commands (**NOT RUN and not Cloud-ready until API-key wiring
is implemented**):

```bash
# NOT RUN: creates/validates schema and payload indexes; mutates Qdrant.
uv run --extra qdrant python scripts/indexing/setup_qdrant_collection.py \
  --config configs/indexing/embedding_indexing.yml \
  --url "$QDRANT_URL" \
  --collection-name "$QDRANT_COLLECTION" \
  --dense-vector-name dense \
  --dense-dimension 1024 \
  --distance Cosine

# NOT RUN: loads BGE-M3, embeds the full corpus, and upserts Qdrant.
uv run --extra qdrant --extra embedding \
  python scripts/indexing/index_qdrant_chunks.py \
  --input data/processed/legal_chunks.jsonl \
  --config configs/indexing/embedding_indexing.yml \
  --url "$QDRANT_URL" \
  --collection-name "$QDRANT_COLLECTION" \
  --processed-validation-report /private/path/processed_validation_report.json \
  --allow-full-corpus \
  --run-type official_full_indexing \
  --checkpoint /private/path/qdrant_cloud_indexing_checkpoint.json \
  --max-retries 3 \
  --reconcile-counts \
  --output /tmp/vnlaw_qdrant_cloud_indexing_report.json
```

Never use `--recreate` against the local source or Cloud target without a
separately reviewed destructive operation.

### Qdrant Cloud Free Tier risks

As of the documentation checked for this audit, a free cluster provides one
node, 1 GB RAM, 0.5 vCPU, and 4 GB disk. It is intended for prototyping, has no
dedicated resources, and supports only manual snapshot/restore. Inactive free
clusters may be suspended after one week and deleted after four weeks if not
reactivated.

The raw float32 dense vectors alone are approximately 158 MiB
(`40389 * 1024 * 4` bytes), but this is not a capacity estimate. Payload text
and repeated `parent_text`, HNSW/index structures, segment metadata, WAL,
snapshot upload/extraction, optimizer work, and operational headroom can
dominate storage and RAM. The reported local `on_disk_payload=true` does not
guarantee the Cloud collection fits or performs acceptably.

Before mutation, record local collection/snapshot size and compare it with
actual Cloud free disk/RAM metrics. Do not proceed if restore/indexing would
approach limits. A streaming migration or rebuild can require substantial
temporary resources; Qdrant's migration guidance warns that the Migration Tool
may require roughly twice the source collection's RAM and disk during
migration. Upgrade the cluster rather than weakening payload traceability,
dropping citation metadata, or reducing safety fields to force a fit.

### Render startup boundary

Render startup must only start the FastAPI service. It must never:

- create, recreate, restore, or delete a Qdrant collection;
- create/download/upload snapshots;
- run `setup_qdrant_collection.py`, `index_qdrant_chunks.py`, or the Qdrant
  Migration Tool;
- load BGE-M3 to rebuild vectors;
- upsert or update payloads;
- crawl, process, validate, or rewrite corpus artifacts;
- run retrieval/generation evaluations.

Migration is a separately approved, one-time operator action. Render real-mode
readiness may perform its existing bounded `get_collection` metadata read, but
startup must not turn readiness into migration or indexing.

## OpenRouter assumptions and gaps

- The implemented real provider is OpenRouter through its OpenAI-compatible
  chat-completions API.
- `OPENROUTER_API_KEY` presence is validated before workflow construction; the
  credential value is used only when the generation client sends a request.
- Provider base URL and model are non-secret configuration.
- The request timeout is currently fixed at 30 seconds in API real-workflow
  construction.
- Real-mode configuration validation requires the key to be present before
  workflow construction. Readiness checks presence only and never sends a
  provider request.
- Provider failures are sanitized by the API, but retry, circuit-breaker,
  concurrency, and cost controls are not deployment-hardened.

Other key names in `.env.example`, such as `OPENAI_API_KEY` and
`ANTHROPIC_API_KEY`, are not used by the current API real workflow.

## Health, readiness, and version status

`GET /health` is a deterministic process liveness endpoint. It must not be used
as proof that real Legal QA can serve requests. `GET /version` returns static
application metadata.

`GET /api/v1/readiness` distinguishes runtime readiness:

- liveness: the API process can answer without external calls;
- fake readiness: configuration is valid without Qdrant, provider credentials,
  chunks, or models;
- real readiness: required settings and local artifact paths are present, then
  the configured Qdrant collection metadata is readable.

The endpoint returns 200 when ready and 503 otherwise. Failure details are
stable operational codes such as `missing_openrouter_api_key` or the sanitized
Qdrant status `unavailable`. It does not return credentials, exception text,
or internal paths. It never calls the LLM, runs retrieval/generation, loads an
embedding model, downloads model files, or mutates Qdrant.

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

1. Package/install real-mode dependency groups and provide the chunks/model
   artifacts without embedding protected data into source control.
2. Define deployed Qdrant TLS/custom CA policy and extend readiness if full
   schema/corpus-version verification is required.
3. Make frontend production API URL configuration fail safely instead of
   silently targeting localhost.
4. Provide a real-mode container/deployment configuration; current Compose is
   fake-only.
5. Complete API security decisions and resource/concurrency controls.
6. Resolve process-local conversation behavior before multi-worker or
   multi-replica use, or explicitly exclude server-side history from the
   initial deployment.
7. Run a controlled real-mode smoke only after the above environment is
   reviewed and explicitly approved.

## Recommended implementation order

1. Build a real-mode backend image/deployment foundation with optional
   dependencies and read-only artifact mounts; retain the current fake-mode
   Compose workflow.
2. Harden frontend production API URL handling and document its build-time
   contract.
3. Add the minimum approved public-API security controls.
4. Perform deployment/security review, then execute one controlled low-risk
   real-mode smoke with citation and fallback checks.

The next implementation task should build the Docker/Compose real-mode
foundation because runtime inputs and readiness semantics are now explicit.

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
