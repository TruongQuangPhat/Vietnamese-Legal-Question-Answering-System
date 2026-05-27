---
name: vnlaw-oop-code-quality
description: Use for Python code quality, OOP architecture, type hints, dependency injection, interfaces, service boundaries, error handling, and maintainable module design.
---

# OOP and Code Quality Skill

Use this skill before implementing or reviewing production code.

## Mandatory Python Standards

- Use Python 3.11+.
- Add `from __future__ import annotations` to new Python files.
- Use full type hints for public functions, methods, and attributes where practical.
- Use Pydantic V2 for API/data boundaries and configuration.
- Use `async def` / `await` for I/O with Qdrant, Neo4j, Redis, LLM providers, HTTP clients, and crawlers.
- Use `ruff`, `mypy`, and `pytest` before commit.
- Maximum line length: 100 characters unless project config says otherwise.

## OOP Boundaries

Prefer interfaces through `typing.Protocol` or abstract base classes.

Recommended interfaces:

```text
BaseCrawler
BaseLegalParser
BaseChunker
BaseEmbedder
BaseVectorStore
BaseGraphStore
BaseRetriever
BaseReranker
BaseLLMClient
BaseAgent
```

Example:

```python
from __future__ import annotations

from typing import Protocol

class BaseLegalParser(Protocol):
    """Parses normalized legal text into structured legal nodes."""

    def parse(self, text: str, law_id: str) -> list[LegalNode]:
        """Parse legal text into hierarchy-preserving nodes."""
        ...
```

## Dependency Injection

Prefer this:

```python
class LegalSearchService:
    """Coordinates retrieval, reranking, and context packing for legal QA."""

    def __init__(
        self,
        vector_store: BaseVectorStore,
        reranker: BaseReranker,
        settings: RetrievalSettings,
    ) -> None:
        self._vector_store = vector_store
        self._reranker = reranker
        self._settings = settings
```

Avoid this:

```python
class LegalSearchService:
    def __init__(self) -> None:
        self.qdrant = AsyncQdrantClient("hardcoded-url")
```

## Class Design Rules

Each class must have one responsibility:

```text
crawler       → fetches source artifacts
parser        → parses normalized text
chunker       → creates hierarchy-preserving chunks
embedder      → embeds text
vector store  → stores/searches vectors
graph store   → manages graph relations
reranker      → reranks candidates
generator     → generates/validates final answer
service       → coordinates use case logic
route         → handles HTTP only
```

Avoid god classes that mix unrelated responsibilities.

## Error Handling

Use specific exceptions and structured logs.

```python
try:
    results = await self._client.query_points(...)
except QdrantException as exc:
    self._logger.error("qdrant_query_failed", error=str(exc), collection=collection_name)
    raise VectorSearchError(f"Qdrant query failed: {exc}") from exc
```

Never use:

```python
except Exception:
    pass
```

## Raw Dict Policy

Avoid passing raw dictionaries across module boundaries.

Prefer typed models for:

```text
crawl targets
legal chunks
retrieval candidates
evidence packets
citations
LLM responses
API requests/responses
evaluation records
```

## Review Checklist

- [ ] Single responsibility is respected.
- [ ] Public API is typed.
- [ ] Dependencies are injected.
- [ ] No hardcoded clients or credentials.
- [ ] Async I/O is used for external systems.
- [ ] Pydantic models are used for boundaries.
- [ ] No raw dicts cross major boundaries without justification.
- [ ] Specific exceptions and structured logs are used.
- [ ] Google-style docstrings exist for public classes/functions.
- [ ] Tests cover normal, edge, and failure cases.

## Do Not

- Do not create god classes.
- Do not hardcode URLs, API keys, or DB clients in services.
- Do not swallow exceptions.
- Do not put business logic in FastAPI routes.
- Do not mix ingestion, retrieval, generation, and evaluation in one module.