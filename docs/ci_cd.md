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
workflows are skeleton-only manual planning workflows and do not deploy.

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

## Azure Readiness Notes

Azure deployment workflows should be added later after subscription and
resource decisions are made. Use placeholders only in workflow documentation and
repository examples:

```text
AZURE_CREDENTIALS
AZURE_RESOURCE_GROUP
AZURE_CONTAINER_APP_NAME
AZURE_CONTAINER_REGISTRY
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
