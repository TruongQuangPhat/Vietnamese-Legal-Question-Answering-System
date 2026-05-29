# Project Setup & Development Principles

## Overview

This document describes the development environment, coding standards, and architectural principles for the VnLaw-QA system. Proper setup ensures consistent tooling, dependency management, and quality enforcement across the Vietnamese Legal QA pipeline.

VnLaw-QA requires strict discipline because:
- Legal accuracy is non-negotiable; every component must be testable and verifiable.
- The pipeline involves multiple stages (crawling, parsing, chunking, retrieval, generation) that depend on stable interfaces.
- Security and PII handling are critical when processing legal documents.
- Async I/O and type safety prevent runtime errors in data-intensive workflows.

## Quick Start

```bash
# Clone and setup environment
uv sync

# Install pre-commit hooks (if configured)
uv run pre-commit install

# Run quality checks
uv run ruff check src tests
uv run ruff format src tests
uv run mypy src
uv run pytest tests/unit -v

# Run the crawler CLI
uv run python scripts/crawl_raw_corpus.py --help
```

**Important**: All development should use the `uv` package manager and the project's `pyproject.toml` configuration.

## Architecture

```
┌─────────────────────────────┐
│  Project Repository         │
│  (CLAUDE.md, pyproject.toml)│
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  Environment Setup          │
│  (uv sync, .env loading)    │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  Configuration              │
│  (pydantic-settings)        │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  Development Commands       │
│  (pytest, ruff, mypy)       │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  Quality Gates              │
│  (type hints, docstrings)   │
└─────────────────────────────┘
```

## Components

### 1. Environment & Dependency Management

**Tool**: `uv` (fast Python package manager and resolver)

- `pyproject.toml` defines all dependencies (core, dev, test)
- `uv sync` creates isolated virtual environment with exact versions
- Lock file ensures reproducibility across machines

**Key dependencies**:
- `pydantic` V2 for configuration and data validation
- `pydantic-settings` for environment variable loading
- `httpx` for async HTTP crawling
- `qdrant-client` for vector storage
- `neo4j` for graph storage
- `anthropic` for Claude API
- `structlog` for structured logging

### 2. Configuration System

**Pattern**: Pydantic V2 settings with environment variable override.

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    qdrant_url: str
    qdrant_api_key: str | None
    neo4j_uri: str
    neo4j_password: str
    anthropic_api_key: str

    class Config:
        env_file = ".env"
```

**.env.example** provides template; **.env** is local-only (gitignored). Never commit secrets.

### 3. Code Quality Standards

**Mandatory** for all production code:

- Python 3.11+
- `from __future__ import annotations` at top of every module
- Complete type hints for public functions, methods, and class attributes
- Google-style docstrings for all public classes, functions, methods
- Async I/O (`async def` / `await`) for network operations (crawling, Qdrant, Neo4j, LLM)
- Pydantic models for data boundaries (config, requests, responses, chunk schemas)
- Custom exceptions with structured logging via `structlog`
- No bare `except Exception:`; catch specific exceptions only

**Tools**:
- `ruff` for linting and formatting
- `mypy` for static type checking
- `pytest` for unit/integration tests

### 4. Project Structure

Canonical layout:

```
vnlaw_qa/
├── .github/workflows/      # CI/CD
├── .claude/                # Claude Code settings
│   ├── settings.example.json
│   └── skills/
├── configs/                 # YAML configurations
│   ├── laws/
│   │   └── corpus_registry.yml
│   ├── models.yml
│   ├── retrieval.yml
│   ├── chunking.yml
│   └── prompts/
├── data/                   # Data directories (gitignored)
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   └── eval/
├── deploy/
│   └── docker/
├── docs/                   # Documentation
├── scripts/                # One-off scripts
├── src/                    # Production code
│   ├── core/
│   ├── ingestion/
│   ├── retrieval/
│   ├── generation/
│   ├── agents/
│   └── api/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── evaluation/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

### 5. Security Principles

- **Secrets**: Never hardcode. Use `.env` with `pydantic-settings`. Add `.env` to `.gitignore`.
- **Logging**: Do not log raw user queries (PII risk). Use structured JSON logs with `request_id` when available.
- **API exposure**: Never expose Qdrant, Neo4j, or Redis directly to the internet in production. Use network policies.
- **Input validation**: Validate all external inputs (registry entries, HTTP responses) with Pydantic models.
- **Cypher queries**: Sanitize inputs to avoid Neo4j injection; use parameterized queries.

## Pipeline Execution Flow

1. **Environment bootstrap**: `uv sync` installs dependencies from lock file
2. **Configuration loading**: Pydantic settings read from `.env` and environment
3. **Development workflow**: Developer runs commands via `uv run <tool>`
4. **Quality enforcement**: Pre-commit or CI runs ruff, mypy, pytest
5. **Documentation**: CLAUDE.md and this docs/ directory serve as living references

## Data Models / Output Schema

### Configuration Models

All configuration files (`configs/*.yml`) are validated against Pydantic models. Example for corpus registry:

```python
from pydantic import BaseModel, Field
from typing import Literal

class CorpusEntry(BaseModel):
    law_id: str
    name: str
    tier: int = Field(ge=0, le=2)
    group: str
    domain_tags: list[str] = []
    status: Literal["active", "planned", "inactive", "amended", "replaced"]
    source_domain: str
    source_type: Literal["html", "pdf", "doc", "docx", "mixed"]
    url: str | None = None
    effective_date: str | None = None  # YYYY-MM-DD
    expiry_date: str | None = None
    crawl_status: Literal["pending", "crawled", "failed", "manual_review"] = "pending"
    priority: Literal["critical", "high", "medium", "low"] = "medium"
```

### Project Metadata Files

- `CLAUDE.md`: Project-wide instructions for Claude Code
- `PROJECT_CONTEXT.md`: Current status, completed phases, next tasks (to be created)
- `.claude/settings.json`: Harness configuration (permissions, hooks)

## CLI Reference

### Main entry points

```bash
# Show help for ingestion CLI
uv run python scripts/crawl_raw_corpus.py --help

# Expected commands (to be implemented in later phases):
# - Crawler: uv run python scripts/crawl_raw_corpus.py --registry ... --output ...
# - Parser: uv run python -m src.processing.parser ...
# - Chunker: uv run python -m src.processing.chunker ...
# - Evaluator: uv run python -m src.evaluation.run ...
```

## Testing

**Unit tests**: `tests/unit/` — test pure functions, Pydantic models, utilities.
**Integration tests**: `tests/integration/` — test component interactions (crawler → storage, parser → chunker).
**Evaluation tests**: `tests/evaluation/` — golden QA, retrieval metrics (RAGAS).

Run all:
```bash
uv run pytest tests/ -v
```

Run specific:
```bash
uv run pytest tests/unit/test_models.py -v
```

## Error Handling

- **Configuration errors**: Raise `ConfigurationError` on missing required env vars or invalid YAML.
- **Crawler errors**: Retry with exponential backoff; log structured error with `law_id`, `url`, `retry_count`.
- **Validation errors**: Pydantic raises `ValidationError`; catch at boundary and log field errors.
- **File system errors**: Use `pathlib` and handle `FileNotFoundError`, `PermissionError` explicitly.

All errors should be logged with `structlog`:
```python
import structlog
logger = structlog.get_logger()
logger.error("crawl_failed", law_id=law_id, url=url, exc_info=True)
```

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| `uv sync` hangs or fails | Network issues, conflicting dependencies | Check uv version, network connectivity | Update uv, clear cache, check pyproject.toml syntax |
| `mypy` reports errors in new code | Missing type hints, wrong return type | Run `uv run mypy src` | Add complete type hints, fix return types |
| `ruff` formatting fails | Inconsistent formatting | Run `uv run ruff format src tests` | Auto-format, then re-run |
| Import errors after adding new module | Python path issues | Verify module location matches package structure | Check `src/` is a package (`__init__.py`), use absolute imports |
| Environment variables not loading | `.env` missing or misnamed | Verify `.env` exists in project root | Copy `.env.example` to `.env` and fill values |
| Tests fail with import errors | PYTHONPATH not set correctly | Run tests via `uv run pytest` (not raw `pytest`) | Always use `uv run` to execute tools |

## Best Practices

- **Commit small, focused changes** — one phase per feature branch.
- **Write docstrings** for all public functions and classes (Google style).
- **Add type hints** before implementation; let `mypy` guide you.
- **Never commit secrets** — verify `.env` is gitignored.
- **Keep logging structured** — use key-value pairs, not string concatenation.
- **Prefer dependency injection** over global singletons.
- **Validate early** — use Pydantic models at system boundaries (HTTP, file I/O).
- **Async all I/O** — crawling, database access, LLM calls should use `async/await`.
- **Respect legal hierarchy** — never split legal clauses arbitrarily.
- **Traceability** — always preserve `source_url`, `law_id`, and `citation` from raw to final answer.

## Changelog

### Version 0.1 (2026-05-21)

- Created initial project setup documentation.
- Documented uv environment, pyproject.toml, and quality tools.
- Defined coding standards (type hints, docstrings, async I/O).
- Described security principles (secrets, logging, validation).
- Provided troubleshooting table for common setup issues.

## Related Documentation

| Document | Status | Description |
|----------|--------|-------------|
| `docs/project_phase_journal.md` | Existing | Project phase journal and pipeline notes |
| `docs/corpus_registry.md` | Existing | Corpus registry schema and design |
| `docs/raw_corpus_audit.md` | Designed | Raw artifact audit procedure |
| `docs/cleaning_normalization.md` | Existing | HTML-to-text and Unicode normalization |
| `docs/legal_parsing.md` | Existing | Legal hierarchy parsing algorithm |
| `docs/parent_child_chunking.md` | Existing | Parent-child chunking design |
| `docs/processed_jsonl.md` | Existing | JSONL export schema and validation |
