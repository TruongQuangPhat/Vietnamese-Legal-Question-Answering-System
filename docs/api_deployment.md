# API & Deployment

## Overview

The API & Deployment phase exposes the VnLaw-QA system through a RESTful FastAPI service and packages it for production deployment using Docker and container orchestration. This phase is the final integration step that combines all previous components into a cohesive, secure, and observable service.

This phase is implemented only after the core retrieval/generation pipeline and evaluation gates are stable.

## Quick Start

**Intended deployment** (design phase, not yet implemented):

```bash
# Build and run with Docker Compose (development)
docker-compose up -d

# Check health
curl http://localhost:8000/health

# Run a query
curl -X POST "http://localhost:8000/api/v1/qa" \
  -H "Content-Type: application/json" \
  -d '{"query": "Quyền sử dụng đất của hộ gia đình là gì?"}'
```

**Expected environment**:
- FastAPI service on port 8000
- Qdrant on port 6333
- Neo4j on port 7687 (optional, for GraphRAG)
- Redis (optional, for caching)
- Docker Compose for local dev; Kubernetes for production.

## Architecture

```
┌────────────────────────────────────────────┐
│         Client Request (HTTPS)            │
└────────────┬───────────────────────────────┘
             │
             ▼
┌──────────────────────┐
│  FastAPI              │
│  Application         │
│  (async routes)      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Middleware          │
│  (rate limit, auth,  │
│   logging, CORS)     │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Use Case            │
│  Handler             │
│  (Naive/Advanced/    │
│   GraphRAG)          │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Infrastructure      │
│  Clients             │
│  (Qdrant, Neo4j,    │
│   Redis, Claude)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Structured          │
│  Response            │
└──────────────────────┘
```

## Components

### 1. FastAPI Application

**Goal**: Provide HTTP API for legal QA with async request handling.

**Core endpoints**:
- `GET /health` — health check (liveness/readiness)
- `POST /api/v1/qa` — Naive/Advanced RAG QA
- `POST /api/v1/graph_qa` — GraphRAG QA (when enabled)
- `GET /metrics` — Prometheus metrics (optional)
- `GET /docs` — Auto-generated OpenAPI/Swagger UI

**Request handling**:
- FastAPI routes are thin wrappers; business logic in use-case classes (e.g., `NaiveRAGUseCase`, `GraphRAGUseCase`).
- Dependency injection for infrastructure clients (Qdrant, Neo4j, Redis, LLMClient).
- Async all the way: no blocking I/O in main thread.
- Request validation via Pydantic models.

**Configuration**:
- Environment variables via `pydantic-settings` (see Configuration section).
- Logging configured at startup with `structlog`.

**Example route handler**:

```python
@router.post("/qa", response_model=QAResponse)
async def qa_endpoint(request: QARequest, use_case: NaiveRAGUseCase = Depends(get_naive_rag_use_case)):
    try:
        result = await use_case.execute(
            query=request.query,
            max_chunks=request.max_chunks,
            confidence_threshold=request.confidence_threshold
        )
        return result
    except Exception as e:
        logger.error("qa_failed", query=request.query, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
```

### 2. Configuration & Secrets

**Goal**: Manage environment-specific settings securely.

**Method**: `pydantic-settings` with `.env` files (never commit secrets).

**Settings model**:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4
    cors_origins: list[str] = ["*"]  # restrict in prod

    # Security
    api_key_header: Optional[str] = None  # if set, require X-API-Key header
    jwt_secret: Optional[str] = None

    # Qdrant
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: Optional[str] = None
    qdrant_collection: str = "vnlaw_qa_chunks"

    # Neo4j
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: Optional[str] = None

    # Redis (caching)
    redis_url: Optional[str] = None

    # LLM
    anthropic_api_key: str  # required
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_timeout: int = 30

    # Feature flags
    enable_graphrag: bool = False

    class Config:
        env_file = ".env"
```

**Environment files**:
- `.env.dev` — local development (no secrets needed except Anthropic key)
- `.env.staging` — staging deployment (real services, test data)
- `.env.prod` — production deployment (restricted access, monitoring)

**Secrets management**: For production, inject secrets via Docker secrets or Kubernetes secrets, not `.env` files.

### 3. Docker Containerization

**Goal**: Package service into portable, reproducible container.

**Dockerfile** (production):

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY src/ ./src/
COPY configs/ ./configs/
COPY data/processed/ ./data/processed/  # read-only mount in prod; better: separate volume
EXPOSE 8000
CMD ["uv", "run", "python", "-m", "src.api.main"]
```

