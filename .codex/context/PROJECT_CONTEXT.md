# Codex Mirror Notice

This file is a Codex-compatible mirror of `PROJECT_CONTEXT.md`. The original content is preserved below.

## Current Status Refresh — June 10, 2026

This refresh supersedes older phase-status statements in the preserved mirror:

- Phase 7 and warning follow-up W1-W3 are complete.
- Phase 7 result: 40,389 valid chunks, 0 invalid chunks, 0 hard errors,
  8,206 accepted non-blocking warnings, payload ready rate 1.0, and
  `embedding_ready=true` / `ready_with_warnings`.
- Phase 7.5 read-only corpus audit is complete with **Go with watch items**.
- Phase 8 is complete and validated; retrieval is the next scoped work.
- Before indexing, run the official Phase 7 validator and read
  `docs/phase75_llm_corpus_audit.md`.
- Preserve short chunks, authority phrases, parent context, IDs, citations,
  hierarchy, hashes, source metadata, warnings, and repeal flags.

# VnLaw-QA Project Context

This file is intended to help Claude Code, Codex, or any future AI coding assistant quickly understand the current project state before making changes.

## 1. Project Goal

VnLaw-QA is a Vietnamese Legal QA/RAG system. It is not a generic chatbot.

### Architecture

- `scripts/` = CLI entrypoints (parse arguments, call services, print results)
- `src/services/` = pipeline orchestration (coordinate phase execution, build reports)
- `src/ingestion/` = Phase 1-4 domain logic (crawler, audit, cleaning, storage)
- `src/processing/` = Phase 5-7 domain logic (parsing, chunking, JSONL validation)
- `src/indexing/` = Phase 8 domain logic (embedding, Qdrant)
- `src/retrieval/` = Phase 9-10 domain logic (search, reranking)
- `src/generation/` = Phase 9-11 domain logic (LLM, prompts, answers)
- `src/agents/` = Phase 11 domain logic (GraphRAG, orchestration)
- `src/evaluation/` = Phase 12 domain logic (RAGAS, metrics)
- `src/api/` = Phase 13 domain logic (FastAPI)
- `src/monitoring/` / `src/security/` = Phase 14 domain logic

Test layout:

- `tests/unit/ingestion/` covers `src/ingestion/*` low-level domain modules.
- `tests/unit/processing/` covers `src/processing/*` parser and future chunking modules.
- `tests/unit/services/` covers `src/services/*` orchestration services and CLI wrappers.

The system must retrieve, process, and answer questions based on Vietnamese legal documents while preserving legal structure, source traceability, and citation integrity.

The long-term goal is to build a reliable Legal RAG pipeline that can answer Vietnamese legal questions with grounded evidence, explicit citations, and safe fallback behavior when evidence is insufficient.

The project pipeline is organized as:

```text
Corpus Registry → Registry-driven Crawling → Raw Corpus Audit → Cleaning / Normalization → Legal Hierarchy Parsing → Parent-child Chunking → Processed Chunk Validation & Embedding Readiness → Embedding / Indexing → Naive RAG → Advanced RAG → GraphRAG → Evaluation → API / Deployment → MLOps / Maintenance
```

## 2. Core Legal RAG Principles

- No source → no confident answer.
- No citation → not a valid legal answer.
- Preserve legal hierarchy: Phần → Chương → Mục → Điều → Khoản → Điểm.
- Parser and chunker quality come before model complexity.
- Do not jump to GraphRAG, agents, or fine-tuning before Naive RAG and evaluation are stable.
- Do not let the LLM invent legal citations.
- Every final legal answer must be traceable back to retrieved source chunks.
- Legal data processing must be deterministic before LLM-based evaluation is introduced.
- Raw data must not be mutated; derived artifacts should be written to separate directories.

## 3. Current Project Status

- The project uses `uv` for environment and dependency management.
- The corpus registry exists at `configs/laws/corpus_registry.yml`.
- The registry-driven crawler has been implemented.
- The crawling phase has completed successfully.
- The registry contains 52 legal document entries.
- 52/52 legal documents have been crawled successfully.
- Raw artifacts are stored under `data/raw/`.
- Raw Corpus Audit & Validation has been implemented.
- **Phase 4 — Cleaning & Normalization is complete/gate-ready.**
- The cleaned corpus has 52/52 `normalized.json` artifacts and 52/52 optional `cleaned.txt` debug artifacts under `data/interim/`.
- Cleaner output uses `cleaner_version` `v0.8.0`.
- Encoded TVPL footer/watermark artifacts are removed from cleaned outputs.
- Article metrics are explicit: `article_reference_count` counts all `Điều N` mentions, while `article_heading_count` and `max_heading_article_number` describe real article headings.
- Remaining duplicate-style flags such as BLHS_VBHN are diagnostic/semantic concerns, not cleaning blockers unless extraction duplication is proven.
- **Phase 5 — Legal Hierarchy Parsing is complete and hardened.**
- 52/52 `hierarchy.json` artifacts exist under `data/interim/{LAW_ID}/`.
- Official parsing report: `artifacts/reports/parsing/legal_parsing_report.json`.
- Full-corpus result: 6 successes, 46 successes with warnings, 0 failures.
- Hardened validation: 0 validator failures, 0 RED audit cases, 0 ORANGE
  audit cases, 0 source-tail leakage nodes.
