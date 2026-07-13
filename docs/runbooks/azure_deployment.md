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

The staging workflow `.github/workflows/deploy-staging.yml` is a manual Azure
App Service source-deploy workflow for the restored staging/recovery Web App.
It defaults to fake mode, uses Azure OIDC, updates only the configured staging
Web App, and runs safe smoke checks. App Service source/zip deployment is legacy
and must not be used for production real embedding dependencies.

Production backend deployment is now container-based through
`.github/workflows/deploy-production-container.yml`. The planning-only
`.github/workflows/deploy-production.yml` remains non-deploying.

Azure App Service source deploy remains the current staging/recovery fallback.
For production, use Azure Container Registry plus Azure App Service for
Containers. If App Service for Containers proves unsuitable, review Azure
Container Apps as a separate fallback rather than returning to source/zip deploy
for real embedding dependencies.

Stage 5 staging fake-mode deployment passed with `GET /health`. Stage 6 adds a
controlled `real-readiness` mode to the same staging workflow. It configures
real-mode app settings and checks only `GET /health` plus
`GET /api/v1/readiness`. Stage 6 passed on the B1 staging App Service after the
chunks artifact was prepared at `/home/data/legal_chunks.jsonl`.

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
- Azure App Service hosts the FastAPI API for the current staging/recovery
  deployment.
- Azure App Service for Containers hosts the production backend after the
  production container workflow passes smoke checks.
- Neon or another reviewed PostgreSQL service remains conversation storage
  unless separately changed.
- Qdrant Cloud remains the vector database unless separately changed.
- OpenRouter with Gemini remains the LLM provider unless separately changed.
- The chunks artifact remains fetched or managed as documented in
  `docs/api_deployment.md` and `docs/backend-runtime.md`.

Do not migrate the database, Qdrant, LLM provider, or chunks artifact process in
the Azure deployment skeleton stage.

## Azure Options

Azure App Service code deploy is the current staging/recovery target. It is not
the production real-embedding deployment path. Remote Oryx source builds with
the embedding extra timed out, and prebuilt zip deployment produced a large
package that Kudu rejected with `502`; partially applied settings then caused
startup failure with `No module named uvicorn`.

Use Azure Container Registry plus Azure App Service for Containers for the first
production backend path. Required Azure resources should exist before dispatch:

- Azure Container Registry;
- production Web App such as `vnlaw-backend-prod-phat`;
- App Service plan sized for BGE-M3/Torch CPU runtime;
- managed identity with `AcrPull` or equivalent image-pull permission;
- production backend URL stored as `AZURE_PRODUCTION_BACKEND_URL`.

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

For production container deployment, also configure the GitHub Environment
`production` with these secret names:

- `AZURE_ACR_NAME`
- `AZURE_ACR_LOGIN_SERVER`
- `AZURE_PRODUCTION_WEBAPP_NAME`
- `AZURE_PRODUCTION_BACKEND_URL`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `OPENROUTER_API_KEY`
- `LEGAL_QA_DATABASE_URL`
- `LEGAL_QA_SESSION_SECRET`
- `LEGAL_QA_CHUNKS_URL`
- `LEGAL_QA_CHUNKS_SHA256`

The staging workflow uses Azure OIDC through `deploy-staging.yml`. Do not
request `id-token: write` in production until production deployment is
explicitly implemented and uses OIDC.

## Staging Deploy Flow

The manual staging workflow now:

1. validates dispatch inputs and required configuration names;
2. logs in to Azure through OIDC;
3. creates an App Service deployment package without the protected local
   `data/processed/legal_chunks.jsonl` file, verifies the operator chunks
   fetch script is included, and prebuilds Python dependencies into
   `.python_packages/lib/site-packages`;
4. configures App Service app settings and startup command;
5. deploys the prebuilt package to the configured Azure Web App with Azure
   remote build disabled;
6. uses plain Uvicorn startup so `/health` can serve without chunks or real
   dependencies;
7. runs `GET /health`;
8. runs `GET /api/v1/readiness` when selected in fake mode or automatically
   in Stage 6 `real-readiness`.

It does not automate `POST /api/v1/legal-qa/ask`. The first/default staging
deployment mode remains fake mode.

Do not extend this source/zip path for real embedding production. It is kept so
the restored `vnlaw-backend-staging-phat` source-deploy app can remain a
staging/recovery fallback.

### App Service dependency build strategy

The real `/ask` path needs both `qdrant` and `embedding` optional dependency
groups. The `embedding` group includes `flagembedding`, `sentence-transformers`,
`transformers`, and `torch`, so Azure App Service/Oryx source deployment can be
slow on B1. One failed deployment showed Oryx dependency installation completing
after roughly 412 seconds, build snippets after roughly 429 seconds, and then
OneDeploy spending the remaining workflow time compressing/deploying until the
GitHub job was canceled near 29 minutes.

