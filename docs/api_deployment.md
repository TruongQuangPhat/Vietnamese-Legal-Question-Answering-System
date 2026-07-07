# API Deployment Readiness

## Purpose and current status

VnLaw-QA is a Vietnamese legal research assistant, not legal advice. The
current product includes a fake-mode Legal QA chat MVP and a real-workflow
adapter. The Qdrant collection has been restored to Qdrant Cloud and validated,
and the backend and frontend are deployed. Infrastructure readiness passes,
but real QA requests exceed the Render Free memory limit; the system is not
production-ready.

The deployed backend remains in real mode. Do not describe the system as
production-ready until the runtime memory blocker, deployment/security review,
and a controlled real-mode QA smoke have been completed.

The API and deployment infrastructure work is closed with this memory
limitation documented. Follow-up quality work must not loosen fallback,
evidence-selection, or citation gates merely to make deployment smoke pass.

This document records the repository state as audited without calling Qdrant,
OpenRouter, embedding inference, or evaluation workflows.

## Production deployment runbook

### Current services

```text
Backend (Render): https://vnlaw-qa-backend.onrender.com
Frontend (Vercel): https://vnlaw-qa.vercel.app
Backend mode: LEGAL_QA_SERVICE_MODE=real
Qdrant collection: vnlaw_chunks_bgem3_v1_full
```

Keep the backend in real mode. Do not switch production to fake mode to conceal
the Render Free memory limitation.

### Render backend

Create a native Python Web Service from the repository root.

Build command:

```bash
python -m pip install --no-cache-dir uv && \
  uv sync --frozen --no-dev --extra qdrant --extra embedding && \
  python scripts/deployment/fetch_processed_chunks.py
```

Start command:

```bash
uv run python -m uvicorn src.api.app:app --host 0.0.0.0 --port $PORT
```

Render supplies `PORT`. Configure `/health` as the service health-check path.
Use one Uvicorn worker while conversation storage remains process-local.

Required Render environment values:

```env
LEGAL_QA_SERVICE_MODE=real
APP_ENV=production
LOG_LEVEL=INFO
LOG_FORMAT=json

QDRANT_URL=<Qdrant Cloud endpoint>
QDRANT_COLLECTION=vnlaw_chunks_bgem3_v1_full
QDRANT_API_KEY=<Render secret>

LEGAL_QA_COLLECTION_NAME=vnlaw_chunks_bgem3_v1_full
LEGAL_QA_QDRANT_URL=<same Qdrant Cloud endpoint>
LEGAL_QA_RETRIEVAL_CONFIG=configs/retrieval/retrieval.yml
LEGAL_QA_LLM_CONFIG=configs/llm/openrouter.yml
LEGAL_QA_DEVICE=cpu
LEGAL_QA_MODEL=google/gemini-2.5-flash
LEGAL_QA_RATE_LIMIT_ENABLED=true
LEGAL_QA_RATE_LIMIT_REQUESTS=10
LEGAL_QA_RATE_LIMIT_WINDOW_SECONDS=60

LEGAL_QA_CHUNKS_URL=https://huggingface.co/datasets/phattruong1802/vnlaw-qa/resolve/main/legal_chunks/v1/legal_chunks.jsonl
LEGAL_QA_CHUNKS_SHA256=95ff0129915ad4e77306fbdaa2c6eb8c7a7c58730cd21050aec429541416b30c
LEGAL_QA_CHUNKS_PATH=data/processed/legal_chunks.jsonl

OPENROUTER_API_KEY=<Render secret>
OPENROUTER_MODEL=google/gemini-2.5-flash
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

CORS_ALLOWED_ORIGINS=["https://vnlaw-qa.vercel.app"]
HF_TOKEN=
```

`HF_TOKEN` is not required for the current public chunks artifact. If the
dataset becomes private, store the token as a Render secret. Never put Qdrant,
OpenRouter, or Hugging Face credentials in Git, build commands, frontend
variables, or logs.

### Vercel frontend

Configure the Vercel project with:

```text
Framework preset: Next.js
Root Directory: apps/frontend
Production URL: https://vnlaw-qa.vercel.app
```

Set this production environment variable before building:

