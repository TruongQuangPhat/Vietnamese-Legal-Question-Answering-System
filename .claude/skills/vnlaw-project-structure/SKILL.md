---
name: vnlaw-project-structure
description: Use when creating, reorganizing, reviewing, or enforcing the VnLaw-QA repository layout, module responsibilities, and Claude Code project boundaries.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# Project Structure Skill

Use this skill to enforce repository organization and module boundaries.

## Canonical Layout

```text
vnlaw_qa/
├── .github/workflows/
├── .claude/skills/
├── configs/
│   ├── models.yml
│   ├── retrieval.yml
│   ├── chunking.yml
│   ├── prompts/
│   └── laws/corpus_registry.yml
├── data/
│   ├── raw/
│   ├── processed/
│   └── eval/
├── deploy/
├── scripts/
├── src/
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
├── notebooks/
├── docs/
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

## Module Responsibilities

### `src/core/`

```text
settings
custom exceptions
structured logging
shared domain types
```

### `src/ingestion/`

```text
crawler
HTML/PDF/DOC parser
normalization
legal hierarchy parser
parent-child chunking
embedding orchestration
ingestion pipeline
```

### `src/retrieval/`

```text
Qdrant vector store
dense/sparse retrieval
RRF fusion
Neo4j graph store
reranker
time-aware filtering
confidence scoring
```

### `src/generation/`

```text
LLM client wrappers
prompt rendering
context packing
answer formatting
citation validation
fallback behavior
```

### `src/agents/`

```text
intent router
vector explorer
graph explorer
orchestrator
optional approved latest-law checker
```

### `src/api/`

```text
FastAPI app
schemas
dependencies
routes
```

## Config Rules

Use `configs/` for non-secret settings:

```text
model names
retrieval parameters
chunking policy
prompt templates
corpus registry
```

Use `.env` for secrets, with `.env.example` containing placeholders only.

## Test Layout

Tests should mirror source modules:

```text
tests/unit/ingestion/
tests/unit/retrieval/
tests/unit/generation/
tests/unit/api/
tests/integration/
tests/evaluation/
```

## Claude Project Boundary

Claude should usually run from repository root.

Do not run Claude from `~/` or a parent folder that includes unrelated projects.

## Do Not

- Do not put business logic in FastAPI routes.
- Do not hardcode retrieval parameters in source code.
- Do not put secrets in `configs/`.
- Do not commit `.env`.
- Do not commit large raw datasets unless explicitly approved.
- Do not create duplicate modules with overlapping responsibility.
- Do not mix ingestion, retrieval, generation, and API logic in one file.