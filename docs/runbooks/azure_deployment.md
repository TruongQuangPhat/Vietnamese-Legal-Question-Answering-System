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

Stage 5 staging fake-mode deployment passed with `GET /health`. Stage 6 adds a
controlled `real-readiness` mode to the same staging workflow. It configures
real-mode app settings and checks only `GET /health` plus
`GET /api/v1/readiness`.

The staging workflow is `workflow_dispatch`-only and should not be added as a
required branch protection check because it does not run on pull requests.
Required checks for normal PRs should remain routine CI checks such as Backend
CI, Frontend CI, Protected Path Guard, Secret Scan, and Backend Container.

For the consolidated Azure staging resource plan, Stage 6 workflow behavior,
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
- `QDRANT_URL` for Stage 6 `real-readiness`
- `QDRANT_API_KEY` for Stage 6 `real-readiness`
- `OPENROUTER_API_KEY` for Stage 6 `real-readiness`
- `LEGAL_QA_DATABASE_URL` for Stage 6 `real-readiness`
- `LEGAL_QA_SESSION_SECRET` for Stage 6 `real-readiness`
- `LEGAL_QA_CHUNKS_URL` for Stage 6 `real-readiness`
- `LEGAL_QA_CHUNKS_SHA256` for Stage 6 `real-readiness`

The staging workflow uses Azure OIDC through `deploy-staging.yml`. Do not
request `id-token: write` in production until production deployment is
explicitly implemented and uses OIDC.

## Staging Deploy Flow

The manual staging workflow now:

1. validates dispatch inputs and required configuration names;
2. logs in to Azure through OIDC;
3. creates an App Service deployment package without the protected local
   `data/processed/legal_chunks.jsonl` file;
4. configures App Service app settings and startup command;
5. deploys the package to the configured Azure Web App;
6. uses plain Uvicorn startup so `/health` can serve without chunks or real
   dependencies;
7. runs `GET /health`;
8. runs `GET /api/v1/readiness` when selected in fake mode or automatically
   in Stage 6 `real-readiness`.

It does not automate `POST /api/v1/legal-qa/ask`. The first/default staging
deployment mode remains fake mode.

## Stage 6 Real-Readiness Runbook

The first real-readiness attempt fetched `legal_chunks.jsonl` inside the App
Service startup command and caused Azure `ContainerTimeout` before Uvicorn
served `/health`. Keep startup simple:

```bash
python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

Chunks should live outside the deployed repository tree at:

```text
/home/data/legal_chunks.jsonl
```

Before using `Deploy Staging` with `service_mode=real-readiness`:

1. Confirm the `staging` GitHub Environment contains the Stage 6 secret names.
2. Confirm the Azure federated credential for GitHub OIDC is configured.
3. Confirm the App Service is the staging Web App, not production.
4. If the current deployed app files do not already include
   `scripts/deployment/fetch_processed_chunks.py`, first dispatch the workflow
   in default fake mode to publish the code package with the plain Uvicorn
   startup command.
5. Prepare the chunks artifact through the App Service SSH console or another
   reviewed operator-controlled remote shell after deployment files are present:

   ```bash
   echo "chunk fetch: started"
   mkdir -p /home/data
   export LEGAL_QA_CHUNKS_PATH=/home/data/legal_chunks.jsonl
   python scripts/deployment/fetch_processed_chunks.py
   bytes="$(wc -c < /home/data/legal_chunks.jsonl)"
   echo "chunk fetch: destination=/home/data/legal_chunks.jsonl"
   echo "chunk fetch: bytes=${bytes}"
   echo "chunk fetch: checksum=passed"
   ```

   The command relies on App Service application settings for
   `LEGAL_QA_CHUNKS_URL` and `LEGAL_QA_CHUNKS_SHA256`. It must not print those
   values.
6. Dispatch the workflow manually with `service_mode=real-readiness`.
7. Review only the safe smoke output: HTTP status, readiness `ready`,
   `service_mode`, and sanitized check names/details.

Stop after readiness. Do not call `/api/v1/legal-qa/ask` in Stage 6. Azure Free
F1 may be insufficient for full real QA serving, so readiness failures should
be treated cautiously and investigated as configuration, dependency, network, or
resource-sizing signals.

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