```env
NEXT_PUBLIC_API_BASE_URL=https://vnlaw-qa-backend.onrender.com
```

`NEXT_PUBLIC_API_BASE_URL` is browser-visible and must contain only the public
backend origin. Redeploy the frontend after changing it because Next.js embeds
the value during build. The matching backend CORS value is:

```env
CORS_ALLOWED_ORIGINS=["https://vnlaw-qa.vercel.app"]
```

### Qdrant Cloud and chunks artifact

Normal deployed serving uses Qdrant Cloud directly and expects collection
`vnlaw_chunks_bgem3_v1_full`. The collection has 40,389 indexed points with
named vector `dense`, dimension 1024, and cosine distance.

Render fetches `legal_chunks/v1/legal_chunks.jsonl` from the public
`phattruong1802/vnlaw-qa` Hugging Face Dataset during build. The fetch script
must verify this pinned SHA256 before installing the file:

```text
95ff0129915ad4e77306fbdaa2c6eb8c7a7c58730cd21050aec429541416b30c
```

The deployed app does not require local Docker or a local Qdrant instance.
Local Docker/Qdrant is only for separately approved local indexing, snapshot
or restore operations, and local retrieval debugging.

### Infrastructure smoke

These read-only commands verify deployed infrastructure without invoking real
QA generation:

```bash
curl -fsS https://vnlaw-qa-backend.onrender.com/health
curl -fsS https://vnlaw-qa-backend.onrender.com/api/v1/readiness
```

Expected status:

- `/health` returns `{"status":"ok"}`;
- `/api/v1/readiness` returns `ready=true`, `service_mode=real`, valid
  configuration, and Qdrant `collection_available`.

Do not treat readiness as proof that BGE-M3 can fit in memory. Do not call
`POST /api/v1/legal-qa/ask` on Render Free: BGE-M3, Torch, and Transformers
exceed the 512 MB memory limit and real QA serving is not reliable there.

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
- Real-mode answer decisions now distinguish `answered`, `answered_with_caution`,
  and `fallback`. Caution answers still require selected citable evidence and
  valid citation IDs; no-evidence cases remain fallback and do not call the LLM.
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
| Embedding and sparse retrieval | Real mode constructs BGE-M3 and loads the complete chunks JSONL | Model cache and processed chunks are absent from committed deployment sources |
| LLM provider | OpenRouter URL/model config and `OPENROUTER_API_KEY` lookup exist | Provider credential, egress, timeout/error behavior, and real response remain unverified |
| Health | `/health` is liveness; `/api/v1/readiness` validates config and optionally reads Qdrant collection metadata | Readiness deliberately does not validate LLM availability or load the embedding model |
| Version | Static API name/version is exposed | It has no build or revision identity |
| CORS | JSON-array origins are supported; legacy comma-separated values remain compatible | Deployed frontend origins must be supplied explicitly |
| Frontend API URL | One public base URL is used by both clients | It is embedded during `next build`; localhost fallback is unsafe for an omitted production setting |
| Containers | Fake-mode images and Compose stack build the MVP | Committed stack does not package or configure real mode |
| Conversation storage | Process-local in-memory repository | Not durable, not shared across workers, and not user-specific |
| API security | Input bounds, sanitized errors, and optional in-process `/api/v1/legal-qa/ask` rate limiting exist | Authentication, authorization, trusted proxy policy, and distributed abuse controls are not implemented |
| Observability | Safe completion/failure metadata is logged | Production logging configuration, metrics, tracing, and alerting are not established |

## Runtime configuration

### Backend process environment

Current API settings:

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
LEGAL_QA_RATE_LIMIT_ENABLED=false
LEGAL_QA_RATE_LIMIT_REQUESTS=10
LEGAL_QA_RATE_LIMIT_WINDOW_SECONDS=60

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

`LEGAL_QA_RATE_LIMIT_ENABLED=true` enables a lightweight in-process fixed-window
limiter on `POST /api/v1/legal-qa/ask`. `LEGAL_QA_RATE_LIMIT_REQUESTS` sets the
number of allowed requests per client key, and
`LEGAL_QA_RATE_LIMIT_WINDOW_SECONDS` sets the window size. Exceeded requests
return HTTP 429 with a `Retry-After` header and do not call the Legal QA
workflow. `/health` and `/api/v1/readiness` are not rate limited. This is
appropriate for the current single-process Render deployment; a future
multi-instance deployment should use shared infrastructure such as an API
gateway, WAF, or Redis-backed limiter.

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