**Optimizations**:
- Multi-stage build: builder installs deps, runtime image slim.
- Use `uv sync --frozen` for reproducible installs.
- Copy only necessary files; `data/processed/` likely mounted as volume in prod.

**docker-compose.yml** (local dev):

```yaml
version: '3.8'
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

  neo4j:
    image: neo4j:5
    environment:
      - NEO4J_AUTH=neo4j/secret
    ports:
      - "7687:7687"
    volumes:
      - neo4j_data:/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  vnlaw-qa:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - QDRANT_URL=http://qdrant:6333
      - NEO4J_URI=bolt://neo4j:7687
      - NEO4J_PASSWORD=secret
      - REDIS_URL=redis://redis:6379
    depends_on:
      - qdrant
      - neo4j
      - redis
    volumes:
      - ./data/processed:/app/data/processed:ro  # read-only mount

volumes:
  qdrant_data:
  neo4j_data:
```

### 4. Security & Access Control

**Goal**: Protect API from abuse and unauthorized access.

**Measures**:

- **Rate limiting**: Per IP or per API key. Example: 100 requests/minute.
  - Implementation: `slowapi` middleware with Redis backend for distributed limits.
  
- **API keys** (if internal deployment): Require `X-API-Key` header; validate against allowed keys in config or database.

- **JWT authentication** (if user-facing): Issue tokens for authenticated users; validate on each request.
  - Not needed for pure internal QA service; only if multi-tenant.

- **CORS**: Restrict `Access-Control-Allow-Origin` to known frontends in production.

- **HTTPS**: Terminate TLS at load balancer (e.g., Nginx, AWS ALB). FastAPI itself can run HTTP internally.

- **Input validation**: Pydantic models prevent injection attacks; no raw query logging in prod.

- **Secrets**: Never commit API keys; use environment variables or secret managers.

### 5. Observability

**Goal**: Monitor service health, performance, and errors in production.

**Logging**:
- `structlog` → JSON format → stdout.
- Include `request_id`, `user_id` (if available), `query_id`, timestamps.
- Sanitize: never log raw user legal questions in production (PII risk). Log only query hash or ID.
- Centralize logs to ELK stack, Datadog, or CloudWatch.

**Metrics** (Prometheus):
- Request count, latency (p50/p95/p99), error rate.
- Component latency: retrieval, generation.
- Cache hit rate (if Redis caching enabled).
- LLM token usage.

**Health checks**:
- `/health/live` — liveness: process running.
- `/health/ready` — readiness: can connect to Qdrant, Neo4j, Redis, LLM API.
- Both return 200 if healthy, 503 if degraded.

**Alerting**:
- Latency p95 > threshold.
- Error rate > 1%.
- Qdrant/Neo4j/Redis connection failures.
- LLM API errors or rate limits.

### 6. Caching Strategy (Optional)

**Goal**: Reduce latency and LLM cost for frequent queries.

**Approach**: Redis cache with query hash as key.

**Cache key**: SHA256 of `query + max_chunks + effective_date filter (if any)`.

**Cache value**: Full `QAResponse` (answer, citations, confidence, retrieved_chunks).

**TTL**: 24 hours (legal content changes slowly but not static).

**Cache policy**:
- Check cache before retrieval; on hit, return immediately.
- Invalidate cache when new laws indexed or embeddings updated (flush all or selective).

**Implementation**: Redis client in FastAPI dependency; `@cached` decorator on use-case execute method.

### 7. Deployment Stages

**Development**:
- Docker Compose local stack.
- Hot-reload with `uv run uvicorn src.api.main:app --reload`.
- `.env.dev` configuration.
- Debug logging.

**Staging**:
- Deploy to staging environment (mirrors prod).
- Docker image pushed to registry.
- Kubernetes or ECS/Fargate.
- `.env.staging`.
- Smoke tests and evaluation suite run on deploy.
- Limited traffic, monitoring enabled.

