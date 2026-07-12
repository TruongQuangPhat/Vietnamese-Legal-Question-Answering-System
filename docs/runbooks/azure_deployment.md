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

Azure production deployment is not active yet. The staging workflow
`.github/workflows/deploy-staging.yml` is now a manual Azure App Service code
deployment workflow. It defaults to fake mode, uses Azure OIDC, updates only the
configured staging Web App, and runs safe smoke checks. The production workflow
`.github/workflows/deploy-production.yml` remains a manual planning skeleton
only.

Azure App Service is the current student-compatible staging target. Azure for
Students policy currently blocks Azure Container Registry, Azure Container Apps,
and Log Analytics Workspace, so the staging workflow does not build, push, or
deploy container images.

Stage 5 staging is fake-mode only. Real-mode Azure staging is deferred to a
later stage and is not configured by `.github/workflows/deploy-staging.yml`.

The staging workflow is `workflow_dispatch`-only and should not be added as a
required branch protection check because it does not run on pull requests.
Required checks for normal PRs should remain routine CI checks such as Backend
CI, Frontend CI, Protected Path Guard, Secret Scan, and Backend Container.

For the consolidated Azure staging resource plan, Stage 5 workflow behavior,
and preflight checklist, see
`docs/ci_cd.md`.

## Recommended Architecture

The intended high-level Azure target keeps the existing provider boundaries
unless a later task explicitly changes them:

- Vercel frontend remains the public UI.
- Azure App Service hosts the FastAPI API for the current staging deployment.
- Neon or another reviewed PostgreSQL service remains conversation storage
  unless separately changed.
- Qdrant Cloud remains the vector database unless separately changed.
- OpenRouter with Gemini remains the LLM provider unless separately changed.
- The chunks artifact remains fetched or managed as documented in
  `docs/api_deployment.md` and `docs/backend-runtime.md`.

Do not migrate the database, Qdrant, LLM provider, or chunks artifact process in
the Azure deployment skeleton stage.

## Azure Options

Azure App Service code deploy is the current staging target because it is
compatible with the active Azure for Students policy. Azure Container Apps and
Azure Container Registry remain blocked by policy for this subscription and are
not used by the staging workflow.

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
- `AZURE_WEBAPP_NAME`
- `AZURE_STAGING_BACKEND_URL`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `OPENROUTER_API_KEY`
- `LEGAL_QA_DATABASE_URL`
- `LEGAL_QA_SESSION_SECRET`
- `HF_TOKEN` only if the chunks artifact becomes private

The staging workflow uses Azure OIDC through `deploy-staging.yml`. Do not
request `id-token: write` in production until production deployment is
explicitly implemented and uses OIDC.

## Staging Deploy Flow

The manual staging workflow now:

1. validates dispatch inputs and required configuration names;
2. logs in to Azure through OIDC;
3. creates an App Service deployment package;
4. configures App Service app settings and startup command;
5. deploys the package to the configured Azure Web App;
6. runs `GET /health`;
7. optionally runs `GET /api/v1/readiness` when selected after config review.

It does not automate `POST /api/v1/legal-qa/ask`. The first/default staging
deployment mode is fake mode, and Stage 5 does not support real-mode staging
secrets or app settings.

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

- Roll back to the previous reviewed App Service deployment.
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

The workflow and documentation do not prove the following until the staging
workflow is manually configured and executed:

- Azure resource availability;
- registry publishing;
- Azure identity or secret access;
- real Qdrant connectivity;
- real LLM credentials;
- model memory behavior;
- chunks artifact availability;
- real `/api/v1/legal-qa/ask` behavior;
- production readiness.