The snapshot migration has since completed. The Qdrant Cloud target collection
is green with 40,389 points and 40,389 indexed vectors; the named vector is
`dense`, size 1,024, with cosine distance. The collection name remains:

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
optional API key. Each CLI now resolves `QDRANT_API_KEY`, normalizes blank
values to no key, and passes the result to the builder. An explicit
`--qdrant-api-key` takes precedence, including an explicit blank value that
disables authentication. Prefer the environment variable because CLI
arguments may be retained in shell history or process listings.

The CLIs still do not read `QDRANT_URL` or `QDRANT_COLLECTION`; URL and
collection must be supplied with `--url` and `--collection-name`. Local
unauthenticated Qdrant remains supported when no key is configured.

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
`QDRANT_API_KEY` is required for authenticated Qdrant Cloud and optional for
local unauthenticated Qdrant.
Run manual commands from a private shell with tracing disabled; never use
`set -x`, echo the key, or paste the literal key into a command. Header examples
reference the environment variable, but the expanded header may still be
briefly visible to local process inspection, so restrict host/session access
and rotate temporary credentials after the operation.

The backend also accepts `LEGAL_QA_QDRANT_URL`,
`LEGAL_QA_COLLECTION_NAME`, and `LEGAL_QA_QDRANT_API_KEY` as higher-priority
aliases. The indexing CLIs intentionally consume only `QDRANT_API_KEY` for
authentication and do not consume the backend-specific key alias.

### Safe connectivity and metadata verification

The following commands are read-only but were **not run** during this audit.
They use environment placeholders only.

Check the local and Cloud Qdrant versions:

```bash
# NOT RUN by Codex: read-only local version check.
curl --fail --silent --show-error http://localhost:6333/

# NOT RUN by Codex: read-only Cloud version check.
curl --fail --silent --show-error \
  -H "api-key: $QDRANT_API_KEY" \
  "$QDRANT_URL/"
```

List Cloud collections:

```bash
# NOT RUN by Codex: read-only Cloud collection listing.
curl --fail --silent --show-error \
  -H "api-key: $QDRANT_API_KEY" \
  "$QDRANT_URL/collections"
```

Inspect the target Cloud collection:

```bash
# NOT RUN by Codex: read-only; a 404 is expected before restore.
curl --fail --silent --show-error \
  -H "api-key: $QDRANT_API_KEY" \
  "$QDRANT_URL/collections/vnlaw_chunks_bgem3_v1_full"
```

Inspect the local source:

```bash
# NOT RUN by Codex: read-only local collection metadata.
curl --fail --silent --show-error \
  http://localhost:6333/collections/vnlaw_chunks_bgem3_v1_full
```

Before creating anything, record both version strings and the complete local
collection response. Do not infer snapshot compatibility from the client
library version or Docker image tag alone; compare the server versions returned
by these endpoints.

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
# NOT RUN: read-only Cloud validation; requires QDRANT_API_KEY in the
# environment and explicit URL/collection flags.
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

Snapshot/restore is preferred for this collection because the local source is
already healthy and fully populated, the Cloud target is empty, and the
snapshot preserves the existing point IDs, vectors, payloads, collection
configuration, and pre-built index. It avoids recomputing 40,389 BGE-M3
embeddings. This preference is conditional, not approval to run it.

This is the preferred path if all of the following are confirmed first:

- source and target Qdrant server versions satisfy snapshot compatibility;
- the downloaded snapshot size and estimated restored collection fit Cloud
  disk and memory limits with substantial headroom;
- the target collection is absent;
- the local collection is quiescent and healthy;
- the rotated Cloud API key is available only through a secret environment
  variable.

Qdrant's snapshot reference specifies the same minor version, with the target
patch version no older than the source. Its newer migration guidance says a
target may be at most one minor version higher. Use the same minor version as
the conservative gate. If Cloud is one minor newer, stop and confirm support
for the exact source/target versions before upload; never attempt a snapshot
from a newer source into an older target.

