---
name: vnlaw-api-backend
description: Use for future FastAPI backend work, request/response schemas, service boundaries, dependency injection, timeouts, request tracing, API testing, and safe wrapping of the legal QA/RAG workflow.
---

# API Backend Skill

Use this skill for FastAPI backend implementation, maintenance, or review.

Current project status: API/backend implementation is future or separately scoped. Retrieval, generation, citation validation, fallback control, and evaluation workflows are already implemented outside the API layer. Do not create `src/api/` or public QA endpoints unless the user explicitly scopes an API/backend task.

## Goal

Expose the legal QA/RAG workflow through a safe, typed, and observable API boundary.

The API should wrap the existing QA workflow; it should not reimplement retrieval, generation, citation validation, or fallback logic inside route handlers.

Expected backend flow:

```text
HTTP request
  → request validation
  → request_id / tracing
  → QA service
  → retrieval/generation workflow
  → citation validation
  → fallback handling
  → typed API response
```

## Current QA Workflow to Wrap

When an API task is explicitly scoped, the backend should wrap the current evaluated system behavior:

```text
coverage-aware hybrid retrieval
  → evidence selection
  → strict legal generation
  → citation ID guard
  → answerability fallback guard
```

Reranking is not part of the adopted pipeline. Time-aware filtering is not part of the current adopted workflow unless separately implemented and evaluated.

## Expected Future Files

Use the repository’s current structure when implementing. Possible API/backend files may include:

```text
src/api/main.py
src/api/dependencies.py
src/api/schemas.py
src/api/routes/qa.py
src/api/routes/health.py

src/services/qa_service.py
src/core/config.py
src/core/exceptions.py
src/core/logger.py

tests/unit/api/
tests/integration/api/
```

Do not create admin routes, authentication, or rate-limiting infrastructure unless the user explicitly scopes them.

## API Principles

* Keep route handlers thin.
* Put business logic in services/use-cases.
* Use dependency injection for retrievers, generators, stores, and settings.
* Use Pydantic V2 request/response models.
* Every response should include `request_id`.
* Use structured JSON logging.
* Use explicit timeouts.
* Never expose internal stack traces.
* Do not log sensitive user input unnecessarily.
* Keep legal safety behavior consistent with the non-API workflow.

For protected/admin endpoints, use authentication and authorization. Do not assume all local development QA endpoints require JWT unless explicitly scoped.

## QA Endpoint

Possible endpoint:

```text
POST /api/v1/qa
```

Request model may include:

```text
question
max_contexts optional
domain optional
jurisdiction optional
query_date optional  # reserved for future time-aware behavior unless implemented
```

Response model should include:

```text
request_id
answer
citations
fallback_used
fallback_reasons
warnings
retrieved_context_summary
processing_time_ms
```

Avoid exposing raw internal retrieval payloads unless the endpoint is explicitly a debug/admin endpoint.

## Error Handling

Use custom exceptions and consistent error responses.

Expected behavior:

* validation error -> 422;
* safe fallback -> 200 with `fallback_used=true`;
* retriever timeout -> 503;
* LLM timeout -> 503;
* unauthorized protected/admin request -> 401/403;
* unexpected internal error -> sanitized 500 response.

Do not return raw internal exceptions.

## Legal QA Safety Requirements

The API must preserve these invariants:

* no trusted evidence -> no confident legal answer;
* no traceable citation -> fallback or invalid answer;
* parent context is auxiliary only and not directly citable;
* do not fabricate laws, articles, clauses, points, penalties, dates, or citations;
* do not use model memory as legal evidence;
* the system is a legal research assistant, not legal advice.

## OOP and Docstring Rules

Expected components may include:

```text
QAService
RetrievalService
GenerationService
CitationValidationService
FallbackPolicy
HealthService
```

Rules:

* FastAPI routes should call services, not implement retrieval logic.
* Services should depend on typed interfaces, not concrete infrastructure clients when possible.
* Public API schemas, services, and route handlers must have Google-style docstrings.
* API docstrings must explain request/response behavior and failure modes.

## Tests

Add tests for:

* request validation;
* fallback behavior;
* invalid citation response behavior;
* timeout handling;
* request_id propagation;
* citation response format;
* route handlers not exposing stack traces;
* dependency injection with fake retrievers/generators;
* no real LLM/Qdrant calls in unit or integration tests unless explicitly scoped.

## Do Not

* Do not create API files unless the user explicitly scopes an API/backend task.
* Do not put retrieval logic in route handlers.
* Do not bypass the existing citation/fallback workflow.
* Do not return raw internal exceptions.
* Do not expose stack traces.
* Do not use wildcard CORS in production.
* Do not bypass Pydantic response schemas.
* Do not log sensitive user data unnecessarily.
* Do not claim time-aware filtering, reranking, or API deployment is adopted unless separately implemented and evaluated.