The staging workflow therefore prebuilds dependencies on the GitHub-hosted
Linux runner into:

```text
.python_packages/lib/site-packages
```

and configures App Service with:

```env
SCM_DO_BUILD_DURING_DEPLOYMENT=false
ENABLE_ORYX_BUILD=false
PYTHONPATH=/home/site/wwwroot/.python_packages/lib/site-packages
```

This keeps the startup command lightweight and avoids running the heavy Oryx
remote build during each deployment. The workflow package step has a bounded
timeout for dependency prebuild, exports requirements without the local editable
project entry, filters CUDA/Triton packages for the CPU-only B1 target, and the
Azure deploy step has a bounded CLI deployment timeout. If the prebuilt package
becomes too large or still times out, treat that as an App Service source-deploy
limitation and review a container-based deployment or lighter query-embedding
runtime as a later separate architecture decision.

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

The workflow package step verifies that
`scripts/deployment/fetch_processed_chunks.py` is included in the App Service
deployment package. If that file is missing under `/home/site/wwwroot` in the
SSH console, dispatch the default fake-mode deployment first so the latest code
package is present without changing real-readiness settings.

Before using `Deploy Staging` with `service_mode=real-readiness`:

1. Confirm the `staging` GitHub Environment contains the Stage 6 secret names.
2. Confirm the Azure federated credential for GitHub OIDC is configured.
3. Confirm the App Service is the staging Web App, not production.
4. Confirm `/home/site/wwwroot/scripts/deployment/fetch_processed_chunks.py`
   exists. If it does not, dispatch the workflow in default fake mode to publish
   the code package with the plain Uvicorn startup command.
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

Successful Stage 6 readiness requires:

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

Stop after readiness. Do not call `/api/v1/legal-qa/ask` in Stage 6. The
separate `/ask` smoke is a later controlled step after explicit approval and
reviewed environment readiness.

## Stage 7 Controlled Ask Smoke Runbook

Stage 7 uses `.github/workflows/staging-ask-smoke.yml`. It is a separate manual
workflow and is not part of `deploy-staging.yml`.

Use this only after Stage 6 real-readiness has passed:

```text
GET /health -> HTTP 200
GET /api/v1/readiness -> HTTP 200 and ready true
```

This step calls real services and may incur Azure, Qdrant, and LLM provider
costs. It must not be used as a benchmark or load test.

Operator steps:

1. Confirm the current GitHub branch selector is `main`.
2. Open `Staging Ask Smoke`.
3. Use GitHub Environment `staging`.
4. Set `confirm_real_ask` exactly to:

   ```text
   I_UNDERSTAND_THIS_CALLS_REAL_SERVICES
   ```

5. Use the default low-risk legal research question or provide another
   non-sensitive Vietnamese legal research question.
6. Keep `timeout_seconds` at `120` unless a reviewed staging resource issue
   requires a different bounded timeout.
7. Dispatch the workflow once.
8. Review only the safe summary: HTTP status, response JSON keys, answer length,
   citation count, evidence count, and response latency when present.

Stop after one `/api/v1/legal-qa/ask` request. Do not retry repeatedly, do not
run concurrent requests, and do not paste full generated answers, prompts,
evidence text, headers, session identifiers, provider keys, database URLs, or
environment variables into logs or tickets.

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

The zero citation/evidence count should be investigated in a later
quality/citation validation stage. It is not a Stage 7 failure because this
runbook step validates one controlled real request, bounded logging, and no
repeated `/ask` calls. The difference between 54 seconds of workflow request
duration and 1995 ms response latency is also a follow-up observation for
cold-start, network, App Service, or client-side timing analysis.

## Stage 8 Frontend to Azure Backend Integration Runbook

The Vercel frontend can target Azure without code changes because the frontend
uses this build-time variable:

```env
NEXT_PUBLIC_API_BASE_URL
```

For Vercel Preview or staging validation, set:

```env
NEXT_PUBLIC_API_BASE_URL=https://vnlaw-backend-staging-phat-feg8eabzgxhuafc3.japaneast-01.azurewebsites.net
```

Do not change Vercel Production until a Preview deployment has passed UI smoke.
If production currently points to Render, the production migration step is to
change Vercel Production `NEXT_PUBLIC_API_BASE_URL` from:

```env
NEXT_PUBLIC_API_BASE_URL=https://vnlaw-qa-backend.onrender.com
```

to the accepted Azure backend origin and redeploy Vercel.

Azure backend CORS must include the exact Vercel browser origin. The backend
default only allows local development. For Preview, add the exact Preview URL
generated by Vercel. For Production, include:

```env
CORS_ALLOWED_ORIGINS=["https://vnlaw-qa.vercel.app"]
```