Manual high-level checklist (**NOT RUN**):

1. Record local and Cloud Qdrant versions, source collection metadata, payload
   indexes, and counts.
2. Stop all writes to the local source collection.
3. Confirm the local snapshot storage has enough free disk for snapshot and
   temporary files.
4. Request a local collection snapshot with
   `POST /collections/vnlaw_chunks_bgem3_v1_full/snapshots`.
5. List snapshots and record the returned name and reported byte size.
6. Download the generated snapshot to a private temporary location and
   record its byte size and checksum. Do not commit it.
7. Confirm the downloaded byte size matches the API metadata and preserve the
   checksum for transfer verification.
8. Confirm the Cloud target collection is absent and the cluster has enough
   free disk/RAM for upload, extraction, and optimization. Qdrant estimates
   approximately twice the collection disk size is needed during restore
   because the uploaded snapshot and restored collection coexist.
9. Upload the snapshot to the Cloud collection snapshot endpoint with
   `priority=snapshot`. Qdrant creates the absent collection during recovery.
10. Wait for recovery/optimization to finish; do not start Render traffic.
11. Run the read-only metadata, count, payload-index, and sampled-point checks.
12. Remove temporary snapshot files after verification according to the
   approved retention policy.

Manual local commands are shown below for a separately approved operation.
Codex did **not** run any of them:

```bash
# NOT RUN: create a local collection snapshot.
curl --fail --silent --show-error -X POST \
  http://localhost:6333/collections/vnlaw_chunks_bgem3_v1_full/snapshots

# NOT RUN: list local snapshots and read the returned name/size metadata.
curl --fail --silent --show-error \
  http://localhost:6333/collections/vnlaw_chunks_bgem3_v1_full/snapshots

# NOT RUN: download the named local snapshot to a private temporary path.
SNAPSHOT_NAME="<snapshot-name-returned-by-qdrant>"
SNAPSHOT_PATH="/tmp/$SNAPSHOT_NAME"
curl --fail --silent --show-error \
  "http://localhost:6333/collections/vnlaw_chunks_bgem3_v1_full/snapshots/$SNAPSHOT_NAME" \
  --output "$SNAPSHOT_PATH"

# NOT RUN: measure and checksum the downloaded snapshot without modifying it.
stat --format='%n %s bytes' "$SNAPSHOT_PATH"
du --human-readable "$SNAPSHOT_PATH"
sha256sum "$SNAPSHOT_PATH"
```

Snapshot creation is a local Qdrant write-like administrative operation and
requires explicit approval. Listing, downloading, `stat`, `du`, and
`sha256sum` are read-only, but only become useful after an approved snapshot
exists. Store snapshots outside the repository and protected corpus/artifact
paths.

The Cloud restore command is a mutation and requires separate explicit
approval. Codex did **not** run it:

```bash
# NOT RUN: upload and recover an already downloaded snapshot into Cloud.
curl --fail --silent --show-error -X POST \
  -H "api-key: $QDRANT_API_KEY" \
  -H "Content-Type: multipart/form-data" \
  -F "snapshot=@${SNAPSHOT_PATH}" \
  "$QDRANT_URL/collections/vnlaw_chunks_bgem3_v1_full/snapshots/upload?priority=snapshot"
```

Use `priority=snapshot` for an absent target collection. Do not pre-create the
target collection and do not use `replica` priority for this migration:
Qdrant warns that the default replica priority can prefer the empty target
state. Never use `no_sync` for this workflow.

Cloud restore from an external URL is not supported because outbound traffic
from Qdrant Cloud is blocked; use uploaded snapshot data. Startup snapshot
restore is also unavailable in Qdrant Cloud.

### Post-restore acceptance checklist

Do not route Render traffic until all checks pass:

1. Confirm the target collection exists and eventually reports `green`,
   `optimizer_status=ok`, and an empty update queue.
2. Confirm named vector `dense`, size 1024, distance `Cosine`, and no
   unexpected sparse vector.
3. Require `points_count == 40389`. Record `indexed_vectors_count`; allow it to
   converge while optimization runs, but investigate persistent mismatch or
   non-green status.
