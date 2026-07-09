---
name: vnlaw-ci-cd
description: Use for GitHub Actions, CI/CD workflow design, CI quality gates, frontend/backend build checks, protected-path guards, secret scanning, Docker/container build checks, staging/production deploy gates, post-deploy smoke checks, and manual evaluation refresh workflow routing for VnLaw-QA.
---

# CI/CD Skill

Use this skill when planning, implementing, reviewing, or documenting CI/CD for
VnLaw-QA.

Canonical repository rules remain in `AGENTS.md`. Current architecture,
deployment status, protected paths, and workflow boundaries remain in
`PROJECT_CONTEXT.md`. Do not duplicate those files here.

## Companion Skills

Read these skills with this one when the task crosses their scope:

- `vnlaw-security-secrets` for secrets, tokens, logs, DB URLs, session secrets,
  provider keys, Docker security, and smoke-output safety.
- `vnlaw-workflow-review` for branch discipline, cross-workflow boundaries,
  protected-path checks, PR review, and final reporting.
- `vnlaw-api-backend` for FastAPI/backend service checks, health/readiness
  behavior, fake-mode API smoke, and backend runtime boundaries.
- `vnlaw-evaluation-cicd` for benchmark, regression, citation/fallback, and
  evaluation quality gates.
- `vnlaw-docstrings-documentation` for durable documentation updates.

## Safe Default CI Policy

CI must be offline-safe and fake-mode by default.

Routine CI must not:

- call real LLM providers;
- mutate or require real Qdrant;
- crawl legal sources;
- index, re-index, embed, or run reranking inference;
- run full benchmark/evaluation workflows unless explicitly scoped;
- call production `POST /api/v1/legal-qa/ask` unless explicitly approved.

Do not loosen fallback, citation, evidence, retrieval, or generation gates just
to make CI pass.

## Recommended CI Jobs

Future GitHub Actions should start with small, isolated jobs:

- backend Python checks;
- frontend lint/build checks;
- protected-path guard;
- secret scan;
- backend fake-mode container build and `/health` smoke.

Documented future workflow names may include:

```text
ci.yml
frontend-ci.yml
protected-paths.yml
secret-scan.yml
backend-container.yml
```

Do not create workflow files unless the task explicitly asks for implementation.

## GitHub Actions Security

Future workflows should use least-privilege `permissions` at the workflow or
job level. Grant write permissions only to jobs that need them.

Avoid `pull_request_target` unless the workflow has been explicitly reviewed
for fork, checkout, secret exposure, and script execution risks.

Deployment `id-token: write` permissions for OIDC should appear only in deploy
jobs that need cloud identity federation. Build, lint, test, protected-path,
and secret-scan jobs should not receive deployment identity permissions.

Third-party actions must be reviewed before adoption and pinned appropriately
for the risk level. Prefer official or widely maintained actions, avoid
unreviewed composite actions, and document why a third-party action is needed.

## Recommended CD Gates

Production deployment must remain guarded:

- CI must pass before deploy.
- Deploy to staging before production.
- Require manual approval before production.
- Run `/health` and `/api/v1/readiness` smoke after deploy.
- Run conversation CRUD smoke where appropriate.
- Run exactly one controlled `/api/v1/legal-qa/ask` smoke only after explicit
  approval and reviewed environment readiness.

Documented future deployment workflow names may include:

```text
deploy-staging.yml
deploy-production.yml
evaluation-refresh.yml
```

## Validation Commands

For CI/CD-related PRs, run the relevant subset and report skipped checks with
reasons:

```bash
git status --short
git diff --check
uv lock --check
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
env UV_CACHE_DIR=/tmp/vnlaw-uv-cache find src scripts tests -name '*.py' -exec uv run python -m py_compile {} +
uv run pytest tests/unit -q --durations=30
```

When frontend or CI config touches frontend behavior, also run frontend
lint/build checks. When container config changes, run Docker build and
fake-mode `/health` smoke.

## Protected Path Checks

Routine CI/CD work must not modify:

```text
data/raw/
data/interim/
data/reports/
data/processed/legal_chunks.jsonl
data/eval/
artifacts/reports/evaluation/
```

Use `git diff --name-only` checks against those paths before final reporting.

## Secret Safety

Never print, log, or commit:

- `.env`;
- `apps/frontend/.env.local`;
- `LEGAL_QA_DATABASE_URL`;
- `LEGAL_QA_SESSION_SECRET`;
- OpenRouter, OpenAI, Anthropic, Qdrant, or Hugging Face tokens;
- Authorization headers;
- raw smoke session tokens.

Only document environment variable names and placeholder values.

## Manual Evaluation Refresh Routing

Evaluation refresh is not normal PR CI. It should be a guarded
`workflow_dispatch`-style path with explicit approval, a unique output
directory, no overwriting historical reports, no tuning on the held-out split,
and no Naive RAG rerun unless explicitly requested.

## Final Report Checklist

Final reports for CI/CD work should include:

- changed files;
- checks run;
- skipped checks with reasons;
- protected paths clean;
- secrets clean;
- no real services called unless explicitly approved;
- remaining deployment risks.
