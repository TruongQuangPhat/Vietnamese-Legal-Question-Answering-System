# CI/CD Guidance

## Purpose

This document defines safe CI/CD policy for VnLaw-QA. CI/CD must preserve legal
source traceability, citation integrity, fallback behavior, protected data
paths, reproducible evaluation, and secret safety.

`AGENTS.md` remains the canonical repository rule source. `PROJECT_CONTEXT.md`
remains the canonical current-state source.

## Current Status

Stage 1 CI quality gates exist for backend checks, frontend checks, protected
path guarding, and lightweight secret scanning. Stage 2 backend fake-mode
container smoke exists for packaging validation. Stage 3 Azure deployment
workflows added manual planning scaffolding. Stage 4A added Azure staging
resource planning. Stage 4B initially targeted Azure Container Apps, but Azure
for Students policy blocked Azure Container Registry, Azure Container Apps, and
Log Analytics Workspace. Stage 5 pivots staging to Azure App Service code
deploy in Japan East and passed fake-mode `/health`. Stage 6 adds a controlled
real-mode readiness preflight for staging and has passed after preparing chunks
at `/home/data/legal_chunks.jsonl`.

App Service source/zip deployment is now legacy/recovery only for this project.
Remote Oryx source builds with the embedding extra timed out, and prebuilt zip
source deployment was too large for reliable Kudu deployment. Production real
embedding dependencies must be deployed as a container image.

## CI Principles

- CI is offline-safe by default.
- CI uses fake mode by default.
- Routine CI does not call real LLM providers, mutate or require real Qdrant,
  run indexing, crawl sources, or run full benchmark workflows.
- Real services require explicit approval and guarded `workflow_dispatch`.
- CI must not loosen fallback, citation, evidence, retrieval, or generation
  gates to make checks pass.
- CI must not require model caches, local Qdrant storage, provider tokens, or
  protected corpus artifacts that are not part of the scoped check.

## Safe CI Environment Defaults

Routine CI should make fake mode explicit and blank all real-service secrets:

```env
LEGAL_QA_SERVICE_MODE=fake
LEGAL_QA_ALLOW_REAL_TESTS=0
LEGAL_QA_ALLOW_DB_TESTS=0
LEGAL_QA_DATABASE_URL=
LEGAL_QA_SESSION_SECRET=
QDRANT_URL=
QDRANT_API_KEY=
LEGAL_QA_QDRANT_URL=
LEGAL_QA_QDRANT_API_KEY=
OPENROUTER_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
HF_TOKEN=
```

Use repository or environment secrets only in explicitly reviewed workflows
that require them. Do not pass secrets to forked PR workflows.

## Workflow Files

Current and planned workflow paths:

```text
.github/workflows/ci.yml
.github/workflows/frontend-ci.yml
.github/workflows/protected-paths.yml
.github/workflows/secret-scan.yml
.github/workflows/backend-container.yml
.github/workflows/deploy-staging.yml
.github/workflows/deploy-production.yml
.github/workflows/deploy-production-container.yml
.github/workflows/production-ask-smoke.yml
.github/workflows/evaluation-refresh.yml
```

## Backend CI Gate

Expected backend checks:

```bash
uv sync --frozen
uv lock --check
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
env UV_CACHE_DIR=/tmp/vnlaw-uv-cache find src scripts tests -name '*.py' -exec uv run python -m py_compile {} +
uv run pytest tests/unit -q --durations=30
git diff --check
```

Backend CI should run in fake mode unless a workflow is explicitly approved for
real-service validation. Fake mode must not require Qdrant, OpenRouter,
embedding models, rerankers, legal corpus data, or full evaluation artifacts.

## Frontend CI Gate

Expected frontend checks:

```bash
cd apps/frontend
npm ci
npm run lint
npm run build
```

`NEXT_PUBLIC_API_BASE_URL` is browser-visible and must contain only a public API
origin. Never put secrets, private tokens, database URLs, session secrets, or
provider credentials in `NEXT_PUBLIC_*` variables.

## Protected Path Guard

Routine CI/CD PRs must not change protected corpus, benchmark, or official
evaluation paths unless an official rerun is explicitly scoped.

Protected paths:

```text
data/raw/
data/interim/
data/reports/
data/processed/legal_chunks.jsonl
data/eval/
artifacts/reports/evaluation/
```

Suggested guard:

```bash
git diff --name-only -- \
  data/raw \
  data/interim \
  data/reports \
  data/processed/legal_chunks.jsonl \
  data/eval \
  artifacts/reports/evaluation
```

Expected output is empty for routine CI/CD guidance, workflow, container, and
deployment PRs.

For GitHub Actions PR checks, compare the PR base branch or base SHA to `HEAD`
instead of relying on a local working-tree diff. A future guard can use this
shape after checkout with enough history:

```bash
BASE_REF="${GITHUB_BASE_REF:-main}"
git fetch --no-tags --depth=1 origin "$BASE_REF"
git diff --name-only "origin/$BASE_REF"...HEAD -- \
  data/raw \
  data/interim \
  data/reports \
  data/processed/legal_chunks.jsonl \
  data/eval \
  artifacts/reports/evaluation
```

For event payloads that expose a trusted base SHA, compare
`"${GITHUB_EVENT_PULL_REQUEST_BASE_SHA}"...HEAD` or the equivalent parsed event
field. The workflow must fail if any protected path appears unless the PR
explicitly scopes an official corpus, benchmark, or evaluation rerun.

## Secret Scan Policy

CI must block commits or logs containing:

- `.env`;
- `apps/frontend/.env.local`;
- database URLs;
- session secrets;
- OpenRouter, OpenAI, Anthropic, Hugging Face, or Qdrant keys;
- Authorization headers;
- raw smoke session tokens;
- model caches;
- Qdrant storage;
- local virtual environments and cache files.

Workflow logs should print safe status codes and environment variable names,
not values.

Implementation options include reviewed third-party scanners such as gitleaks
or trufflehog, or an internal grep-based guard for repository-specific patterns.
Third-party scanner actions must be reviewed and pinned appropriately before
use. Placeholder variable names such as `OPENROUTER_API_KEY` are allowed in
docs and examples, but real-looking values, bearer tokens, connection strings,
and private URLs must be blocked.

## Container Build Gate

Future container CI should validate fake-mode packaging only:

1. Build the backend image.
2. Run it with `LEGAL_QA_SERVICE_MODE=fake`.
3. Smoke `GET /health`.
4. Do not call real `POST /api/v1/legal-qa/ask`.
5. Do not require Qdrant, OpenRouter, chunks, model caches, embedding
   inference, or reranking inference.
6. Do not fetch processed chunks or model caches unless artifact-fetch
   validation is explicitly scoped.

Real-mode container packaging requires separate approval and environment review.

## CD Policy

Deployment should follow this path:

1. PR CI passes.
2. Merge to `main`.
3. Deploy staging.
4. Run safe staging smoke with `/health` and `/api/v1/readiness`.
5. Run exactly one controlled staging `/api/v1/legal-qa/ask` smoke only after
   real-readiness passes and the operator confirms real-service usage.
6. Run conversation CRUD smoke where appropriate.
7. Require manual approval.
8. Deploy production.
9. Run safe production smoke with `/health` and `/api/v1/readiness`.

A controlled `POST /api/v1/legal-qa/ask` smoke is manual, exactly one request,
and only after explicit approval and reviewed environment readiness. Do not use
repeated production `/ask` calls as validation.

## Evaluation Refresh Policy

Evaluation refresh is not normal PR CI.

Rules:

- Use a guarded manual trigger such as `workflow_dispatch`.
- Require explicit approval.
- Use a unique non-existing output directory.
- Do not overwrite official reports.
- Do not tune on the held-out split.
- Do not rerun the Naive RAG baseline unless explicitly requested.
- Keep corpus, chunking, retrieval, generator, evidence-selection, fallback,
  and evaluation code fixed unless the task scopes a controlled ablation.

## Azure Staging Notes

Azure for Students policy currently blocks these previously planned staging
resources:

- Azure Container Registry;
- Azure Container Apps;
- Log Analytics Workspace.

Allowed Azure Policy locations found for the student subscription:

```text
uaenorth
koreacentral
japaneast
malaysiawest
indonesiacentral
```

Stage 5 uses Azure App Service code deploy in Japan East as the current
student-compatible staging target. Stage 5 fake-mode deployment passed with
`GET /health` returning `{"status":"ok"}`. Stage 6 extends the same manual
workflow with a controlled `real-readiness` mode that configures real-mode
settings and calls only `GET /health` plus `GET /api/v1/readiness`. Stage 6
passed on the B1 staging App Service after the chunks artifact was prepared at
`/home/data/legal_chunks.jsonl`.

Use environment variable and secret names only in workflow documentation and
repository examples:

```text
AZURE_CLIENT_ID
AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID
AZURE_RESOURCE_GROUP
AZURE_WEBAPP_NAME
AZURE_STAGING_BACKEND_URL
QDRANT_URL
QDRANT_API_KEY
OPENROUTER_API_KEY
LEGAL_QA_DATABASE_URL
LEGAL_QA_SESSION_SECRET
```

Stage 6 may reference GitHub Environment secrets through exact GitHub Actions
secret expressions in workflow YAML. The lightweight secret guard still blocks
raw values and non-placeholder assignments.

Do not include real values in Git, workflow logs, docs, examples, or issue
comments.

For the Azure deployment skeleton and future manual rollout checklist, see
`docs/runbooks/azure_deployment.md`.