**Production**:
- Immutable Docker image with version tag.
- Kubernetes or cloud managed service (AWS ECS, GCP Cloud Run).
- `.env.prod`.
- Auto-scaling (HPA) based on request rate and latency.
- Secrets from cloud secret manager.
- HTTPS with valid TLS certificate.
- Full observability (logs, metrics, alerts).
- Blue-green or canary deployments with health checks.

## Pipeline Execution Flow

1. **Build phase**:
   - Run tests, lint, type-check.
   - Build Docker image; tag with git commit SHA.
   - Push image to registry.

2. **Deploy phase**:
   - Update Kubernetes deployment/image tag.
   - Wait for rollout; monitor pod health.
   - Run smoke tests against new version.

3. **Runtime phase** (per request):
   - Load balancer → FastAPI pod.
   - Middleware: rate limit, auth, request ID, logging.
   - Route handler receives validated request.
   - Use case executes retrieval/generation pipeline.
   - Infrastructure clients (Qdrant, Neo4j, LLM) called async.
   - Response model serialized → JSON.
   - Structured logs written; metrics incremented.
   - Return 200 with response body.

4. **Error phase**:
   - Exceptions caught at route level or middleware.
   - Log error details (sanitized).
   - Return appropriate HTTP status:
     - 400: bad request (validation error)
     - 429: rate limited
     - 500: internal error
     - 503: service unavailable (infrastructure down)

## Data Models / Output Schema

### API Request Models

```python
from pydantic import BaseModel, Field
from typing import Optional

class QARequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    max_chunks: int = Field(default=10, ge=1, le=50)
    confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    effective_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")  # YYYY-MM-DD

class GraphQARequest(QARequest):
    traversal_depth: int = Field(default=2, ge=1, le=3)
```

### API Response Models

```python
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class Citation(BaseModel):
    chunk_id: str
    citation: str
    source_url: Optional[str] = None

class RetrievedChunk(BaseModel):
    chunk_id: str
    score: float
    payload: dict  # or define specific fields

class QAResponse(BaseModel):
    answer: str
    citations: List[Citation]
    confidence: float
    retrieved_chunks: List[RetrievedChunk]  # include for debugging; may hide in prod
    fallback: bool
    processing_time_ms: float
    query_id: str
    timestamp: datetime
```

### Health Check Response

```json
{
  "status": "healthy|degraded|unhealthy",
  "checks": {
    "qdrant": {"status": "ok", "latency_ms": 5},
    "neo4j": {"status": "ok", "latency_ms": 10},
    "redis": {"status": "skip", "message": "not configured"}
  }
}
```

## CLI Reference

### FastAPI Dev Server

```bash
# Development with hot reload
uv run uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Production (multiple workers)
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker Commands

```bash
# Build image
docker build -t vnlaw-qa:latest .

# Run container (with env file)
docker run -p 8000:8000 --env-file .env.dev vnlaw-qa:latest

# Docker Compose (full stack)
docker-compose up -d
docker-compose logs -f vnlaw-qa
docker-compose down
```

### Kubernetes Deployment (example)

```bash
# Apply deployment and service
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# Check rollout status
kubectl rollout status deployment/vnlaw-qa