When both Preview and Production should call Azure, configure Azure App Service
with every accepted exact origin:

```env
CORS_ALLOWED_ORIGINS=["https://vnlaw-qa.vercel.app","https://<vercel-preview-origin>"]
```

Migration checklist:

1. Set Vercel Preview `NEXT_PUBLIC_API_BASE_URL` to the Azure backend URL.
2. Add the exact Vercel Preview URL to Azure App Service
   `CORS_ALLOWED_ORIGINS`.
3. Redeploy Vercel Preview.
4. Run UI smoke against Azure. Do not run `/api/v1/legal-qa/ask` loops,
   benchmarks, load tests, or concurrent request tests.
5. If Preview passes, schedule the Vercel Production backend URL switch.
6. Keep the Render backend URL as the rollback value until Azure production
   traffic is accepted.
7. Plan Render decommission separately after Azure acceptance: remove
   Render-only secrets, disable Render traffic, preserve safe logs, and record
   the final rollback boundary.

## Stage 9 Vercel Preview UI Smoke Runbook

Stage 9 is a manual browser smoke from Vercel Preview to the Azure staging
backend. It does not switch Vercel Production.

1. In Vercel Preview environment settings, set:

   ```env
   NEXT_PUBLIC_API_BASE_URL=https://vnlaw-backend-staging-phat-feg8eabzgxhuafc3.japaneast-01.azurewebsites.net
   ```

2. Redeploy Vercel Preview.
3. Copy the exact generated Vercel Preview URL.
4. In Azure App Service app settings, set `CORS_ALLOWED_ORIGINS` to include the
   exact Preview origin. If only Preview should be allowed during the smoke:

   ```env
   CORS_ALLOWED_ORIGINS=["https://<vercel-preview-origin>"]
   ```

   If Production and Preview should both be allowed:

   ```env
   CORS_ALLOWED_ORIGINS=["https://vnlaw-qa.vercel.app","https://<vercel-preview-origin>"]
   ```

5. Restart Azure App Service after saving `CORS_ALLOWED_ORIGINS`.
6. Open the Vercel Preview frontend.
7. Open browser DevTools and select the Network tab.
8. Submit exactly one safe Vietnamese legal question:

   ```text
   Theo Bộ luật Dân sự Việt Nam, hợp đồng dân sự có thể bị vô hiệu trong những trường hợp nào?
   ```

9. Verify the request URL goes to Azure:

   ```text
   https://vnlaw-backend-staging-phat-feg8eabzgxhuafc3.japaneast-01.azurewebsites.net
   ```

10. Verify the request does not go to Render.
11. Verify the UI displays a response.
12. Verify no browser CORS error appears.

Pass criteria:

- Vercel Preview uses the Azure backend origin.
- Azure CORS allows the exact Vercel Preview origin.
- The UI renders one response.
- Exactly one question is submitted.
- No CORS error appears.

Fail and rollback notes:

- If the Network tab shows Render, fix Vercel Preview
  `NEXT_PUBLIC_API_BASE_URL` and redeploy Preview.
- If CORS fails, fix Azure `CORS_ALLOWED_ORIGINS`, restart App Service, and
  retest once.
- If the UI cannot render a response, stop and preserve safe browser/Azure logs
  without full answer text, prompts, headers, session identifiers, provider
  keys, database URLs, or environment dumps.
- Do not switch Vercel Production in Stage 9.
- Render remains the rollback backend until a later production migration passes.

## Future Production Deploy Flow

1. Staging passes.
2. Manual production approval is granted through the GitHub Environment.
3. Deploy production.
4. Run safe smoke checks.
5. Optionally run exactly one controlled `POST /api/v1/legal-qa/ask` smoke only
   after explicit approval and reviewed environment readiness.
6. Stop if timeout, out-of-memory, or `5xx` symptoms occur. Do not retry
   production ask requests repeatedly.

## Production Container Backend Runbook

Use `.github/workflows/deploy-production-container.yml` only after the Azure
production container resources are created and reviewed.

Manual dispatch guard:

```text
I_UNDERSTAND_THIS_DEPLOYS_PRODUCTION_CONTAINER_BACKEND
```

The workflow:

1. checks out the repository;
2. validates required secret names without printing values;
3. downloads `legal_chunks.jsonl` into GitHub runner temporary storage;
4. verifies the configured SHA256;
5. builds `docker/backend/Dockerfile` target `production-with-chunks`;
6. runs local fake-mode container `GET /health`;
7. logs in to Azure with OIDC;
8. pushes the image to Azure Container Registry;
9. configures the separate production Web App container image and settings;
10. restarts the production backend;
11. runs production `GET /health`;
12. runs production `GET /api/v1/readiness`.