- Zero `AMBIGUOUS_CLAUSE_CANDIDATE` and zero
  `POINT_LIKE_LINE_OUTSIDE_CLAUSE` warnings.
- Remaining accepted non-blocking warnings: `SOURCE_NOTE_EXCLUDED`,
  `EMPTY_ARTICLE_NODE`, `NODE_ID_COLLISION_RESOLVED`,
  `ARTICLE_COUNT_MISMATCH`, `MAX_ARTICLE_NUMBER_MISMATCH`.
- **Phase 6 — Parent-child Chunking is complete and validated.**
- Output JSONL: `data/processed/legal_chunks.jsonl`.
- Chunking report: `artifacts/reports/chunking/chunking_report.json`.
- Full-corpus result: 34 successes, 18 successes with warnings, 0 failures,
  40,389 chunks.
- Chunk breakdown: 1,322 article chunks, 20,643 clause chunks, 18,424 point chunks.
- Full-corpus validation: 0 bad JSON lines, 0 duplicate `chunk_id`, 0
  selection-rule issues, 0 chunk invariant issues.
- Phase 6 hardening result: 0 source-tail markers in chunk `text`, 0
  source-tail markers in `parent_text`, 180 empty/repealed chunks flagged, and
  max `parent_text` length reduced to 14,481 characters.
- Phase 7 and Phase 7.5 are complete with 40,389 valid chunks, 0 invalid
  chunks, 0 errors, 8,206 accepted warnings, and payload readiness 1.0.
- Phase 8 is complete: all 40,389 chunks are indexed in Qdrant collection
  `vnlaw_chunks_bgem3_v1_full` with BGE-M3 dense vectors (`dense`, 1024,
  Cosine), 0 failed chunks, and passing full index validation.

## 4. Implemented Phases

### Phase 0 — Project Setup and Principles

Implemented. Relevant files:

- `pyproject.toml`
- `CLAUDE.md`
- `PROJECT_CONTEXT.md`
- `.env.example`
- `docs/project_setup.md`

### Phase 1 — Legal Corpus Registry

Implemented. Relevant files:

- `configs/laws/corpus_registry.yml`
- `docs/corpus_registry.md`

The registry is the source of truth for the legal corpus. It defines each legal document using metadata such as `law_id`, `name`, `tier`, `group`, `domain_tags`, `source_domain`, `source_type`, `url`, `crawl_status`, `priority`, and `notes`.

### Phase 2 — Registry-driven Crawling

Implemented. Relevant files:

- `src/ingestion/`
- `scripts/`
- `docs/raw_data_crawling.md`
- `docs/project_phase_journal.md`
- `data/raw/`
- `artifacts/reports/crawling/crawl_report.json`

The crawler reads from `configs/laws/corpus_registry.yml`, fetches legal source
artifacts from approved sources, stores immutable raw evidence under
`data/raw/`, and writes the generated batch crawl report to
`artifacts/reports/crawling/crawl_report.json`.

### Phase 3 — Raw Corpus Audit & Validation

Implemented. Relevant files:

- `src/ingestion/audit.py`
- `scripts/corpus/audit_raw_corpus.py`
- `tests/unit/ingestion/test_audit.py`
- `docs/raw_corpus_audit.md`
- `artifacts/reports/audit/raw_corpus_audit.json`

This phase validates that crawled raw artifacts are complete, readable, not blocked/error pages, and suitable for Cleaning & Normalization.

### Phase 4 — Cleaning & Normalization

Implemented and gate-ready. Relevant files:

- `src/ingestion/cleaning.py`
- `src/services/cleaning_service.py`
- `scripts/corpus/clean_raw_corpus.py`
- `src/ingestion/cleaning_diagnostics.py`
- `src/services/cleaning_quality_audit_service.py`
- `scripts/corpus/audit_cleaning_quality.py`
- `tests/unit/ingestion/test_cleaning.py`
- `docs/cleaning_normalization.md`
- `data/interim/{LAW_ID}/normalized.json`
- `data/interim/{LAW_ID}/cleaned.txt`
- `artifacts/reports/cleaning/cleaning_report.json`
- `artifacts/reports/cleaning/cleaning_quality_audit.json`