## Stage 4A - Azure Staging Resource Planning

### Status

Completed / planning only:

- Not deployed.
- No Azure resources created.
- No image push.
- No Azure login.
- No live service calls.

### Context

The VnLaw-QA backend is a FastAPI container. Stage 1 proves routine code
quality gates. Stage 2 proves the backend Docker image can build and serve
fake-mode `GET /health`. Stage 3 added manual-only Azure deployment skeleton
workflows. Stage 4A decides the staging resource plan before implementing any
real Azure deployment.

The current production Render backend and Vercel frontend remain unchanged by
this planning stage.

### Decision Summary

The original recommendation preferred Azure Container Apps for staging unless
Azure subscription or resource constraints forced App Service.

Reasoning:

- The backend is already containerized.
- Container Apps is container-native.
- Revision-based updates and rollback are useful for staging and future
  production.
- App Service for Containers remains a viable fallback if simpler web-app
  operations are preferred.

Azure for Students policy later blocked Azure Container Registry and Container
Apps, so Stage 5 selected Azure App Service code deploy instead. This decision
does not make cost, quota, performance, or memory guarantees. Real-mode sizing
must be tested in the selected Azure environment.

### Options Considered

#### Option A - Azure Container Apps

Azure Container Apps provides container-native backend hosting with a
revision-based deployment model. It is suitable for staging and production
experiments when subscription, networking, and resource constraints allow it.

This option requires a container registry and a Container Apps managed
environment. A future workflow would likely use Azure login, image build and
push, and a container app update. Real-mode memory sizing and cold-start
behavior must be tested separately.

#### Option B - App Service

App Service provides web-app oriented hosting with familiar App Service
operations. For the current Azure for Students staging target, code deploy is
used instead of App Service for Containers because ACR is blocked.

This option uses an App Service deployment package and Oryx build on App
Service. Real-mode memory sizing and cold-start behavior must be tested
separately.

### Non-goals

The Stage 4A planning step did not:

- create Azure resources;
- implement deployment;
- push images;
- log in to Azure;
- request `id-token: write`;
- run production `/api/v1/legal-qa/ask` smoke;
- mutate Qdrant;
- run indexing, crawling, embedding, reranking, snapshots, or evaluation;
- modify protected data, benchmark, or official evaluation artifact paths.

### Proposed Staging Resources

Resource placeholders only:

- Azure subscription
- Resource group
- Azure region/location
- Azure App Service Web App
- App Service plan
- Staging backend URL
- Logs/monitoring approach within student subscription policy limits

Suggested placeholder/configuration names:

- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION`
- `AZURE_WEBAPP_NAME`
- `AZURE_STAGING_BACKEND_URL`

### Future GitHub Environment Setup

Use separate GitHub Environments:

- `staging`
- `production`

Production requires Required reviewers. Staging may use lighter approval or no
approval depending on project preference.

Deployment skeleton workflows should not be required branch protection checks
because they are `workflow_dispatch`-only and do not run on pull requests.
Normal PR required checks should remain:

- Backend CI
- Frontend CI
- Protected Path Guard
- Secret Scan
- Backend Container

### Stage 5/6 Secret Names

Names only, no values:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_WEBAPP_NAME`
- `AZURE_STAGING_BACKEND_URL`

Stage 6 `real-readiness` additionally requires:

- `QDRANT_URL`
- `QDRANT_API_KEY`
- `OPENROUTER_API_KEY`
- `LEGAL_QA_DATABASE_URL`
- `LEGAL_QA_SESSION_SECRET`
- `LEGAL_QA_CHUNKS_URL`
- `LEGAL_QA_CHUNKS_SHA256`

Optional only if a later runtime packaging change needs it:

- `HF_TOKEN`

### Authentication Decision

Use GitHub OIDC for the staging deployment workflow. Do not add
`id-token: write` to any workflow unless that workflow actually uses OIDC.
Avoid long-lived credentials when possible.

### Stage 5 Staging Deployment Flow

Implemented staging flow:

1. Required CI checks pass.
2. Backend Container check passes.
3. Manual staging deployment workflow is dispatched.
4. Azure login runs through GitHub OIDC.
5. A backend repository deployment package is created for App Service.
6. App Service fake-mode settings and startup command are configured.
7. The package is deployed to the configured Azure Web App.
8. Safe smoke runs:
   - `GET /health`;
   - `GET /api/v1/readiness` only after config review;
   - no automated `/api/v1/legal-qa/ask`.
9. Do not call `/api/v1/legal-qa/ask` unless explicitly approved.

### Stage 6 Real-Readiness Preflight

Stage 6 extends `.github/workflows/deploy-staging.yml` with a
`service_mode=real-readiness` dispatch option. The default remains `fake`.

The `real-readiness` path:

