---
name: vnlaw-api-backend
description: Use for FastAPI backend implementation, request/response schemas, service boundaries, dependency injection, rate limits, timeouts, request tracing, and API testing.
---

# API Backend Skill

Use this skill for FastAPI backend work.
Current project status: API/backend implementation is a future phase. Do not
create `src/api/` or QA endpoints until retrieval/generation gates have passed.

## Expected Future Files

```text
src/api/main.py
src/api/dependencies.py
src/api/schemas.py
src/api/routes/qa.py
src/api/routes/health.py
src/api/routes/admin.py

src/services/qa_service.py
src/core/config.py
src/core/exceptions.py
src/core/logger.py

tests/unit/api/
tests/integration/api/
```

## API Principles

- Keep route handlers thin.
- Put business logic in services/use-cases.
- Use dependency injection for retrievers, generators, stores, and settings.
- Use Pydantic V2 request/response models.
- Every response must include `request_id`.
- Use structured JSON logging.
- Use explicit timeouts.
- Use rate limiting.
- Use JWT Bearer auth for protected endpoints.
- Never expose internal stack traces.

## QA Endpoint

Expected endpoint:

```text
POST /api/v1/qa
```

Request model should include:

```text
question
query_date optional
user_context optional
domain optional
jurisdiction optional
max_contexts optional
```

Response model should include:

```text
request_id
answer
citations
confidence_score
retrieved_context_summary
fallback_used
warnings
processing_time_ms
```

## Error Handling

Use custom exceptions and consistent error responses.

Expected behavior:

- validation error → 422;
- low confidence fallback → 200 with `fallback_used=true`;
- retriever timeout → 503;
- LLM timeout → 503;
- unauthorized admin request → 401/403.

Do not return raw internal exceptions.

## OOP and Docstring Rules

Expected components:

```text
QAService
RetrievalService
GenerationService
CitationValidationService
HealthService
```

Rules:

- FastAPI routes should call services, not implement retrieval logic.
- Services should depend on typed interfaces, not concrete infrastructure clients when possible.
- Public API schemas, services, and route handlers must have Google-style docstrings.
- API docstrings must explain request/response behavior and failure modes.

## Tests

Add tests for:

- request validation;
- fallback behavior;
- timeout handling;
- request_id propagation;
- citation response format;
- auth/rate-limit behavior for protected endpoints;
- route handler not exposing stack traces.

## Do Not

- Do not put retrieval logic in route handlers.
- Do not return raw internal exceptions.
- Do not expose stack traces.
- Do not use wildcard CORS in production.
- Do not bypass Pydantic response schemas.
- Do not log sensitive user data unnecessarily.
