---
name: vnlaw-project-structure
description: Use when creating, reorganizing, reviewing, or enforcing the VnLaw-QA repository layout, module responsibilities, protected paths, and Codex project boundaries.
---

# Project Structure Skill

Use this skill to enforce repository organization and module boundaries.

## Current Implemented Layout

```text
VnLaw-QA/
├── .agents/skills/
├── .codex/context/
├── configs/
│   ├── laws/corpus_registry.yml
│   ├── sources/
│   ├── ingestion/
│   ├── processing/
│   ├── indexing/
│   ├── retrieval/
│   ├── generation/
│   └── evaluation/
├── data/
│   ├── raw/          # protected crawl artifacts
│   ├── interim/      # protected normalized artifacts and hierarchy outputs
│   ├── processed/    # protected validated legal_chunks.jsonl
│   ├── indexes/      # local/runtime index-related artifacts when used
│   └── eval/         # protected benchmark/qrels/evidence data
├── artifacts/
│   ├── reports/
│   │   ├── crawling/
│   │   ├── audit/
│   │   ├── cleaning/
│   │   ├── parsing/
│   │   ├── chunking/
│   │   ├── indexing/
│   │   ├── retrieval/
│   │   ├── generation/
│   │   └── evaluation/
│   ├── traces/
│   ├── runs/
│   ├── metrics/
│   └── logs/
├── scripts/
├── src/
│   ├── core/
│   ├── ingestion/
│   ├── processing/
│   ├── indexing/
│   ├── retrieval/
│   ├── generation/
│   ├── services/
│   └── evaluation/
├── tests/
│   ├── unit/
│   │   ├── ingestion/
│   │   ├── processing/
│   │   ├── indexing/
│   │   ├── retrieval/
│   │   ├── services/
│   │   └── evaluation/
│   ├── integration/
│   │   ├── corpus/
│   │   ├── retrieval/
│   │   └── evaluation/
│   └── fixtures/
├── docs/
├── AGENTS.md
├── PROJECT_CONTEXT.md
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

Some future or separately scoped directories may exist as scaffolding. Add implementation logic to them only when the user explicitly scopes that area.

## Current System State

The repository currently includes implemented workflows for:

```text
registry-driven ingestion
raw corpus audit
cleaning and normalization
legal hierarchy parsing
parent-child chunking
processed JSONL validation
BGE-M3 dense indexing
BM25 sparse retrieval
RRF fusion
coverage-aware quota retrieval
Naive RAG baseline
strict generation
citation ID guard
answerability fallback guard
retrieval/generation evaluation
workflow-level integration tests
```

Current key artifacts and contracts:

```text
data/processed/legal_chunks.jsonl
Qdrant collection: vnlaw_chunks_bgem3_v1_full
dense vector name: dense
dense dimension: 1024
benchmark version: v0.1.0
```

Reranking was evaluated but not adopted. GraphRAG, Neo4j, API/backend, time-aware filtering, monitoring, security hardening, Docker/deployment, and production MLOps are future or separately scoped unless explicitly requested.

## Target Future Layout

Use this as a compact roadmap for future expansion. Do not create empty enterprise folders unless they remove real operational complexity.

```text
VnLaw-QA/
├── configs/
│   ├── laws/
│   ├── sources/
│   ├── ingestion/
│   ├── processing/
│   ├── indexing/
│   ├── retrieval/
│   ├── generation/
│   └── evaluation/
├── data/
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   ├── indexes/
│   └── eval/
├── artifacts/
│   ├── reports/
│   ├── traces/
│   ├── runs/
│   ├── metrics/
│   └── logs/
├── src/
│   ├── core/
│   ├── ingestion/
│   ├── processing/
│   ├── indexing/
│   ├── retrieval/
│   ├── generation/
│   ├── services/
│   ├── evaluation/
│   ├── api/          # future/separately scoped
│   ├── monitoring/   # future/separately scoped
│   └── security/     # future/separately scoped
├── scripts/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   └── fixtures/
├── docs/
├── docker/           # future/separately scoped
├── deployment/       # future/separately scoped
└── .github/workflows/
```

Prefer the compact current layout over a deeply nested enterprise layout.

## Module Responsibilities

### `src/core/`

```text
settings
custom exceptions
structured logging
shared domain types
shared utilities
```

### `src/ingestion/`

```text
crawler
raw artifact audit
registry loading
storage helpers
HTML cleaning and normalization
cleaning diagnostics
```

Do not mix crawler behavior with parsing, chunking, embedding, retrieval, or generation logic.

### `src/processing/`

```text
legal hierarchy parser
parent-child chunking domain logic
processed JSONL validation logic
legal metadata schemas
```

Legal parsing placement:

```text
domain logic: src/processing/
orchestration: src/services/
CLI: scripts/corpus/
tests: tests/unit/processing/ and tests/unit/services/
output: data/interim/{LAW_ID}/hierarchy.json
report: artifacts/reports/parsing/
```

Parent-child chunking placement:

```text
domain logic: src/processing/
orchestration: src/services/
CLI: scripts/corpus/
tests: tests/unit/processing/ and tests/unit/services/
integration tests: tests/integration/corpus/
output: data/processed/legal_chunks.jsonl
report: artifacts/reports/chunking/
```

### `src/indexing/`

```text
embedding model wrappers
embedding batch logic
Qdrant dense indexing
index payload validation
indexing reports
```

Current indexing contract:

```text
embedding model: BAAI/bge-m3
Qdrant collection: vnlaw_chunks_bgem3_v1_full
vector name: dense
dimension: 1024
distance: cosine
```

Sparse BM25 retrieval is handled separately from Qdrant dense indexing unless a future task explicitly scopes sparse-vector indexing.

### `src/retrieval/`

```text
dense retrieval
BM25 sparse retrieval
RRF fusion
coverage-aware quota retrieval
evidence selection
RAG pipeline coordination
citation guard integration
fallback behavior around retrieval/evidence
```

Current retrieval placement:

```text
domain logic: src/retrieval/
reports: artifacts/reports/retrieval/
traces: artifacts/traces/retrieval/
metrics: artifacts/metrics/retrieval/
unit tests: tests/unit/retrieval/
integration tests: tests/integration/retrieval/
```

Future or separately scoped retrieval components:

```text
cross-encoder reranking
Neo4j graph store
GraphRAG traversal
time-aware filtering
agentic routing/orchestration
```

Do not treat these future components as adopted current behavior unless explicitly implemented and evaluated.

### `src/generation/`

```text
LLM client wrappers
prompt rendering
context/evidence packing
answer formatting
citation validation
fallback behavior
```

Use this area only if the repository currently has generation modules. If generation logic currently lives under `src/retrieval/` or `src/evaluation/`, preserve the existing structure unless a refactor is explicitly scoped.

Generation/RAG placement:

```text
domain logic: src/generation/ or current implemented module
reports: artifacts/reports/generation/
traces: artifacts/traces/generation/
metrics: artifacts/metrics/generation/
tests: tests/unit/retrieval/ and tests/unit/evaluation/ where current code lives
```

### `src/services/`

```text
pipeline orchestration
batch execution
report building
cross-module coordination
service-level workflows
```

Services coordinate use cases. They should not become god classes that mix unrelated domain logic.

### `src/evaluation/`

```text
benchmark loading
split handling
retrieval evaluation
strict generation evaluation
error analysis
evidence selection diagnostics
artifact contract helpers
metrics aggregation
```

Evaluation placement:

```text
domain logic: src/evaluation/
datasets: data/eval/
reports: artifacts/reports/evaluation/
metrics: artifacts/metrics/evaluation/
runs: artifacts/runs/evaluations/
unit tests: tests/unit/evaluation/
integration tests: tests/integration/evaluation/
```

### `src/api/`

```text
future/separately scoped
FastAPI app
schemas
dependencies
routes
```

Do not create API files unless the user explicitly scopes API/backend work.

## Config Rules

Use `configs/` for non-secret settings:

```text
corpus registry
processing validation config
indexing config
retrieval parameters
model names
evaluation config
prompt templates if implemented
```

Use `.env` for secrets, with `.env.example` containing placeholders only.

Do not put API keys, real credentials, or private tokens in `configs/`.

## Test Layout

Tests should mirror source modules and workflow boundaries:

```text
tests/unit/ingestion/
tests/unit/processing/
tests/unit/indexing/
tests/unit/retrieval/
tests/unit/services/
tests/unit/evaluation/

