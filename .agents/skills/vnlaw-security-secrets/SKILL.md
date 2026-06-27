---
name: vnlaw-security-secrets
description: Use when reviewing or implementing secrets handling, PII safety, logging safety, API security, vector/graph DB exposure, Docker security, legal QA safety, protected paths, and safe agent operations.
---

# Security and Secrets Skill

Use this skill for security-sensitive code, documentation, tests, scripts, and reviews.

## Secrets

Never hardcode:

```text
API keys
database passwords
JWT secrets
connection strings
tokens
provider credentials
OpenRouter keys
LLM provider keys
```

Use `.env` and `pydantic-settings` when secrets are needed.

Keep `.env.example` with placeholders only.

Never print, log, commit, or paste real secrets.

## Protected Paths

Do not modify protected project data or official evaluation artifacts unless the user explicitly scopes the operation:

```text
data/raw/**
data/interim/**
data/reports/**
data/processed/legal_chunks.jsonl
data/eval/**
artifacts/reports/evaluation/**
```

Do not re-embed, re-index, upsert, recreate, delete Qdrant collections, overwrite benchmark data, or overwrite official evaluation artifacts unless explicitly requested.

## PII and Legal Question Safety

User legal questions may contain sensitive personal or business information.

Potential sensitive fields include:

```text
citizen ID
address
phone number
tax code
land parcel information
case details
company secrets
family disputes
medical facts
employment facts
criminal or sanction-related facts
financial details
```

Do not log raw legal questions, full prompts, full retrieved evidence, or full generated answers in production unless explicitly approved and redacted.

## Logging

Use structured logs with safe metadata:

```text
request_id
timestamp
operation
status
latency
safe error category
dataset/split name when applicable
artifact path when safe
```

Do not log:

```text
raw API keys
raw prompts
raw user PII
full legal dispute details
provider secrets
full traceback to user-facing outputs
full selected evidence if it contains sensitive user context
```

## API Security

API/backend is future or separately scoped unless explicitly requested.

When API work is scoped:

* use authentication for protected/admin endpoints;
* use rate limiting for production/protected endpoints;
* avoid `allow_origins=["*"]` in production;
* configure explicit timeouts;
* return safe error messages to clients;
* never expose internal stack traces;
* keep route handlers thin and avoid business logic in routes.

Suggested timeout behavior:

```text
LLM timeout -> safe 503 or fallback behavior depending on endpoint contract
retriever timeout -> safe 503 or fallback behavior depending on endpoint contract
```

## Database and Service Security

For production or deployed environments:

* Qdrant should require authentication and should not be publicly exposed.
* Neo4j, if implemented, must not expose Bolt publicly.
* Redis, if implemented, must require authentication and should not be public.
* Sanitize every Cypher input.
* Never build Cypher queries by string-concatenating raw user input.

Neo4j, Redis, Docker, and production deployment are future or separately scoped unless explicitly requested.

## LLM and RAG Safety

When working with legal QA generation:

* do not send secrets to the LLM;
* minimize user PII in prompts;
* do not log full prompts by default;
* do not allow citations outside selected evidence;
* do not use model memory as legal evidence;
* do not expose chain-of-thought;
* do not bypass citation validation or fallback checks.

Legal QA safety invariants:

```text
no trusted evidence -> no confident legal answer
no traceable citation -> fallback or invalid answer
parent context is auxiliary only and not directly citable
citation ID validity is required but not full human legal review
```

## Agent Safety

When Codex or an assistant works on this repository:

* do not print secrets;
* do not run `cat .env`;
* do not run destructive shell commands;
* do not delete raw data;
* do not modify protected paths unless explicitly scoped;
* do not run expensive crawls, real LLM calls, real Qdrant writes, embedding inference, reranking inference, or full benchmark pipelines unless explicitly scoped;
* use mocks, fakes, tiny fixtures, and `tmp_path` for routine tests.

Safe validation commands usually include:

```bash
env UV_CACHE_DIR=/tmp/vnlaw-uv-cache find src scripts tests -name '*.py' -exec uv run python -m py_compile {} +

uv run pytest tests/unit -q --durations=30
uv run pytest tests/integration -q --durations=30

uv run ruff check src scripts tests
uv run ruff format --check src scripts tests

uv lock --check
git diff --check
```

Protected path checks:

```bash
git diff --name-only -- \
  data/raw \
  data/interim \
  data/reports \
  data/processed/legal_chunks.jsonl \
  data/eval

git diff --name-only -- artifacts/reports/evaluation
```

Expected output is usually empty unless the user explicitly scoped data/artifact changes.

## Review Checklist

* [ ] No secrets in code.
* [ ] No secrets in tests.
* [ ] No secrets in docs or reports.
* [ ] `.env` is ignored.
* [ ] `.env.example` has placeholders only.
* [ ] No raw PII logs.
* [ ] No full prompt/evidence logging without explicit approval and redaction.
* [ ] Inputs are sanitized where external systems are involved.
* [ ] Timeouts are configured for external services when scoped.
* [ ] Production CORS is restricted when API is scoped.
* [ ] Protected paths are not modified unless explicitly scoped.
* [ ] Official evaluation artifacts are not overwritten unless explicitly scoped.
* [ ] Real LLM/Qdrant/embedding/reranking/full benchmark workflows are not run unless explicitly requested.

## Do Not

* Do not expose stack traces to users.
* Do not log full prompts with sensitive user content.
* Do not commit raw credentials.
* Do not use wildcard CORS in production.
* Do not run destructive shell commands without explicit instruction.
* Do not modify protected corpus or evaluation artifacts without explicit scope.
* Do not call real LLM/API, Qdrant, embedding, reranking, or full benchmark workflows unless explicitly requested.
