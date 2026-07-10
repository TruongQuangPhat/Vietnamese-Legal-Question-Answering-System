# Azure Deployment Runbook

## Purpose

This runbook prepares future Azure deployment for VnLaw-QA while preserving
legal QA safety, secret hygiene, and controlled real-service validation.
VnLaw-QA is a Vietnamese legal research assistant, not legal advice. Deployment
work must not weaken citation, fallback, evidence-selection, retrieval, or
generation behavior.

## Current Status

Stage 1 CI quality gates exist for backend checks, frontend checks, protected
path guarding, and lightweight secret scanning. Stage 2 backend fake-mode
container smoke exists and validates packaging with `LEGAL_QA_SERVICE_MODE=fake`
and `GET /health`.

Azure deployment is not active yet. The skeleton workflows
`.github/workflows/deploy-staging.yml` and
`.github/workflows/deploy-production.yml` are manual planning workflows only.
They do not log in to Azure, create resources, push images, deploy containers,
or call live endpoints.

The skeleton workflows do not deploy. They are `workflow_dispatch`-only and
should not be added as required branch protection checks because they do not run
on pull requests. Required checks for normal PRs should remain routine CI checks
such as Backend CI, Frontend CI, Protected Path Guard, Secret Scan, and Backend
Container.

For the consolidated Azure staging resource plan and preflight checklist, see
`docs/ci_cd.md`.

## Recommended Architecture

The intended high-level Azure target keeps the existing provider boundaries
unless a later task explicitly changes them:

- Vercel frontend remains the public UI.
- Azure backend container hosts the FastAPI API.
- Neon or another reviewed PostgreSQL service remains conversation storage
  unless separately changed.
- Qdrant Cloud remains the vector database unless separately changed.
- OpenRouter with Gemini remains the LLM provider unless separately changed.
- The chunks artifact remains fetched or managed as documented in
  `docs/api_deployment.md` and `docs/backend-runtime.md`.

Do not migrate the database, Qdrant, LLM provider, or chunks artifact process in
the Azure deployment skeleton stage.

## Azure Options

Azure Container Apps is the tentative preference for container-native staging
and production experiments if subscription, networking, and resource
constraints allow it.

App Service for Containers is also acceptable if simpler web-app operations are
preferred. Choose between these options only after reviewing Azure subscription
limits, networking, secret management, logs, rollback support, and runtime
memory needs.

## GitHub Environments

Create separate GitHub Environments:

- `staging`
- `production`

Production manual approval only takes effect after maintainers configure
environment protection rules in GitHub settings. After this PR, maintainers
should configure:

```text
Settings -> Environments -> production -> Required reviewers
```

`staging` may have no approval or lighter approval depending on project
preference. Secrets must be stored in GitHub Environment secrets or an
Azure/hosting secret manager, never in Git, workflow logs, `.env`, or frontend
public variables.

## Required Secret Names

Store names only in documentation and workflow logs. Do not write values in the
repository.

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION`
- `AZURE_CONTAINER_APP_NAME`
- `AZURE_CONTAINER_APP_ENVIRONMENT`
- `AZURE_CONTAINER_REGISTRY`
- `AZURE_IMAGE_NAME`
- `AZURE_CONTAINER_REGISTRY_USERNAME` if password-based registry auth is used
  later
- `AZURE_CONTAINER_REGISTRY_PASSWORD` if password-based registry auth is used
  later
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `OPENROUTER_API_KEY`
- `LEGAL_QA_DATABASE_URL`
- `LEGAL_QA_SESSION_SECRET`
- `HF_TOKEN` only if the chunks artifact becomes private

Prefer Azure OIDC in a later deployment implementation if it is explicitly
scoped and reviewed. Do not request `id-token: write` until the workflow
actually uses OIDC.

## Future Staging Deploy Flow

1. CI checks pass.
2. Backend fake-mode container smoke passes.
3. Build the backend image.
4. Push the image to the reviewed registry.
5. Deploy or update the staging container app or service.
6. Run safe smoke checks:
   - `GET /health`;
   - `GET /api/v1/readiness` after configuration review;
   - missing-session expected `401` if anonymous session ownership is enabled;
   - conversation CRUD where appropriate.
7. Do not call `POST /api/v1/legal-qa/ask` unless explicitly approved.

## Future Production Deploy Flow

1. Staging passes.
2. Manual production approval is granted through the GitHub Environment.
3. Deploy production.
4. Run safe smoke checks.
5. Optionally run exactly one controlled `POST /api/v1/legal-qa/ask` smoke only
   after explicit approval and reviewed environment readiness.
6. Stop if timeout, out-of-memory, or `5xx` symptoms occur. Do not retry
   production ask requests repeatedly.

## Rollback

Rollback must be explicit and environment-aware:

- Roll back to the previous reviewed image or Azure revision.
- Do not switch production to fake mode to hide real-mode failures.
- Roll back conversation store or session-auth configuration only with reviewed
  operator intent.
- Preserve logs without secrets, raw session tokens, provider keys, raw prompts,
  or full user legal questions.

## Safety Rules

- No secrets in Git.
- Do not commit `.env` or `apps/frontend/.env.local`.
- Do not switch production to fake mode to hide real-mode failures. Fake mode is
  for CI, API contract checks, and container liveness smoke only; it does not
  validate real legal QA, Qdrant connectivity, LLM credentials, chunks, memory
  behavior, or real `/api/v1/legal-qa/ask` behavior.
- Do not print raw session tokens in logs.
- Do not print provider keys, database URLs, Qdrant keys, or Authorization
  headers in logs.
- Do not mutate protected paths.
- Do not mutate Qdrant collections or payloads from deployment workflows.
- Do not run indexing, crawling, embedding, reranking, snapshots, or benchmark
  evaluation from deployment workflows.
- Do not run production `/api/v1/legal-qa/ask` loops.
- Keep `/health` and `/api/v1/readiness` lightweight.

## Remaining Limitations

The skeleton workflows do not prove:

- Azure resource availability;
- registry publishing;
- Azure identity or secret access;
- real Qdrant connectivity;
- real LLM credentials;
- model memory behavior;
- chunks artifact availability;
- real `/api/v1/legal-qa/ask` behavior;
- production readiness.