It must not call `/api/v1/legal-qa/ask`. It must not fetch chunks during app
startup. The chunks file is copied into the private production image at:

```text
/home/data/legal_chunks.jsonl
```

Production container app settings include:

```env
acrUseManagedIdentityCreds=true
WEBSITES_CONTAINER_START_TIME_LIMIT=1800
WEBSITES_PORT=8000
PORT=8000
LEGAL_QA_SERVICE_MODE=real
LEGAL_QA_CHUNKS_PATH=/home/data/legal_chunks.jsonl
CORS_ALLOWED_ORIGINS=["https://vnlaw-qa.vercel.app"]
```

The Web App must also keep `alwaysOn=true` and Docker container logging set to
`filesystem`. The production deploy workflow persists these settings so manual
portal fixes are not required after each deployment.

Secrets remain environment values only: Qdrant, OpenRouter, database URL, and
session secret values must never be printed in workflow logs.

### Production container troubleshooting

App Service source/zip deployment is deprecated for the real embedding path.
Remote Oryx builds with the embedding extra timed out, and the prebuilt zip
package became too large for reliable Kudu deployment. Use the container
workflow for real production dependencies and keep the restored source-deploy
staging app only as a recovery fallback.

If `/health` returns `503` after deployment:

- Confirm the production Web App is using the pushed container image.
- Confirm `acrUseManagedIdentityCreds=true` and the Web App identity has
  `AcrPull` on the registry.
- Confirm `WEBSITES_PORT=8000`, `PORT=8000`, and the container command starts
  Uvicorn on `0.0.0.0:8000`.
- Confirm `WEBSITES_CONTAINER_START_TIME_LIMIT=1800` and `alwaysOn=true`.
- Use Docker container filesystem logs and Azure log stream, but do not print
  secrets, environment dumps, headers, cookies, prompts, retrieved legal text,
  provider responses, or full user questions.

If `/api/v1/legal-qa/ask` times out:

- Do not loop real ask requests. Run only the single manually confirmed smoke.
- Check sanitized `legal_qa_request_timing` entries for the last completed
  stage: request validation, context loading, retrieval-question preparation,
  embedding/model loading, query embedding, Qdrant retrieval, provider call,
  response mapping, completion, or failure.
- The embedding/model-loading and query-embedding entries are coarse markers:
  BGE-M3 model loading and query embedding occur inside the retrieval adapter,
  so the following retrieval timing may include both embedding and Qdrant work.
- A timeout before `qdrant_retrieval` completes usually points to BGE-M3 or
  retrieval cold-start cost on CPU. A timeout after `llm_generation_provider_call`
  starts points to provider latency or egress.
- Scale from B1 to B2 or P1v3 when model cold loading, CPU query embedding, or
  memory pressure remains above the bounded smoke timeout.
- Bake the model cache into the image only after confirming the bottleneck is
  repeated model download or initialization, and keep the image private.
- Keep Vercel Production unchanged until production ask smoke passes.

## Production Ask Smoke Runbook

Run `.github/workflows/production-ask-smoke.yml` only after production
container deploy returns healthy and ready.

Manual dispatch guard:

```text
I_UNDERSTAND_THIS_CALLS_REAL_PRODUCTION_SERVICES
```

The workflow calls exactly:

```text
GET /health
GET /api/v1/readiness
POST /api/v1/legal-qa/ask
```

It sends one request only. `timeout_seconds` is configurable up to 600 seconds
for production ML cold start. It fails if the response reports
`decision=error`, contains `internal_error`, has `metadata.model=null`, has
`metadata.retrieval_question_prepared=false`, or returns the generic internal
error answer. It prints only safe summary fields: HTTP status, response keys,
answer length, citation/evidence counts, model-present status,
retrieval-question-prepared status, sanitized warnings, and latency when
present.

## Vercel Production Cutover

Do not change Vercel Production until the Azure production container backend
has passed deploy smoke and one controlled production ask smoke.

Cutover sequence:

1. Deploy Azure production container backend.
2. Confirm `/health` returns HTTP 200.
3. Confirm `/api/v1/readiness` returns HTTP 200 and `ready=true`.
4. Run one controlled production `/ask` smoke.
5. Confirm Azure `CORS_ALLOWED_ORIGINS` includes exactly:

   ```text
   https://vnlaw-qa.vercel.app
   ```

6. Set Vercel Production:

   ```env
   NEXT_PUBLIC_API_BASE_URL=<Azure production container backend URL>
   ```

7. Redeploy Vercel Production.
8. Run one browser UI smoke against Vercel Production.
9. Keep Render as rollback until Azure production is stable.
10. Decommission Render only after a separate reviewed cleanup plan removes
    Render-only secrets, disables Render traffic, preserves safe logs, and
    records the rollback boundary.

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
