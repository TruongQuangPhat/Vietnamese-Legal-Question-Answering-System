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
deploy in Japan East. Production deployment remains skeleton-only.

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
5. Run conversation CRUD smoke where appropriate.
6. Require manual approval.
7. Deploy production.
8. Run safe production smoke with `/health` and `/api/v1/readiness`.

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
student-compatible staging target. Use environment variable and secret names
only in workflow documentation and repository examples:

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

### Future Secret Names

Names only, no values:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_WEBAPP_NAME`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `OPENROUTER_API_KEY`
- `LEGAL_QA_DATABASE_URL`
- `LEGAL_QA_SESSION_SECRET`
- `HF_TOKEN` only if needed

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
- [ ] Stage 5 App Service workflow can be manually dispatched.

### Open Questions

- Minimum memory/CPU for real mode.
- Whether the chunks artifact is public or private.
- Smoke-test scope for first real deployment.

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

- `service_mode`: `fake` or `real`, default `fake`;
- `run_readiness`: boolean, default `false`.

The first/default staging deployment mode is fake mode. Fake mode sets only
safe liveness and CI guard environment variables:

```env
PORT=8000
LEGAL_QA_SERVICE_MODE=fake
LEGAL_QA_ALLOW_REAL_TESTS=0
LEGAL_QA_ALLOW_DB_TESTS=0
LEGAL_QA_RATE_LIMIT_ENABLED=false
LEGAL_QA_AUTH_ENABLED=false
SCM_DO_BUILD_DURING_DEPLOYMENT=true
```

Real mode is available only when explicitly selected and required runtime
secrets are configured in the `staging` GitHub Environment. Real-mode staging
still does not call `/api/v1/legal-qa/ask` from the workflow.

### Required Staging Environment Secrets

Names only, no values:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_WEBAPP_NAME`
- `AZURE_STAGING_BACKEND_URL`

For real mode only:

- `QDRANT_URL`
- `QDRANT_API_KEY`
- `OPENROUTER_API_KEY`
- `LEGAL_QA_DATABASE_URL`
- `LEGAL_QA_SESSION_SECRET`
- `HF_TOKEN` only if needed by the current runtime

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
to the Azure Web App. It runs `GET /api/v1/readiness` only when `run_readiness` is
selected manually after configuration review.

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

### Production Boundary

`.github/workflows/deploy-production.yml` remains a planning-only skeleton.
Production deployment, production Azure login, production image push, and
production smoke checks are not implemented in Stage 5.

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
