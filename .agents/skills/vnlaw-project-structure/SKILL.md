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
│   ├── laws/corpus_registry.yml
│   ├── sources/.gitkeep
│   ├── ingestion/.gitkeep
│   ├── processing/.gitkeep
│   ├── indexing/.gitkeep
│   ├── retrieval/.gitkeep
│   ├── generation/.gitkeep
│   └── evaluation/.gitkeep
├── data/
│   ├── raw/          # immutable crawl artifacts
│   ├── interim/      # normalized artifacts and generated hierarchy outputs
│   ├── processed/    # validated Phase 6 legal_chunks.jsonl
│   ├── indexes/      # future retrieval indexes
│   └── eval/         # future evaluation datasets
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
│   ├── traces/       # parser/retrieval/generation traces
│   ├── runs/         # experiment and benchmark runs
│   ├── metrics/      # evaluation metrics
│   └── logs/         # saved logs when needed
├── scripts/
├── src/
│   ├── core/
│   ├── ingestion/
│   ├── processing/
│   ├── indexing/
│   ├── retrieval/
│   ├── generation/
│   ├── services/
│   ├── api/
│   ├── evaluation/
│   ├── monitoring/
│   └── security/
├── tests/
│   ├── unit/
│   │   ├── ingestion/
│   │   ├── processing/
│   │   ├── indexing/
│   │   ├── retrieval/
│   │   ├── generation/
│   │   ├── services/
│   │   └── evaluation/
│   ├── integration/
│   ├── regression/
│   └── fixtures/
├── docs/
├── AGENTS.md
├── CLAUDE.md
├── PROJECT_CONTEXT.md
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

Future-phase directories are scaffolded with `.gitkeep` placeholders. Add
implementation logic to them only when the corresponding phase starts.

## Target Production Layout

Use this as the compact roadmap for future phases. The repository contains this
scaffold now, but implementation remains phase-gated.

```text
VnLaw-QA/
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
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   ├── indexes/
│   └── eval/
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
│   │   ├── crawling/
│   │   ├── audit/
│   │   ├── cleaning/
│   │   ├── parsing/
│   │   ├── retrieval/
│   │   └── generation/
│   ├── runs/
│   │   ├── experiments/
│   │   ├── benchmarks/
│   │   └── evaluations/
│   ├── metrics/
│   │   ├── indexing/
│   │   ├── retrieval/
│   │   ├── generation/
│   │   └── evaluation/
│   └── logs/
├── src/
│   ├── core/
│   ├── ingestion/
│   ├── processing/
│   ├── indexing/
│   ├── retrieval/
│   ├── generation/
│   ├── services/
│   ├── api/
│   ├── evaluation/
│   ├── monitoring/
│   └── security/
├── scripts/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   └── fixtures/
├── docs/
├── docker/
├── deployment/
├── monitoring/
└── .github/workflows/
```

Prefer this compact target over a deeply nested enterprise layout unless the
extra separation removes real operational complexity. Empty scaffold folders
must contain only `.gitkeep` until their phase begins.

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
```

### `src/processing/`

```text
implemented legal hierarchy parser
implemented parent-child chunking domain logic
future processed JSONL validation logic
```

Phase 5 Legal Hierarchy Parsing placement:

```text
domain logic: src/processing/
orchestration: src/services/
CLI: scripts/
tests: tests/unit/processing/
output: data/interim/{LAW_ID}/hierarchy.json
report: artifacts/reports/parsing/legal_parsing_report.json
```

Phase 6 Parent-child Chunking placement:

```text
domain logic: src/processing/
orchestration: src/services/
CLI: scripts/
tests: tests/unit/processing/ and tests/unit/services/
output: data/processed/legal_chunks.jsonl
report: artifacts/reports/chunking/
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

Retrieval placement:

```text
domain logic: src/retrieval/
reports: artifacts/reports/retrieval/
traces: artifacts/traces/retrieval/
metrics: artifacts/metrics/retrieval/
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

Generation/RAG placement:

```text
domain logic: src/generation/
reports: artifacts/reports/generation/
traces: artifacts/traces/generation/
metrics: artifacts/metrics/generation/
```

### `src/indexing/`

```text
future phase only
embedding/index build orchestration helpers
index payload validation
```

Indexing placement:

```text
domain logic: src/indexing/
indexes: data/indexes/
reports: artifacts/reports/indexing/
metrics: artifacts/metrics/indexing/
```

### `src/evaluation/`

```text
future phase only
golden QA and RAG evaluation logic
metrics aggregation
```

Evaluation placement:

```text
domain logic: src/evaluation/
datasets: data/eval/
reports: artifacts/reports/evaluation/
metrics: artifacts/metrics/evaluation/
runs: artifacts/runs/evaluations/
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
tests/unit/processing/
tests/unit/indexing/
tests/unit/retrieval/
tests/unit/generation/
tests/unit/services/
tests/unit/evaluation/
tests/integration/
tests/regression/
tests/fixtures/
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