4. Confirm all seven expected payload indexes and their types.
5. Run the maintained validator with `--skip-retrieval-sanity`; inspect its
   sampled payload/vector and filter results. This is a real Cloud read and
   should be run only after migration approval.
6. Compare selected deterministic point IDs, `chunk_id`, hashes, citations,
   source URLs, hierarchy metadata, `text`, and `parent_text` with the local
   source.
7. Confirm readiness returns ready in the intended backend environment without
   exposing credentials.
8. Retain the snapshot checksum and migration record, then remove temporary
   snapshot files according to the approved retention policy.

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

1. Inject `QDRANT_API_KEY` through a private environment and verify it is not
   present in command history, logs, reports, or process arguments.
2. Verify processed-corpus validation and immutable input hashes.
3. Create the empty Cloud collection with `dense`, size 1024, Cosine, no
   sparse vector, and the seven payload indexes.
4. Run a small explicitly bounded pilot and validate it.
5. Run the full resumable indexing command with a private checkpoint and
   report outside protected data paths.
6. Reconcile counts, inspect failed chunk IDs, and retry only failed batches.
7. Run read-only schema, sampled payload/vector, filter, and count validation.
8. Enable backend traffic only after all checks pass.

Maintained commands (**NOT RUN; Qdrant mutation requires separate approval**):

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
approach limits. Qdrant's current migration guidance says snapshot restore
needs approximately twice the collection disk size during the restore window
because the snapshot and restored collection coexist. A snapshot near or above
2 GB is therefore an immediate 4 GB Free Tier warning even before operational
headroom; smaller snapshots can still fail because snapshot size is not equal
to peak restored disk or RAM.

Warning signs include insufficient disk errors, upload/restore rejection,
cluster restart or suspension, prolonged yellow/red status, optimizer backlog,
memory pressure, slow or failed indexing, and inability for
`indexed_vectors_count` to stabilize. Upgrade the cluster rather than weakening
payload traceability, dropping citation metadata, or reducing safety fields to
force a fit.

### Command approval boundary

Safe pre-migration read-only commands, provided they use placeholders and do
not print secret values:

- local/Cloud root version checks;
- local/Cloud collection listing and metadata reads;
- local snapshot listing;
- local filesystem `stat`, `du`, and `sha256sum` for an already approved
  snapshot file;
- `git diff`, secret-reference, ignored-file, and protected-path checks.

Commands requiring explicit approval:

- snapshot creation or deletion;
- snapshot upload/recovery;
- target collection create, recreate, or delete;
- setup, indexing, upsert, payload update, or Qdrant Migration Tool;
- real Cloud sampled validation or retrieval;
- embedding model loading and full evaluation.

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

`CORS_ALLOWED_ORIGINS` should be a JSON array string in deployed environments:

```env
CORS_ALLOWED_ORIGINS='["https://your-vercel-app.vercel.app"]'
```

Legacy comma-separated values remain supported for compatibility. The default
permits only `http://localhost:3000`. Set exact HTTPS frontend origins for each
deployment. Do not use wildcard origins in production. Invalid JSON arrays
fail configuration loading instead of silently configuring the wrong origin.

The frontend calls the API directly from the browser, so the configured API
URL must be browser-reachable; Docker service names are not valid public
browser destinations. HTTPS frontend deployments should use an HTTPS API to
avoid mixed-content failures.

## Render backend preparation

### Chosen strategy

Use a **native Render Python Web Service**, configured manually in the Render
dashboard. Do not apply a Blueprint or deploy yet.

This is the smallest auditable path because Render can install the locked
`qdrant` and `embedding` dependency groups directly and can expand its `PORT`
environment variable in the start command. The existing backend Dockerfile and
Compose stack intentionally remain fake-mode local packaging. Converting that
image would not solve the current real-mode artifact blocker:
`SparseBM25Retriever` requires the complete processed chunks JSONL, which is
ignored by Git and excluded from the Docker build context.

Render service settings:

```text
Service type: Web Service
Runtime: Python
Root directory: repository root
Build command: python -m pip install --no-cache-dir uv && uv sync --frozen --no-dev --extra qdrant --extra embedding && python scripts/deployment/fetch_processed_chunks.py
Start command: uv run python -m uvicorn src.api.app:app --host 0.0.0.0 --port $PORT
Health check path: /health
```

`/health` is suitable for Render process health checks. Check
`/api/v1/readiness` separately during deployment review because it can return
503 when configuration, the local chunks artifact, or the read-only Qdrant
metadata check is unavailable.

Required Render environment configuration:

```env
LEGAL_QA_SERVICE_MODE=real
APP_ENV=production
LOG_LEVEL=INFO
LOG_FORMAT=json

QDRANT_URL=https://your-qdrant-cloud-endpoint
QDRANT_COLLECTION=vnlaw_chunks_bgem3_v1_full
QDRANT_API_KEY=

LEGAL_QA_COLLECTION_NAME=vnlaw_chunks_bgem3_v1_full
LEGAL_QA_QDRANT_URL=https://your-qdrant-cloud-endpoint
LEGAL_QA_RETRIEVAL_CONFIG=configs/retrieval/retrieval.yml
LEGAL_QA_LLM_CONFIG=configs/llm/openrouter.yml
LEGAL_QA_CHUNKS_URL=https://huggingface.co/datasets/phattruong1802/vnlaw-qa/resolve/main/legal_chunks/v1/legal_chunks.jsonl
LEGAL_QA_CHUNKS_SHA256=95ff0129915ad4e77306fbdaa2c6eb8c7a7c58730cd21050aec429541416b30c
LEGAL_QA_CHUNKS_PATH=data/processed/legal_chunks.jsonl
LEGAL_QA_DEVICE=cpu
LEGAL_QA_MODEL=google/gemini-2.5-flash
LEGAL_QA_RATE_LIMIT_ENABLED=true
LEGAL_QA_RATE_LIMIT_REQUESTS=10
LEGAL_QA_RATE_LIMIT_WINDOW_SECONDS=60

OPENROUTER_API_KEY=
OPENROUTER_MODEL=google/gemini-2.5-flash
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

CORS_ALLOWED_ORIGINS=["https://your-vercel-app.vercel.app"]
HF_TOKEN=
```

For local browser testing, use
`CORS_ALLOWED_ORIGINS=["http://localhost:3000"]`. In a shell or `.env`, quote
the complete JSON value when needed to prevent shell interpretation; in the
Render dashboard, enter the JSON array itself.

Store `QDRANT_API_KEY` and `OPENROUTER_API_KEY` as secret environment values,
never in Git or Render command fields. `HF_TOKEN` is optional for the public
chunks artifact and public BGE-M3 model. If either becomes private or gated,
inject the token as a secret. The duplicated generic and backend-specific
Qdrant variables make the selected values explicit; the backend-specific
values take precedence.

`LOG_FORMAT=json` is retained as the intended deployment convention, but the
current FastAPI bootstrap does not yet wire `LOG_FORMAT` into a production
logging initializer. Treat structured logging as a remaining hardening item,
not as a verified behavior.

### Processed chunks build artifact

The public Hugging Face Dataset artifact is the checksum-pinned build input:

```text
dataset: phattruong1802/vnlaw-qa
artifact: legal_chunks/v1/legal_chunks.jsonl
size: 180,915,261 bytes
SHA256: 95ff0129915ad4e77306fbdaa2c6eb8c7a7c58730cd21050aec429541416b30c
target: data/processed/legal_chunks.jsonl
```

The complete Render build command is:

```bash
python -m pip install --no-cache-dir uv && \
  uv sync --frozen --no-dev --extra qdrant --extra embedding && \
  python scripts/deployment/fetch_processed_chunks.py
```

The standard-library-only fetcher downloads to a temporary file in the target
directory, verifies SHA256, and atomically installs the target only after
verification. It reuses an existing matching file. A mismatched existing file
fails safely; set `LEGAL_QA_CHUNKS_OVERWRITE=1` only for an intentional
replacement. Failed downloads and checksum mismatches remove the temporary
file.

Output includes only the source hostname and filename, never the full URL or
query string. An Authorization header is sent only when `HF_TOKEN` is nonblank,
and the token is never printed. The current public artifact needs no token.