1. validates the required Azure and real-readiness GitHub Environment secrets;
2. deploys the same App Service package with the Qdrant and embedding optional
   dependencies prebuilt on the GitHub runner;
3. verifies `scripts/deployment/fetch_processed_chunks.py` is present in the
   App Service deployment package for operator-controlled chunk preparation;
4. configures App Service for `LEGAL_QA_SERVICE_MODE=real`;
5. keeps `LEGAL_QA_RATE_LIMIT_ENABLED=false` and `LEGAL_QA_AUTH_ENABLED=false`;
6. sets the existing collection name `vnlaw_chunks_bgem3_v1_full`;
7. configures the legal chunks artifact URL, SHA256, and
   `LEGAL_QA_CHUNKS_PATH=/home/data/legal_chunks.jsonl`;
8. runs bounded `GET /health`;
9. runs bounded `GET /api/v1/readiness`.

Stage 6 does not call `/api/v1/legal-qa/ask`, does not call LLM providers
directly, does not run benchmarks, and does not crawl, index, re-embed, rerank,
or mutate Qdrant. `/api/v1/legal-qa/ask` is deferred to Stage 7 and requires a
separate explicit approval.

The first real-readiness attempt that fetched chunks inside the App Service
startup command caused Azure `ContainerTimeout` before Uvicorn served
`/health`. The startup command is now always plain Uvicorn:

