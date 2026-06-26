# VnLaw-QA

VnLaw-QA is a Vietnamese legal question-answering and retrieval-augmented
generation project focused on trusted legal sources, hierarchy-preserving data
processing, traceable citations, and safe fallback when evidence is
insufficient.

## What This Project Is

VnLaw-QA is a legal research support system for Vietnamese law. It builds a
trusted legal corpus, cleans and parses legal documents into hierarchy-aware
chunks, indexes those chunks for retrieval, and evaluates retrieval and RAG
behavior under strict citation and fallback rules.

The project emphasizes deterministic corpus processing before any LLM usage.
Legal text is kept traceable from the original trusted source through raw,
intermediate, processed, retrieval, and answer-evaluation artifacts.

## What This Project Is Not

- It is not a generic chatbot.
- It is not a replacement for professional legal advice.
- It must not give confident legal answers without trusted evidence.
- It must not fabricate laws, articles, clauses, points, penalties, dates, or
  citations.
- It must not treat a valid citation ID as proof that a generated claim is
  semantically faithful.

## Core Principles

- Use a trusted legal corpus, currently centered on `thuvienphapluat.vn`.
- Preserve Vietnamese legal hierarchy: `Phần -> Chương -> Mục -> Điều ->
  Khoản -> Điểm`.
- Prefer consolidated legal documents (`VBHN`) when available.
- Keep retrieval and generation citation-first.
- Fall back safely when evidence is missing, incomplete, unsafe, or indirect.
- Keep preprocessing deterministic before using LLMs.
- Keep secrets, Qdrant storage, model caches, and runtime state out of Git.

## Architecture

High-level flow:

```text
trusted legal sources
-> raw corpus
-> cleaning and normalization
-> legal hierarchy parsing
-> parent-child chunking
-> processed chunk validation
-> embedding and indexing
-> retrieval
-> evidence construction and selection
-> generation and evaluation
```

Main source modules:

| Path | Responsibility |
| --- | --- |
| `src/ingestion/` | Corpus registry loading, crawling support, raw audit, cleaning, and storage utilities. |
| `src/processing/` | Legal hierarchy parsing, parent-child chunking, and processed JSONL validation. |
| `src/indexing/` | Embedding model integration and Qdrant indexing/validation utilities. |
| `src/retrieval/` | Dense retrieval, evidence construction, evidence selection, Naive RAG generation, review export, and quality gates. |
| `src/evaluation/` | Frozen benchmark schemas, validation, metrics, and controlled retrieval comparison utilities. |
| `src/generation/` | Reserved home for generation-specific code when split from retrieval orchestration. |
| `src/services/` | Existing orchestration services where a service boundary is already used. |
| `src/api/`, `src/monitoring/`, `src/security/` | Separately scoped application, observability, and security surfaces. |

Scripts under `scripts/` are thin CLI wrappers. Reusable logic belongs under
`src/`.

## Pipeline Overview

```text
Legal corpus registry
-> crawling and raw audit
-> cleaning and normalization
-> hierarchy parsing
-> parent-child chunking
-> processed corpus validation
-> embedding and Qdrant indexing
-> retrieval
-> evidence selection
-> generation and evaluation
```

The validated processed corpus is `data/processed/legal_chunks.jsonl`. Runtime
reports and benchmark outputs live under `artifacts/reports/`.

## Current Capabilities

- Registry-driven Vietnamese legal corpus ingestion.
- Raw corpus audit and immutable raw artifact policy.
- Deterministic cleaning and normalization for trusted legal HTML.
- Hierarchy-preserving legal parser.
- Parent-child legal chunking without arbitrary character-window splitting.
- Processed chunk validation and embedding-readiness checks.
- BGE-M3 dense indexing in Qdrant.
- Sparse BM25 and hybrid retrieval evaluation utilities.
- Evidence construction and strict evidence-selection gate.
- Fallback-aware Naive RAG baseline.
- Citation-ID guard and manual faithfulness review workflow.
- Frozen legal QA benchmark validation and retrieval/generation evaluation
  workflow.

For current metrics, benchmark status, and stage-level decisions, read
`PROJECT_CONTEXT.md` and `docs/phase10_tracer.md`.

## Repository Layout

```text
VnLaw-QA/
├── configs/
│   ├── laws/          # trusted legal corpus registry
│   ├── indexing/      # embedding and Qdrant indexing config
│   ├── processing/    # parser/chunk/processed JSONL validation config
│   ├── retrieval/     # retrieval and quality-gate config
│   ├── evaluation/    # frozen benchmark config
│   └── llm/           # non-secret LLM provider defaults
├── data/
│   ├── raw/           # immutable crawl artifacts
│   ├── interim/       # derived cleaning and hierarchy artifacts
│   ├── processed/     # validated legal chunk corpus
│   └── eval/          # benchmark and reviewed evaluation assets
├── artifacts/
│   └── reports/       # generated reports and evaluation artifacts
├── docs/              # durable technical documentation
├── scripts/
│   ├── corpus/        # corpus pipeline CLIs
│   ├── indexing/      # embedding/Qdrant CLIs
│   ├── retrieval/     # retrieval, RAG, review, and quality-gate CLIs
│   └── evaluation/    # benchmark validation and comparison CLIs
├── src/               # reusable implementation modules
└── tests/             # unit, integration, regression, and fixtures
```

## Setup

Requirements:

- Python `>=3.11`
- `uv`

Install dependencies:

```bash
uv sync
```

Run the main lightweight checks:

```bash
uv run pytest tests/unit -q
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
uv lock --check
```

Some retrieval and generation commands require optional extras, Qdrant, local
model cache access, or provider credentials. See the component docs before
running those workflows.

## Common Commands

Validate the processed legal chunk corpus:

```bash
uv run python scripts/corpus/validate_processed_jsonl.py \
  --input data/processed/legal_chunks.jsonl \
  --config configs/processing/processed_jsonl_validation.yml \
  --output /tmp/processed_jsonl_validation_report.json \
  --pretty
```

Validate the frozen legal QA benchmark:

```bash
uv run python scripts/evaluation/validate_benchmark.py \
  --queries data/eval/legal_qa_benchmark/benchmark_queries.jsonl \
  --legal-targets data/eval/legal_qa_benchmark/benchmark_targets.jsonl \
  --evidence-judgments data/eval/legal_qa_benchmark/benchmark_qrels.jsonl \
  --evidence-groups data/eval/legal_qa_benchmark/evidence_groups.jsonl \
  --review-records data/eval/legal_qa_benchmark/review_records.jsonl \
  --split-manifest data/eval/legal_qa_benchmark/split_manifest.json \
  --benchmark-manifest data/eval/legal_qa_benchmark/benchmark_manifest.json \
  --processed-chunks data/processed/legal_chunks.jsonl
```

Run focused test suites:

```bash
uv run pytest tests/unit/processing -q
uv run pytest tests/unit/retrieval -q
uv run pytest tests/unit/evaluation -q
```

Inspect available CLI options before running corpus, indexing, retrieval, or
evaluation workflows:

```bash
uv run python scripts/corpus/validate_processed_jsonl.py --help
uv run python scripts/retrieval/run_naive_rag.py --help
uv run python scripts/evaluation/validate_benchmark.py --help
```

Detailed indexing, retrieval, generation, and benchmark commands are documented
in `docs/embedding_indexing.md`, `docs/naive_rag.md`, and
`docs/evaluation.md`.

## Data and Artifacts

- `data/raw/` is immutable crawl state.
- `data/interim/` contains derived cleaning and hierarchy artifacts.
- `data/processed/legal_chunks.jsonl` is the validated legal chunk corpus.
- `data/eval/` contains reviewed evaluation assets and frozen benchmark files.
- `artifacts/reports/` stores generated crawl, audit, indexing, retrieval, and
  evaluation reports.
- Qdrant storage, Hugging Face/model caches, virtual environments, Python
  caches, runtime logs, and local secrets must not be committed.

Do not mutate protected corpus paths unless a task explicitly scopes an
official rerun.

## Documentation Map

| Document | Purpose |
| --- | --- |
| `AGENTS.md` | Repository-wide safety, workflow, protected-path, and validation rules. |
| `PROJECT_CONTEXT.md` | Canonical current project state, architecture, limitations, and roadmap. |
| `docs/project_phase_journal.md` | Chronological engineering journal for completed corpus and processing phases. |
| `docs/phase10_tracer.md` | Operational tracker for frozen benchmark and advanced retrieval evaluation work. |
| `docs/end_to_end_pipeline.md` | End-to-end architecture and data-flow reference. |
| `docs/corpus_registry.md` | Trusted corpus registry schema and source policy. |
| `docs/raw_data_crawling.md` | Registry-driven crawling pipeline. |
| `docs/raw_corpus_audit.md` | Raw artifact audit rules and validation gates. |
| `docs/cleaning_normalization.md` | Vietnamese legal text cleaning and normalization details. |
| `docs/legal_parsing.md` | Legal hierarchy parser design. |
| `docs/parent_child_chunking.md` | Parent-child chunking design and validation notes. |
| `docs/processed_jsonl.md` | Processed chunk schema and embedding-readiness validation. |
| `docs/embedding_indexing.md` | BGE-M3 embedding and Qdrant indexing design. |
| `docs/naive_rag.md` | Dense retrieval and fallback-aware Naive RAG baseline reference. |
| `docs/evaluation.md` | Frozen benchmark protocol, schemas, validation, metrics, and CLI usage. |
| `docs/advanced_rag.md` | Advanced retrieval design notes and controlled-ablation context. |
| `docs/graphrag_agents.md` | Future GraphRAG and agent design notes. |
| `docs/api_deployment.md` | Future API/deployment notes. |
| `docs/mlops_maintenance.md` | Future MLOps and maintenance notes. |

## Development Boundaries

- Do not mutate `data/raw/`, `data/interim/`, `data/reports/`, or
  `data/processed/legal_chunks.jsonl` without explicit scope.
- Do not modify frozen benchmark labels, qrels, evidence groups, split
  assignments, or manifests outside an explicitly scoped benchmark task.
- Do not recreate, delete, upsert, re-index, or mutate Qdrant collections
  unless indexing work is explicitly requested.
- Do not bypass or relax evidence selection, fallback behavior, citation
  guards, or quality gates without a controlled safety-scoped ablation.
- Do not use LLMs for deterministic preprocessing.
- Do not commit runtime state, generated caches, local settings, or secrets.
- Do not claim production readiness or broad legal QA quality from narrow
  regression suites.

## Security

Provider credentials belong only in environment variables or an untracked
local `.env` file. Non-secret provider defaults may live in config files.

Never print, log, serialize, or commit API keys, tokens, Authorization headers,
or full environment dumps. If a secret is ever committed, remove it from the
repository history according to the project security policy and rotate the
credential before merging.