The full 52-law corpus cleans successfully with no warning artifacts, failed artifacts, suspiciously short outputs, or missing article markers. Cleaning preserves legal text structure for the Legal Hierarchy Parser and removes known TVPL encoded footer/watermark artifacts.

## 5. Current Phase

Completed phase:

```text
Phase 5 — Legal Hierarchy Parsing (complete and hardened)
```

Completed phase:

```text
Phase 6 — Parent-child Chunking
```

Goal: Create validated parent-child chunks from the parsed legal hierarchy.
Child units are Clause or Point where available, with Article text preserved as
parent context for downstream retrieval and generation.

This phase consumes `data/interim/{LAW_ID}/hierarchy.json`. It does not embed,
index, retrieve, generate answers, or implement RAG.

Implemented outputs:

```text
data/processed/legal_chunks.jsonl
artifacts/reports/chunking/chunking_report.json
```

Key requirements:

- Read hierarchy artifacts from `data/interim/`.
- Do not mutate `data/raw/`.
- Do not rewrite Phase 5 parsing unless a chunking-blocking parser defect is proven.
- Preserve source traceability from hierarchy node metadata and offsets.
- Use legal hierarchy instead of arbitrary token/character windows.
- Validate chunks before any embedding or retrieval work.
- Add focused unit tests.
- Domain logic under `src/processing/`.
- Orchestration/report building under `src/services/`.
- CLI entrypoint under `scripts/`.
- Unit tests under `tests/unit/processing/`.

Current next phase:

```text
Phase 9 — Retrieval layer / Naive RAG baseline
```

## 6. Next Immediate Tasks

1. Build BGE-M3 query embedding and dense top-k Qdrant retrieval.
2. Preserve warning-aware payload, parent context, and legal traceability.
3. Evaluate retrieval quality before adding answer generation.
4. Keep sparse/hybrid retrieval and reranking separately scoped.

## 7. Next Phase: Retrieval / Naive RAG

Phase 8 is complete and validated. Retrieval is next and must be separately
scoped.

Key requirements:

- embed queries with BGE-M3;
- search collection `vnlaw_chunks_bgem3_v1_full` using named vector `dense`;
- retain `parent_text` as traceable Article context;
- preserve IDs, citations, hierarchy, hashes, source metadata, and warnings;
- evaluate retrieval before implementing answer generation.

## 8. Do Not Do Yet

- Do not mutate `data/processed/legal_chunks.jsonl`.
- Do not commit Qdrant storage or model caches.
- Do not implement answer generation before retrieval is evaluated.
- Do not implement Advanced RAG yet.
- Do not implement GraphRAG or agents yet.
- Do not build UI yet.
- Do not implement API/deployment work yet.
- Do not fine-tune any model yet.
- Do not chunk by arbitrary character length.
- Do not use LLM-based cleaning.
- Do not mutate `data/raw/`.

## 9. Important Paths

```text
configs/laws/corpus_registry.yml
data/raw/
data/interim/
data/processed/
artifacts/reports/indexing/<run_id>/
src/ingestion/
src/processing/
scripts/
tests/unit/ingestion/
tests/unit/processing/
docs/end_to_end_pipeline.md
docs/project_phase_journal.md
docs/raw_data_crawling.md
docs/raw_corpus_audit.md
docs/cleaning_normalization.md
docs/legal_parsing.md
docs/parent_child_chunking.md
docs/processed_jsonl.md
```

## 8.1 Target Production Layout

The repository now includes the production scaffold with `.gitkeep`
placeholders. Implementation remains phase-gated; empty future-phase folders do
not imply that those phases have started.

```text
VnLaw-QA/
├── configs/{laws,sources,ingestion,processing,indexing,retrieval,generation,evaluation}/
├── data/{raw,interim,processed,indexes,eval}/
├── artifacts/
│   ├── reports/{crawling,audit,cleaning,parsing,chunking,indexing,retrieval,generation,evaluation}/
│   ├── traces/{crawling,audit,cleaning,parsing,retrieval,generation}/
│   ├── runs/{experiments,benchmarks,evaluations}/
│   ├── metrics/{indexing,retrieval,generation,evaluation}/
│   └── logs/
├── src/{core,ingestion,processing,indexing,retrieval,generation,services,api,evaluation,monitoring,security}/
├── scripts/
├── tests/{unit,integration,regression,fixtures}/
├── docs/
├── docker/
├── deployment/
├── monitoring/
└── .github/workflows/
```

Keep the current boundary: CLI in `scripts/`, orchestration in `src/services/`,
and reusable domain logic in focused `src/` modules. Do not add implementation
logic to scaffolded future-phase directories before their phase starts.

## 8.2 Future Phase Placement

