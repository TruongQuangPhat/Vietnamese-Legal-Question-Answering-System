---
name: vnlaw-api-backend
description: Use for FastAPI backend implementation, request/response schemas, service boundaries, dependency injection, rate limits, timeouts, request tracing, and API testing.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# API Backend Skill

Use this skill for FastAPI backend work (Phase 13).

**Prerequisites**: Phases 0-12 must be stable. Retrieval and generation pipelines must work.

## Expected Files

```text
src/api/main.py              # FastAPI app factory
src/api/dependencies.py      # DI container
src/api/schemas.py           # Pydantic request/response models
src/api/routes/qa.py         # POST /api/v1/qa
src/api/routes/health.py     # GET /health
src/api/routes/admin.py      # admin endpoints (optional)

src/services/qa_service.py   # end-to-end QA orchestration
src/core/config.py           # settings
src/core/exceptions.py       # custom exceptions
src/core/logger.py           # structured logging

tests/unit/api/
tests/integration/api/
```

## API Principles

- Keep route handlers thin — no business logic in routes.
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

Request model:

```text
question: str
query_date: date | None
user_context: str | None
domain: str | None
jurisdiction: str | None
max_contexts: int | None
confidence_threshold: float | None
```

Response model:

```text
request_id: str
answer: str
citations: list[Citation]
confidence_score: float
retrieved_context_summary: list[str]
fallback_used: bool
warnings: list[str]
processing_time_ms: float
```

## Error Handling

Use custom exceptions and consistent error responses.

Expected behavior:

- validation error -> 422;
- low confidence fallback -> 200 with `fallback_used=true`;
- retriever timeout -> 503;
- LLM timeout -> 503;
- unauthorized admin request -> 401/403.

Do not return raw internal exceptions.

## OOP and Docstring Rules

Expected components:

```text
QAService                 # end-to-end QA orchestration
RetrievalService          # retrieval + reranking
GenerationService         # LLM call + prompt rendering
CitationValidationService # citation integrity checks
HealthService             # health checks
```

Rules:

- FastAPI routes should call services, not implement retrieval logic.
- Services should depend on typed interfaces, not concrete infrastructure clients.
- Public API schemas, services, and route handlers must have Google-style docstrings.
- API docstrings must explain request/response behavior and failure modes.

## Do Not

- Do not put retrieval logic in route handlers.
- Do not return raw internal exceptions.
- Do not expose stack traces.
- Do not use wildcard CORS in production.
- Do not bypass Pydantic response schemas.
- Do not log sensitive user data unnecessarily.
