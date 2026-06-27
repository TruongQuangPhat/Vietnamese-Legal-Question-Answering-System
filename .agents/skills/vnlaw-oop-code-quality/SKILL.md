---
name: vnlaw-oop-code-quality
description: Use for Python code quality, OOP architecture, type hints, dependency injection, interfaces, service boundaries, error handling, testing boundaries, and maintainable module design.
---

# OOP and Code Quality Skill

Use this skill before implementing or reviewing production code.

## Mandatory Python Standards

* Use Python 3.11+.
* Add `from __future__ import annotations` to new Python files.
* Use full type hints for public functions, methods, and attributes where practical.
* Use Pydantic V2 for API/data boundaries and configuration.
* Use `async def` / `await` for I/O with Qdrant, Neo4j, Redis, LLM providers, HTTP clients, and crawlers when those systems are explicitly scoped.
* Use `ruff`, `pytest`, and `uv lock --check` before commit.
* Use `mypy` only if it is configured or explicitly scoped for the task.
* Maximum line length: 100 characters unless project config says otherwise.

## Current Project Boundaries

The current system includes corpus processing, legal parsing, parent-child chunking, dense indexing, retrieval, strict generation, citation validation, fallback control, and evaluation workflows.

Reranking was evaluated but not adopted. GraphRAG, Neo4j, API/backend, and multi-agent orchestration are future or separately scoped unless the user explicitly requests them.

Do not run real Qdrant, real LLM/API, real embedding inference, real reranking, or full benchmark pipelines unless explicitly scoped.

Protected paths include:

```text id="fx42ur"
data/raw/**
data/interim/**
data/reports/**
data/processed/legal_chunks.jsonl
data/eval/**
artifacts/reports/evaluation/**
```

## OOP Boundaries

Prefer interfaces through `typing.Protocol` or abstract base classes.

Recommended interfaces may include:

```text id="e7nldp"
BaseCrawler
BaseLegalParser
BaseChunker
BaseEmbedder
BaseVectorStore
BaseRetriever
BaseLLMClient
BaseEvaluator
```

Optional or future-scoped interfaces:

```text id="s755uj"
BaseReranker
BaseGraphStore
BaseAgent
```

Example:

```python id="v5tsml"
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

```python id="bqvuh5"
class LegalSearchService:
    """Coordinates retrieval and evidence preparation for legal QA."""

    def __init__(
        self,
        retriever: BaseRetriever,
        settings: RetrievalSettings,
    ) -> None:
        self._retriever = retriever
        self._settings = settings
```

Avoid this:

```python id="bwyy0f"
class LegalSearchService:
    def __init__(self) -> None:
        self.qdrant = AsyncQdrantClient("hardcoded-url")
```

If reranking is explicitly scoped for a controlled ablation, inject the reranker through a typed interface instead of hardcoding it.

## Class Design Rules

Each class must have one responsibility:

```text id="v1v6r4"
crawler       → fetches source artifacts
parser        → parses normalized text
chunker       → creates hierarchy-preserving chunks
embedder      → embeds text
vector store  → stores/searches dense vectors
retriever     → retrieves/ranks candidates
selector      → selects citable evidence
generator     → generates answer drafts from selected evidence
citation guard → validates citations against selected evidence
fallback policy → decides safe fallback behavior
evaluator     → computes metrics and writes reports
service       → coordinates use case logic
route         → handles HTTP only, if API is explicitly scoped
```

Future or separately scoped components:

```text id="lg4fgc"
graph store   → manages graph relations
reranker      → reranks candidates in controlled ablations
agent         → orchestrates multi-step retrieval or reasoning workflows
```

Avoid god classes that mix unrelated responsibilities.

## Error Handling

Use specific exceptions and structured logs.

```python id="m4pmqn"
try:
    results = await self._client.query_points(...)
except QdrantException as exc:
    self._logger.error("qdrant_query_failed", error=str(exc), collection=collection_name)
    raise VectorSearchError(f"Qdrant query failed: {exc}") from exc
```

Never use:

```python id="1c1d9g"
except Exception:
    pass
```

Do not log secrets, API keys, full prompts with sensitive user input, or raw provider credentials.

## Raw Dict Policy

Avoid passing raw dictionaries across module boundaries.

Prefer typed models for:

```text id="ncb47k"
crawl targets
legal nodes
legal chunks
retrieval candidates
evidence packets
citations
LLM responses
API requests/responses
evaluation records
artifact manifests
```

Small local dictionaries are acceptable inside a function when they do not cross a module/service boundary.

## Testing and Validation

Use safe validation by default:

```bash id="1dlf7k"
env UV_CACHE_DIR=/tmp/vnlaw-uv-cache find src scripts tests -name '*.py' -exec uv run python -m py_compile {} +

uv run pytest tests/unit -q --durations=30
uv run pytest tests/integration -q --durations=30

uv run ruff check src scripts tests
uv run ruff format --check src scripts tests

uv lock --check
git diff --check
```

Use mocks, fakes, tiny fixtures, and `tmp_path` for tests involving Qdrant, LLM providers, embeddings, rerankers, or evaluation artifacts.

## Review Checklist

* [ ] Single responsibility is respected.
* [ ] Public API is typed.
* [ ] Dependencies are injected.
* [ ] No hardcoded clients or credentials.
* [ ] Async I/O is used for external systems when scoped.
* [ ] Pydantic models are used for boundaries.
* [ ] No raw dicts cross major boundaries without justification.
* [ ] Specific exceptions and structured logs are used.
* [ ] Google-style docstrings exist for public classes/functions where project style requires it.
* [ ] Tests cover normal, edge, and failure cases.
* [ ] Real services are not called unless explicitly scoped.
* [ ] Protected paths are not modified unless explicitly scoped.

## Do Not

* Do not create god classes.
* Do not hardcode URLs, API keys, or DB clients in services.
* Do not swallow exceptions.
* Do not put business logic in FastAPI routes.
* Do not mix ingestion, retrieval, generation, and evaluation in one module.
* Do not treat reranking, GraphRAG, API/backend, or agents as current adopted behavior unless explicitly scoped.
* Do not run real Qdrant, LLM/API, embedding, reranking, or full benchmark workflows unless explicitly requested.