tests/integration/corpus/
tests/integration/retrieval/
tests/integration/evaluation/

tests/fixtures/
```

Future or separately scoped:

```text
tests/unit/api/
tests/integration/api/
tests/regression/
```

Routine tests should use mocks, fakes, tiny fixtures, and `tmp_path`. Do not require real Qdrant, real LLM, real embedding inference, real reranking, or full benchmark runs unless explicitly scoped.

## Protected Paths

Do not modify these unless the user explicitly scopes the operation:

```text
data/raw/**
data/interim/**
data/reports/**
data/processed/legal_chunks.jsonl
data/eval/**
artifacts/reports/evaluation/**
```

Do not re-embed, re-index, upsert, recreate, delete Qdrant collections, or overwrite official evaluation artifacts unless explicitly requested.

## Codex Project Boundary

Codex should usually run from repository root.

Do not run Codex from `~/` or a parent folder that includes unrelated projects.

Before making structural changes, run:

```bash
git status --short
find src -maxdepth 2 -type d | sort
find tests -maxdepth 3 -type d | sort
find docs -maxdepth 1 -type f | sort
```

## Do Not

* Do not put business logic in FastAPI routes.
* Do not hardcode retrieval parameters in source code.
* Do not put secrets in `configs/`.
* Do not commit `.env`.
* Do not commit Qdrant storage, model caches, or large generated runtime state.
* Do not create duplicate modules with overlapping responsibility.
* Do not mix ingestion, retrieval, generation, and API logic in one file.
* Do not treat API, GraphRAG, reranking, time-aware filtering, monitoring, or production deployment as current adopted behavior unless explicitly scoped.