# Port forward for testing
kubectl port-forward svc/vnlaw-qa 8000:8000
```

## Testing

**Unit tests**:
- `test_request_validation()`: invalid `query` length or `confidence_threshold` range rejected.
- `test_response_model()`: response conforms to schema; all required fields present.
- `test_health_endpoint()`: returns 200 when dependencies up.
- `test_rate_limit_middleware()`: exceeds limit returns 429.
- `test_cors_headers()`: appropriate `Access-Control-Allow-Origin` set.

**Integration tests**:
- End-to-end API request → response; measure latency.
- Cache behavior: identical query hits cache on second call.
- Error paths: Qdrant down returns 503 with degraded status.
- Authentication: missing/invalid API key returns 401.

**Load testing**:
- Use `locust` or `k6` to simulate concurrent users (e.g., 50 RPS).
- Monitor latency p95, error rate, resource usage.
- Identify bottlenecks (DB connection pool, LLM rate limits).

## Error Handling

- **ValidationError** (bad request): return 400 with error details.
- **Infrastructure failure** (Qdrant/Neo4j/Redis/LLM unreachable): return 503 Service Unavailable; include degraded health check.
- **Rate limit exceeded**: return 429 with `Retry-After` header.
- **Authentication/authorization failure**: return 401 or 403.
- **Unexpected exception**: log sanitized error (no PII); return 500 generic message.

All errors logged with `request_id` for correlation. Responses do not expose internal stack traces in production.

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| 503 on all requests | Qdrant/Neo4j/LLM not running or credentials wrong | Check `/health/ready`; inspect logs for connection errors | Start dependencies; verify env vars; check network connectivity |
| High latency p95 | LLM API slow OR retrieval not using filters | Profile request stages; check Qdrant query time | Enable caching; optimize retrieval filters; use faster LLM model; add timeouts |
| 429 Too Many Requests | Rate limit too strict OR bot traffic | Check rate limit counters in logs | Increase rate limit; add allowlist for trusted IPs |
| Container exits on start | Missing env vars (e.g., ANTHROPIC_API_KEY) OR port already in use | `docker logs` shows config error | Provide required env vars; free port 8000 |
| CORS errors in browser | `cors_origins` not including frontend origin | Browser console shows CORS block | Add frontend URL to `cors_origins` |
| Memory leak / OOM | Large response objects cached OR unbounded retrieved_chunks stored | Monitor container memory; profile heap | Limit `max_chunks`; cap cache size; avoid storing large texts in memory |
| HTTPS termination failing | Load balancer not configured with TLS cert | Browser shows connection not secure | Configure ALB/NGINX with valid TLS certificate; redirect HTTP → HTTPS |
| Pods crash looping | Unhandled exception on startup | `kubectl logs` shows stack trace | Fix configuration; add retry/backoff for infrastructure connections |

## Best Practices

- **Thin routes** — keep business logic in use-case classes, not in route handlers.
- **Async all I/O** — Qdrant, Neo4j, Redis, LLM calls must use async clients.
- **Sanitize logs** — never log raw user queries in prod; use query hash or ID.
- **Graceful degradation** — if caching disabled, still serve; if Redis down, skip cache but continue.
- **Timeouts everywhere** — set timeouts on all external calls; fail fast.
- **Health checks** — separate liveness (process up) and readiness (dependencies reachable).
- **Immutable images** — same image tag deployed to all environments; config via env vars only.
- **Monitor SLOs** — track latency p95 < 2s, error rate < 0.1%.
- **Canary deployments** — route small percentage of traffic to new version; monitor errors/latency before full rollout.
- **Secure defaults** — CORS restricted, rate limiting enabled, authentication required in prod.

## Changelog

### Version 0.1 (2026-05-21)

- Created initial API & deployment documentation.
- Defined FastAPI routes, middleware, and configuration via `pydantic-settings`.
- Specified Dockerfile multi-stage build and docker-compose stack.
- Documented security (rate limiting, API keys, CORS, HTTPS) and observability (logging, metrics, health checks).
- Provided caching strategy (Redis) and deployment stages (dev/staging/prod).
- Added request/response Pydantic models and error handling policies.
- Included troubleshooting table for common deployment and runtime issues.

## Related Documentation

| Document | Status | Description |
|----------|--------|-------------|
| `docs/project_phase_journal.md` | Existing | Project phase journal and pipeline notes |
| `docs/project_setup.md` | Implemented | Environment setup and coding standards |
| `docs/corpus_registry.md` | Implemented | Corpus registry schema and design |
| `docs/raw_corpus_audit.md` | Designed | Raw artifact audit procedure |
| `docs/cleaning_normalization.md` | Existing | HTML-to-text and Unicode normalization |
| `docs/legal_parsing.md` | Existing | Legal hierarchy parsing algorithm |
| `docs/parent_child_chunking.md` | Existing | Parent-child chunking design |
| `docs/processed_jsonl.md` | Existing | JSONL export schema and validation |
| `docs/embedding_indexing.md` | Future extension | Embedding model and Qdrant indexing |
| `docs/naive_rag.md` | Future extension | Baseline RAG implementation |
| `docs/advanced_rag.md` | Future extension | Hybrid retrieval, reranking, time-aware filtering |
| `docs/graphrag_agents.md` | Future extension | Legal graph schema, traversal, agent orchestration |
| `docs/evaluation.md` | Future extension | Evaluation metrics, golden QA dataset, CI gates |
| `docs/mlops_maintenance.md` | Future extension | Corpus updates, index refresh, monitoring, runbooks |