```bash
python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

`/health` must not depend on chunks, Qdrant, OpenRouter, embedding models, or
other real-mode dependencies. Chunks should be prepared outside the startup
path into `/home/data/legal_chunks.jsonl`, then readiness can validate that
the configured file exists and Qdrant collection metadata is readable.

The successful Stage 6 readiness criteria are:

```text
GET /health -> HTTP 200
GET /api/v1/readiness -> HTTP 200 and ready true
```

The observed successful readiness response was sanitized to:

```json
{
  "ready": true,
  "service_mode": "real",
  "checks": [
    {"name": "configuration", "ready": true, "detail": "valid"},
    {"name": "qdrant", "ready": true, "detail": "collection_available"}
  ]
}
```

Azure B1 is enough for the current readiness preflight. Full real QA serving is
separate from readiness, and failures should be treated as configuration,
dependency, network, or resource-sizing signals, not as broad legal QA quality
results.

### Stage 7 Controlled Staging Ask Smoke

Stage 7 adds `.github/workflows/staging-ask-smoke.yml` as a separate manual
workflow. It is not part of `deploy-staging.yml` and does not deploy code or
change App Service configuration.

Prerequisites:

1. Stage 6 real-readiness has passed on Azure staging.
2. `GET /health` returns HTTP 200.
3. `GET /api/v1/readiness` returns HTTP 200 with `ready=true`,
   `service_mode=real`, configuration `valid`, and Qdrant
   `collection_available`.
4. The workflow is dispatched from `main`.
5. The operator types `I_UNDERSTAND_THIS_CALLS_REAL_SERVICES`.

The workflow calls only:

```text
GET /health
GET /api/v1/readiness
POST /api/v1/legal-qa/ask
```

It sends exactly one `/api/v1/legal-qa/ask` request, with no loop, no retry, no
concurrency, no benchmark, and no load test. The minimal request body follows
the current `LegalQARequest` API schema:

```json
{
  "question": "<workflow input>",
  "include_evidence": false,
  "include_debug": false
}
```

Pass criteria:

- `/health` returns HTTP 200;
- `/api/v1/readiness` returns HTTP 200 and `ready=true`;
- `/api/v1/legal-qa/ask` returns HTTP 200;
- logs show only HTTP status, response JSON keys, answer length, citation count,
  evidence count, and response latency when present.

Observed Stage 7 result:

- Controlled Staging Ask Smoke workflow passed.
- `/api/v1/legal-qa/ask` returned HTTP 200.
- Ask request duration was 54 seconds.
- Response JSON keys were `answer`, `citations`, `decision`, `evidence`,
  `metadata`, `request_id`, and `warnings`.
- Answer length was 54 characters.
- Citation count was 0 and evidence count was 0.
- Response `metadata.latency_ms` was 1995.
- No full answer, secrets, headers, or environment variables were printed.
- No repeated `/api/v1/legal-qa/ask` calls were made.

The zero citation/evidence count is not a Stage 7 deployment-smoke failure
because Stage 7 only proves that one controlled real `/ask` request can complete
without unsafe logging or repeated calls. Citation and evidence quality should
be investigated in a later quality/citation validation stage. The difference
between the 54-second workflow request duration and the 1995 ms response
latency is a follow-up observation for cold-start, network, App Service, or
client-side timing analysis.

Failure handling:

- Stop after the first failure.
- Do not rerun repeatedly to chase intermittent provider, memory, or timeout
  symptoms.
- Do not print full answers, prompts, evidence text, headers, provider keys,
  database URLs, session secrets, or environment variables.
- Treat failures as deployment/resource/provider signals, not as legal-quality
  benchmark results.

### Real-mode Risk Notes

Fake mode only proves container liveness and API contract basics. Real mode may
load embeddings, chunks, retrieval, Qdrant configuration, and LLM
configuration. Reranking is not part of the adopted final pipeline, but future
experiments or configuration changes must still be reviewed before enabling any
real reranking inference.

Real-mode memory and cold-start behavior must be tested separately. Do not
switch production to fake mode to hide real-mode failures. Do not repeatedly
retry production `/api/v1/legal-qa/ask` if timeout, out-of-memory, or `5xx`
symptoms occur.

### Rollback Plan

- Roll back to the previous reviewed App Service deployment.
- Preserve logs without secrets, raw prompts, raw session tokens, provider
  keys, or database URLs.
- Stop if `5xx`, out-of-memory, or timeout symptoms occur.
- Do not repeatedly retry production `/api/v1/legal-qa/ask`.
- Do not mutate Qdrant or corpus artifacts during rollback.

### Azure Staging Preflight Checklist

#### Repository Preconditions

- [ ] Stage 1 CI checks pass.
- [ ] Stage 2 Backend Container check passes.
- [ ] Stage 3 deployment skeleton exists.
- [ ] Protected Path Guard is active.
- [ ] Secret Scan is active.
- [ ] No uncommitted protected data/evaluation/artifact path changes exist.

#### Azure Preconditions

- [ ] Azure subscription confirmed.
- [ ] Region selected.
- [ ] Resource group selected or planned.
- [ ] Azure App Service selected.
- [ ] Staging backend name selected.
- [ ] Log/monitoring approach reviewed within current policy limits.
- [ ] Resource sizing reviewed for real mode.

#### GitHub Preconditions

- [ ] `staging` environment exists.
- [ ] `production` environment exists.
- [ ] Production Required reviewers configured.
- [ ] Staging secrets configured only after resource creation.
- [ ] Deploy skeleton workflows are not required branch checks.
- [ ] Normal required PR checks remain routine CI checks.

#### Secret Hygiene

- [ ] No `.env` committed.
- [ ] No `apps/frontend/.env.local` committed.
- [ ] No raw database URL printed.
- [ ] No session secret printed.
- [ ] No provider key printed.
- [ ] No Qdrant key printed.
- [ ] No raw smoke session token printed.
- [ ] Secrets stored only in GitHub Environment secrets or an Azure secret
      manager.

#### Safe First Staging Smoke

- [ ] Call `/health` first.
- [ ] Call `/api/v1/readiness` only after config review.
- [ ] Verify auth/session behavior without printing tokens.
- [ ] Run conversation CRUD smoke if scoped.
- [ ] Do not automate `/api/v1/legal-qa/ask`.
- [ ] Stop on timeout, out-of-memory, or `5xx`; do not retry repeatedly.

#### No-Go Conditions

- [ ] CI checks failing.
- [ ] Backend Container check failing.
- [ ] Required secrets missing.
- [ ] App Service resource missing.
- [ ] Rollback unclear.
- [ ] Protected path changes present.
- [ ] Real provider keys exposed.
- [ ] Staging URL not confirmed.
- [ ] App Service deployment package cannot be reproduced.
- [ ] Memory sizing not reviewed for real mode.

#### Completion Criteria

- [ ] Resource plan approved.
- [ ] GitHub environments configured.
- [ ] Required secrets listed and assigned owners.
- [ ] Rollback path documented.
- [ ] First staging smoke scope approved.
- [ ] Stage 6 App Service workflow can be manually dispatched.

### Open Questions

- Minimum memory/CPU for full real QA serving.
- Whether the chunks artifact should remain packaged or be fetched for later
  real-mode deploys.
- Smoke-test scope for Stage 7 `/api/v1/legal-qa/ask`.

## Stage 5 - Manual Azure App Service Staging Deployment

### Status

Implemented as a guarded manual staging workflow in
`.github/workflows/deploy-staging.yml`.

Current staging resources:

```text
AZURE_WEBAPP_NAME=vnlaw-backend-staging-phat
AZURE_RESOURCE_GROUP=rg-vnlaw-staging
AZURE_LOCATION=japaneast
AZURE_STAGING_BACKEND_URL=https://vnlaw-backend-staging-phat-feg8eabzgxhuafc3.japaneast-01.azurewebsites.net
APP_SERVICE_PLAN=asp-vnlaw-staging
```

This workflow:

- runs only through `workflow_dispatch`;
- uses GitHub Environment `staging`;
- uses Azure OIDC login with `id-token: write`;
- creates a code deployment package for Azure App Service;
- excludes heavy cache, frontend build, protected data, and official
  evaluation report paths from the package;
- deploys the package to the configured Azure Web App;
- configures fake-mode App Service settings and the FastAPI startup command;
- runs safe staging smoke checks;
- does not deploy production;
- does not call `/api/v1/legal-qa/ask`.

### Behavior

The staging workflow has two inputs:

- `service_mode`: `fake` or `real-readiness`, default `fake`;
- `run_readiness`: boolean, default `false`.

The default fake path sets only safe liveness and CI guard environment
variables:

```env
PORT=8000
LEGAL_QA_SERVICE_MODE=fake
LEGAL_QA_ALLOW_REAL_TESTS=0
LEGAL_QA_ALLOW_DB_TESTS=0
LEGAL_QA_RATE_LIMIT_ENABLED=false
LEGAL_QA_AUTH_ENABLED=false
SCM_DO_BUILD_DURING_DEPLOYMENT=false
ENABLE_ORYX_BUILD=false
PYTHONPATH=/home/site/wwwroot/.python_packages/lib/site-packages
```

The `real-readiness` path configures real mode for `/health` and
`/api/v1/readiness` only. It sets `LEGAL_QA_CHUNKS_PATH` to
`/home/data/legal_chunks.jsonl`, but it does not fetch chunks during App Service
startup and does not call `/api/v1/legal-qa/ask`.

### Azure App Service Dependency Packaging

The real `/ask` path requires `--extra qdrant --extra embedding`. The embedding
extra brings in `flagembedding`, `sentence-transformers`, `transformers`, and
`torch`; Azure App Service/Oryx remote source builds became too slow after that
extra was added. The observed failed deployment completed dependency install in
about 412 seconds and build snippets in about 429 seconds, then remained in
OneDeploy compression/deployment until the GitHub job was canceled near 29
minutes.

The staging workflow now uses a prebuilt App Service package:

1. GitHub Actions exports the locked non-dev requirements with `qdrant` and
   `embedding`, without the local editable project entry.
2. GitHub Actions installs them into
   `.python_packages/lib/site-packages` with CPU Torch resolution, filtering
   CUDA/Triton packages that are not needed on the B1 CPU App Service target.
3. App Service remote build is disabled with
   `SCM_DO_BUILD_DURING_DEPLOYMENT=false` and `ENABLE_ORYX_BUILD=false`.
4. `PYTHONPATH` points at the packaged dependency directory.
5. Azure CLI zip deployment runs with a bounded timeout.

This keeps real `/ask` dependencies available while avoiding heavy Oryx work on
the B1 App Service instance. If the prebuilt package still exceeds App Service
source-deploy limits, the next reviewed option is a separate container-based
deployment or a lighter query-embedding architecture; do not reintroduce chunk
fetching or model loading into the startup command.

Status update: the prebuilt source package also proved unsuitable for reliable
App Service source deployment. The prebuilt package was about 362 MB, Kudu
returned `502`, and partially applied app settings caused startup failure with
`No module named uvicorn`. Treat `deploy-staging.yml` as a legacy recovery path
for the restored staging source-deploy app only. Do not use source/zip deploy
for production real embedding dependencies.

### Required Staging Environment Secrets

Names only, no values:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_WEBAPP_NAME`
- `AZURE_STAGING_BACKEND_URL`