`data/processed/legal_chunks.jsonl` remains ignored by Git and excluded from
the Docker context. It is a verified build artifact, not source code. Do not
commit it, remove its ignore rule, or regenerate it during deployment.

The first real request constructs BGE-M3 and local BM25 lazily. Readiness does
not download or load the model, so a 200 readiness response does not prove that
the Render plan has enough RAM, disk/cache space, startup latency, or request
time for BGE-M3 on CPU. Review Render resource limits and Hugging Face cache
behavior before deployment.

Use one Uvicorn worker while conversation storage remains process-local.
Multiple workers or replicas would produce inconsistent server-side
conversation state. This limitation does not make chat history durable; the
frontend still treats localStorage as its rich source of truth.

### Startup boundary

Render startup must do only this:

```bash
uv run python -m uvicorn src.api.app:app --host 0.0.0.0 --port $PORT
```

It must not run indexing, collection setup, snapshot create/upload/restore,
corpus generation, evaluation, model preloading, real retrieval smoke, or an
OpenRouter request. Normal serving uses Qdrant Cloud and does not require a
local Qdrant process.

### Stage 5 post-deploy smoke and runtime decision

Current production endpoints:

```text
Backend: https://vnlaw-qa-backend.onrender.com
Frontend: https://vnlaw-qa.vercel.app
CORS_ALLOWED_ORIGINS=["https://vnlaw-qa.vercel.app"]
```

Infrastructure smoke passes on Render:

- `GET /health` responds successfully.
- `GET /api/v1/readiness` responds with `ready=true`,
  `service_mode=real`, valid configuration, and
  `collection_available` for Qdrant.

These checks establish process, configuration, and read-only Qdrant
availability only. They do not load BGE-M3 or prove that a Legal QA request can
complete.

Real `POST /api/v1/legal-qa/ask` serving is blocked on Render Free. Loading
BGE-M3 with Torch and Transformers exceeds the 512 MB instance memory limit
and causes an out-of-memory termination. Do not repeat `/ask` smoke requests on
this instance.

Runtime decision: keep `LEGAL_QA_SERVICE_MODE=real` and document the resource
limitation. Do not switch production to fake mode to make the smoke appear to
pass. A controlled real QA smoke remains pending until the backend runs with
sufficient memory or the embedding runtime architecture is changed and
reviewed.

## Container and Compose status

The existing files remain intentionally fake-mode foundations and are not the
chosen Render deployment path:

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
- Public deployment still needs authentication/authorization decisions,
  distributed abuse controls, request/body limits at the proxy, trusted
  proxy/header handling, TLS termination, and dependency/resource limits.
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

1. Move the real backend to a runtime with enough memory for BGE-M3, Torch,
   Transformers, local BM25, and request-time overhead, or separately review an
   architecture that removes the local embedding memory requirement.
2. Repeat one controlled real QA smoke only after the memory blocker is
   resolved.
3. Define deployed Qdrant TLS/custom CA policy and extend readiness if full
   schema/corpus-version verification is required.
4. Make frontend production API URL configuration fail safely instead of
   silently targeting localhost.
5. Complete API security decisions and resource/concurrency controls.
6. Resolve process-local conversation behavior before multi-worker or
   multi-replica use, or explicitly exclude server-side history from the
   initial deployment.
7. Complete the controlled real-mode smoke; infrastructure-only smoke has
   passed, but `/ask` remains blocked by memory.

## Recommended implementation order

1. Select a runtime with sufficient memory or review a lower-memory embedding
   runtime design without weakening retrieval/citation safety.
2. Add the minimum approved public-API security controls.
3. Perform deployment/security review, then execute one controlled low-risk
   real-mode smoke with citation and fallback checks.

## Safe validation commands

These checks do not call real services:

```bash
git diff --check

grep -R "localhost\|127.0.0.1" -n \
  src apps/frontend docs README.md PROJECT_CONTEXT.md 2>/dev/null || true

grep -R \
  "OPENROUTER_API_KEY\|OPENAI_API_KEY\|ANTHROPIC_API_KEY\|HF_TOKEN\|QDRANT_API_KEY" \
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