```text
Phase 5 Legal Hierarchy Parsing:
  domain logic: src/processing/
  orchestration: src/services/
  CLI: scripts/
  tests: tests/unit/processing/
  output: data/interim/{LAW_ID}/hierarchy.json
  report: artifacts/reports/parsing/legal_parsing_report.json

Phase 6 Parent-child Chunking:
  domain logic: src/processing/
  orchestration: src/services/
  CLI: scripts/corpus/chunk_legal_corpus.py
  output: data/processed/legal_chunks.jsonl
  report: artifacts/reports/chunking/chunking_report.json

Phase 8 Indexing:
  domain logic: src/indexing/
  indexes: data/indexes/
  reports: artifacts/reports/indexing/
  metrics: artifacts/metrics/indexing/

Retrieval:
  domain logic: src/retrieval/
  reports: artifacts/reports/retrieval/
  traces: artifacts/traces/retrieval/
  metrics: artifacts/metrics/retrieval/

Generation/RAG:
  domain logic: src/generation/
  reports: artifacts/reports/generation/
  traces: artifacts/traces/generation/
  metrics: artifacts/metrics/generation/

Evaluation:
  domain logic: src/evaluation/
  datasets: data/eval/
  reports: artifacts/reports/evaluation/
  metrics: artifacts/metrics/evaluation/
  runs: artifacts/runs/evaluations/
```

## 10. Official Pipeline Commands

Official user-facing commands for the ingestion pipeline:

- Crawl raw legal corpus:

```bash
uv run python scripts/corpus/crawl_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --output data/raw \
  --report artifacts/reports/crawling/crawl_report.json \
  --only-status pending
```

- Audit raw corpus:

```bash
uv run python scripts/corpus/audit_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --output artifacts/reports/audit/raw_corpus_audit.json
```

- Clean and normalize corpus:

```bash
uv run python scripts/corpus/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report artifacts/reports/cleaning/cleaning_report.json \
  --write-txt \
  --audit
```

- Audit cleaning quality:

```bash
uv run python scripts/corpus/audit_cleaning_quality.py \
  --raw-dir data/raw \
  --interim-dir data/interim \
  --report-dir artifacts/reports/cleaning \
  --registry configs/laws/corpus_registry.yml
```

- Chunk legal corpus:

```bash
uv run python scripts/corpus/chunk_legal_corpus.py \
  --input-dir data/interim \
  --output data/processed/legal_chunks.jsonl \
  --report artifacts/reports/chunking/chunking_report.json \
  --overwrite \
  --verbose \
  --no-color
```

- Run unit tests:

```bash
uv run pytest tests/unit/ingestion -q
```

## 10. Trusted Source Policy

The only default trusted source is:

```text
https://thuvienphapluat.vn
```

Do not add another data source unless the task explicitly asks for it and the change is documented as an approved architectural decision.

Prefer **VBHN** consolidated documents when available. If no VBHN exists, crawl and represent the original document and amendments in chronological order with accurate `effective_date`, `expiry_date`, and status metadata.

## 11. Current Completed Work Summary

### Phase 4 — Cleaning & Normalization

- 52/52 legal documents cleaned successfully.
- Outputs: `normalized.json` + optional `cleaned.txt` per law under `data/interim/{LAW_ID}/`.
- Cleaner version: `v0.8.0`.
- Known fixes applied:
  - Start-trimming defects corrected for LANM_2025, LVL_2025, LNO_VBHN, LXD_VBHN.
  - Conservative line-fragment repair for split Vietnamese words.
  - Block-aware HTML extraction to avoid artificial newlines from inline elements.
  - Source-law / amendment pre-body note removal for LHNGD_VBHN, LTATGT_VBHN.
  - Encoded TVPL footer/watermark artifacts removed.
  - Article metric clarity: `article_reference_count`, `article_heading_count`, `max_heading_article_number`, `has_heading_article_1`, `heading_sequence_score`.
- Final validation: 57 cleaning tests passed; 159 total ingestion tests passed.
- Gate decision: **Phase 4 complete/gate-ready.**

## 12. Next Phase Preparation

Phase 8 is complete and validated. Retrieval / Naive RAG is the next
engineering focus and requires a separately scoped task.

Key design constraints:

- Query collection `vnlaw_chunks_bgem3_v1_full`.
- Must not mutate protected corpus paths.
- Must preserve `Phần / Chương / Mục / Điều / Khoản / Điểm` traceability.
- Must preserve Article parent context from `parent_text`.
- Must preserve accepted warning visibility and repeal metadata.
- Must evaluate dense retrieval before adding answer generation.

## 13. Out-of-Scope Reminders

These are explicitly deferred until their respective phase gates are met:

- Embedding / indexing (Qdrant)
- Neo4j graph construction
- Naive RAG baseline
- Advanced RAG (hybrid search, RRF, reranking)
- GraphRAG and multi-agent retrieval
- API / deployment (FastAPI)
- Fine-tuning / MLOps
- UI work