For `real-readiness` only:

- `QDRANT_URL`
- `QDRANT_API_KEY`
- `OPENROUTER_API_KEY`
- `LEGAL_QA_DATABASE_URL`
- `LEGAL_QA_SESSION_SECRET`
- `LEGAL_QA_CHUNKS_URL`
- `LEGAL_QA_CHUNKS_SHA256`

### Authentication and Permissions

`deploy-staging.yml` uses:

```yaml
permissions:
  contents: read
  id-token: write
```

`id-token: write` is present only because Azure OIDC login is implemented in
the staging workflow. Production remains skeleton-only and must not request
`id-token: write` until production deployment is explicitly implemented.

### Safe Smoke Scope

The staging workflow always runs a bounded `GET /health` smoke after deploying
to the Azure Web App. It runs `GET /api/v1/readiness` when `run_readiness` is
selected manually in fake mode, and always runs readiness for
`service_mode=real-readiness`.

The staging workflow does not:

- call `/api/v1/legal-qa/ask`;
- call Qdrant directly;
- call OpenRouter, Gemini, OpenAI, Anthropic, or another LLM provider directly;
- run crawling, indexing, embedding, reranking, or benchmark/evaluation jobs.

### Branch Protection

`deploy-staging.yml` is `workflow_dispatch`-only and should not be a required
PR check. Normal required PR checks remain:

- Backend CI
- Frontend CI
- Protected Path Guard
- Secret Scan
- Backend Container

### Production Container Backend

Production backend deployment is implemented separately in
`.github/workflows/deploy-production-container.yml`. It is `workflow_dispatch`
only, uses the GitHub Environment `production`, and requires the confirmation
phrase:

```text
I_UNDERSTAND_THIS_DEPLOYS_PRODUCTION_CONTAINER_BACKEND
```

The workflow:

1. validates required production secret names without printing values;
2. downloads `legal_chunks.jsonl` from `LEGAL_QA_CHUNKS_URL` into the GitHub
   runner temp directory;
3. verifies `LEGAL_QA_CHUNKS_SHA256`;
4. builds `docker/backend/Dockerfile` target `production-with-chunks`;
5. runs local fake-mode container `GET /health`;
6. pushes the image to Azure Container Registry only after local smoke passes;
7. configures a separate production App Service for Containers Web App;
8. restarts the production backend;
9. runs bounded `GET /health` and `GET /api/v1/readiness`.

The deploy workflow does not call `/api/v1/legal-qa/ask`. It does not crawl,
index, re-embed, rerank, run benchmarks, mutate Qdrant, or modify protected
paths.

Required production resources and settings:

- Azure Container Registry, with login server stored as
  `AZURE_ACR_LOGIN_SERVER`;
- production Web App such as `vnlaw-backend-prod-phat`;
- production App Service plan sized for BGE-M3/Torch CPU memory;
- managed identity with `AcrPull` or equivalent registry pull permission;
- `acrUseManagedIdentityCreds=true`;
- `WEBSITES_CONTAINER_START_TIME_LIMIT=1800`;
- `WEBSITES_PORT=8000`;
- `PORT=8000`;
- `alwaysOn=true`;
- Docker container logging set to `filesystem`;
- `LEGAL_QA_SERVICE_MODE=real`;
- `LEGAL_QA_CHUNKS_PATH=/home/data/legal_chunks.jsonl`;
- Qdrant URL/API key through `QDRANT_URL` and `QDRANT_API_KEY`;
- `OPENROUTER_API_KEY`;
- `LEGAL_QA_DATABASE_URL`;
- `LEGAL_QA_SESSION_SECRET`;
- `CORS_ALLOWED_ORIGINS` including `https://vnlaw-qa.vercel.app`.

`.github/workflows/deploy-production.yml` remains planning-only and is not the
container deployment path.

### Production Ask Smoke

Production `/ask` validation is separate in
`.github/workflows/production-ask-smoke.yml`. It is `workflow_dispatch` only,
uses the GitHub Environment `production`, and requires:

```text
I_UNDERSTAND_THIS_CALLS_REAL_PRODUCTION_SERVICES
```

It calls only:

```text
GET /health
GET /api/v1/readiness
POST /api/v1/legal-qa/ask
```

It sends exactly one `/ask` request with a configurable timeout up to 600
seconds for production ML cold start, prints only safe summary fields, and fails
if `decision == "error"`, `warnings` contains `internal_error`,
`metadata.model` is null, `metadata.retrieval_question_prepared` is false, or
the answer is the generic internal-error answer.

Production `/ask` timeout diagnostics come from sanitized
`legal_qa_request_timing` logs. The logs record stage names and elapsed
milliseconds for request validation, context loading, retrieval-question
preparation, embedding/retrieval, provider call, response mapping, completion,
and failure without logging question text, conversation content, retrieved
legal text, prompts, full answers, headers, cookies, provider responses, or
secret values.

## Stage 8 - Frontend to Azure Backend Integration Audit

The frontend API base URL is configured through:

```env
NEXT_PUBLIC_API_BASE_URL
```

The Next.js client reads this value in `apps/frontend/src/lib/api-config.ts`.
It is browser-visible and embedded during `next build`; changing it requires a
new Vercel deployment. Do not put secrets in any `NEXT_PUBLIC_*` value.

Current frontend code does not hardcode the Render backend URL. Render backend
references remain in deployment documentation and frontend setup guidance as
the current production value:

```env
NEXT_PUBLIC_API_BASE_URL=https://vnlaw-qa-backend.onrender.com
```

For Vercel Preview or staging validation against Azure App Service, set:

```env
NEXT_PUBLIC_API_BASE_URL=https://vnlaw-backend-staging-phat-feg8eabzgxhuafc3.japaneast-01.azurewebsites.net
```

Do not change Vercel Production until a Preview deployment passes UI smoke.
The later Production migration step is to change Vercel Production
`NEXT_PUBLIC_API_BASE_URL` from the Render backend origin to the accepted Azure
backend origin and redeploy the frontend.

Backend CORS is controlled by `CORS_ALLOWED_ORIGINS`. The backend default only
allows `http://localhost:3000`; deployed browser traffic requires exact Vercel
origins in the backend environment. For Azure Preview/Staging, include the
actual Vercel Preview URL produced by Vercel. For Production, include:

```env
CORS_ALLOWED_ORIGINS=["https://vnlaw-qa.vercel.app"]
```

