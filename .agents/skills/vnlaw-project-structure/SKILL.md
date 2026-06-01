---
name: vnlaw-project-structure
description: Use when creating, reorganizing, reviewing, or enforcing the VnLaw-QA repository layout, module responsibilities, and Codex project boundaries.
---

# Project Structure Skill

Use this skill to enforce repository organization and module boundaries.

## Current Implemented Layout

```text
VnLaw-QA/
├── .agents/skills/
├── .codex/context/
├── .claude/skills/
├── configs/
│   └── laws/corpus_registry.yml
├── data/
│   ├── raw/          # immutable crawl artifacts
│   ├── interim/      # normalized artifacts and future hierarchy/chunks
│   ├── reports/      # audit and quality reports
│   └── processed/    # future validated JSONL chunks
├── scripts/
├── src/
│   ├── core/
│   ├── ingestion/
│   └── services/
├── tests/
│   └── unit/ingestion/
├── docs/
├── AGENTS.md
├── CLAUDE.md
├── PROJECT_CONTEXT.md
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

Future phases may add `src/retrieval/`, `src/generation/`, `src/agents/`,
`src/api/`, `tests/integration/`, `tests/evaluation/`, `deploy/`, and
additional config files under `configs/`. Add and document them only when their
phase starts.

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
raw artifact audit
registry loading
storage helpers
HTML cleaning and normalization
cleaning diagnostics
future legal hierarchy parser
future parent-child chunking domain logic
```

### `src/services/`

```text
pipeline orchestration
batch execution
report building
cross-module coordination
```

### `src/retrieval/`

```text
future phase only
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
future phase only
LLM client wrappers
prompt rendering
context packing
answer formatting
citation validation
fallback behavior
```

### `src/agents/`

```text
future phase only
intent router
vector explorer
graph explorer
orchestrator
optional approved latest-law checker
```

### `src/api/`

```text
future phase only
FastAPI app
schemas
dependencies
routes
```

## Config Rules

Use `configs/` for non-secret settings:

```text
current:
corpus registry

future:
model names
retrieval parameters
chunking policy
prompt templates
```

Use `.env` for secrets, with `.env.example` containing placeholders only.

## Test Layout

Tests should mirror source modules:

```text
tests/unit/ingestion/
future:
tests/unit/retrieval/
tests/unit/generation/
tests/unit/api/
tests/integration/
tests/evaluation/
```

## Codex Project Boundary

Codex should usually run from repository root.

Do not run Codex from `~/` or a parent folder that includes unrelated projects.

## Do Not

- Do not put business logic in FastAPI routes.
- Do not hardcode retrieval parameters in source code.
- Do not put secrets in `configs/`.
- Do not commit `.env`.
- Do not commit large raw datasets unless explicitly approved.
- Do not create duplicate modules with overlapping responsibility.
- Do not mix ingestion, retrieval, generation, and API logic in one file.