If Preview and Production are both routed to Azure, the Azure App Service value
should be a JSON array containing every accepted exact origin, for example:

```env
CORS_ALLOWED_ORIGINS=["https://vnlaw-qa.vercel.app","https://<vercel-preview-origin>"]
```

Migration checklist:

- [ ] Set Vercel Preview `NEXT_PUBLIC_API_BASE_URL` to the Azure staging backend
      origin.
- [ ] Add the exact Vercel Preview origin to Azure App Service
      `CORS_ALLOWED_ORIGINS`.
- [ ] Redeploy Vercel Preview and run UI smoke against Azure.
- [ ] Confirm no `/api/v1/legal-qa/ask` loop, benchmark, or load test is run
      from the UI smoke.
- [ ] Switch Vercel Production `NEXT_PUBLIC_API_BASE_URL` from Render to the
      accepted Azure backend origin only after Preview passes.
- [ ] Keep the previous Render backend URL as the rollback value until Azure
      production traffic is accepted.
- [ ] After Azure production is accepted, plan Render decommission separately:
      remove Render-specific secrets, disable Render traffic, preserve safe
      logs, and document final rollback limits.

## Stage 9 - Vercel Preview to Azure Backend UI Smoke

Stage 9 prepares a manual browser smoke where the Vercel Preview frontend calls
the Azure App Service backend. It does not change Vercel Production and does
not modify frontend code. The frontend still reads:

```env
NEXT_PUBLIC_API_BASE_URL
```

Vercel Preview setup:

```env
NEXT_PUBLIC_API_BASE_URL=https://vnlaw-backend-staging-phat-feg8eabzgxhuafc3.japaneast-01.azurewebsites.net
```

After Vercel creates the Preview deployment, copy the exact Preview URL and add
that origin to Azure App Service:

```env
CORS_ALLOWED_ORIGINS=["https://<vercel-preview-origin>"]
```

If Azure must also allow the production Vercel origin during the same test
window, include both exact origins:

```env
CORS_ALLOWED_ORIGINS=["https://vnlaw-qa.vercel.app","https://<vercel-preview-origin>"]
```

Restart Azure App Service after changing `CORS_ALLOWED_ORIGINS`; do not rely on
the new value being picked up without a restart.

Manual UI smoke checklist:

- [ ] Set Vercel Preview `NEXT_PUBLIC_API_BASE_URL` to the Azure backend URL.
- [ ] Redeploy Vercel Preview.
- [ ] Copy the exact Vercel Preview URL.
- [ ] Add the exact Preview origin to Azure `CORS_ALLOWED_ORIGINS`.
- [ ] Restart Azure App Service.
- [ ] Open the Vercel Preview frontend.
- [ ] Open browser DevTools and select the Network tab.
- [ ] Submit exactly one safe Vietnamese legal question:

      ```text
      Theo Bộ luật Dân sự Việt Nam, hợp đồng dân sự có thể bị vô hiệu trong những trường hợp nào?
      ```

- [ ] Verify the request URL goes to the Azure backend, not Render.
- [ ] Verify the UI displays a response.
- [ ] Verify no browser CORS error appears.

Pass criteria:

- Vercel Preview is built with the Azure `NEXT_PUBLIC_API_BASE_URL`.
- Browser Network shows the `/api/v1/legal-qa/ask` request going to
  `vnlaw-backend-staging-phat-feg8eabzgxhuafc3.japaneast-01.azurewebsites.net`.
- The UI renders a response.
- No CORS error appears in the browser.
- Exactly one UI question is submitted; no loop, benchmark, load test, or
  concurrent request test is run.

Fail criteria:

- The browser request still goes to Render.
- The browser blocks the request with CORS.
- The UI cannot render a response.
- Multiple `/api/v1/legal-qa/ask` requests are sent unintentionally.

Rollback and production hold:

- Do not switch Vercel Production in Stage 9.
- Keep Render as the rollback backend value until the later production migration
  passes.
- If Preview fails, restore the Preview `NEXT_PUBLIC_API_BASE_URL` to the prior
  value or delete the Preview override, then redeploy Preview.
- Do not decommission Render until Azure production traffic is accepted and a
  separate Render decommission checklist is executed.

## Rollback and Incident Notes

Production rollback must be explicit and environment-aware. CI/CD must not hide
real-mode failure by switching production to fake mode. If real-mode deployment
fails, report the failure, preserve logs without secrets, and roll back to a
known reviewed deployment or hold the release.

## Out of Scope

This guidance does not implement CI/CD automation, deploy to Azure, create Azure
resources, change Dockerfiles, change backend/frontend runtime behavior, change
retrieval or generation behavior, call real providers, mutate Qdrant, crawl,
index, re-embed, rerank, snapshot, run full benchmark workflows, call production
`/api/v1/legal-qa/ask`, modify protected paths, or document secrets.
