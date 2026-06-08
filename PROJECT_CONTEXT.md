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

The project pipeline is organized as:

```text
Corpus Registry
→ Registry-driven Crawling
→ Raw Corpus Audit
→ Cleaning / Normalization
→ Legal Hierarchy Parsing
→ Parent-child Chunking
→ Processed Chunk Validation & Embedding Readiness
→ Embedding / Indexing
→ Naive RAG
→ Advanced RAG
→ GraphRAG
→ Evaluation
→ API / Deployment
→ MLOps / Maintenance
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
- The registry contains **52 legal document entries**.
- 52/52 legal documents have been crawled successfully under `data/raw/`.
- 52/52 raw artifacts passed audit.
- 52/52 documents cleaned to `data/interim/{LAW_ID}/normalized.json`.
- **Phase 5 — Legal Hierarchy Parsing is complete and hardened.**
- 52/52 `hierarchy.json` artifacts generated under `data/interim/{LAW_ID}/`.
- Official parsing report: `artifacts/reports/parsing/legal_parsing_report.json`.
- Full-corpus result: 6 successes, 46 successes with warnings, 0 failures.
- Hardened validation: 0 orphan nodes, 0 invalid parent chains, 0 invalid offsets, 0 invalid sibling overlaps, 0 duplicate node IDs.
- Zero RED audit cases, zero ORANGE audit cases, zero source-tail leakage nodes.
- Zero `AMBIGUOUS_CLAUSE_CANDIDATE` and zero `POINT_LIKE_LINE_OUTSIDE_CLAUSE` warnings.
- Remaining accepted non-blocking warnings: `SOURCE_NOTE_EXCLUDED`, `EMPTY_ARTICLE_NODE`, `NODE_ID_COLLISION_RESOLVED`, `ARTICLE_COUNT_MISMATCH`, `MAX_ARTICLE_NUMBER_MISMATCH`.
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
- Full validation audit:
  `artifacts/reports/chunking/full_corpus_validation_report.json`.
- Do not arbitrarily split Article parent context in Phase 6. Phase 7/8 should
  embed only `text` and handle `parent_text` as Article context payload.
**Phase 7 â Processed Chunk Validation & Embedding Readiness**, a validation gate over `data/processed/legal_chunks.jsonl` before embedding/indexing begins. Phase 7 does not implement embedding or indexing.
  processed chunk output remains validated.
- Current branch: `feature/legal-parser-chunking`.

## 4. Implemented Phases

### Phase 0 — Project Setup and Principles

Implemented.

Relevant files:

- `pyproject.toml` — Python 3.11+, hatchling, pydantic v2, ruff, pytest
- `CLAUDE.md` — coding, workflow, and assistant rules
- `PROJECT_CONTEXT.md` — this file
- `.env.example` — environment variable placeholders
- `docs/project_setup.md`

### Phase 1 — Legal Corpus Registry

Implemented.

Relevant files:

- `configs/laws/corpus_registry.yml`
- `src/ingestion/registry.py`
- `src/ingestion/models.py`
- `docs/corpus_registry.md`

The registry is the source of truth for the legal corpus. It defines each legal document using metadata such as `law_id`, `name`, `tier`, `group`, `domain_tags`, `source_domain`, `source_type`, `url`, `crawl_status`, `priority`, and `notes`.

### Phase 2 — Registry-driven Crawling

Implemented (52/52).

Relevant files:

- `src/ingestion/crawler.py`
- `src/ingestion/selector.py`
- `src/ingestion/storage.py`
- `src/ingestion/rate_limiter.py`
- `src/services/crawl_service.py`
- `scripts/crawl_raw_corpus.py`
- `docs/raw_data_crawling.md`
- `data/raw/`
- `artifacts/reports/crawling/crawl_report.json`

The crawler reads from `configs/laws/corpus_registry.yml`, fetches legal source artifacts from `thuvienphapluat.vn`, stores immutable raw evidence under `data/raw/{law_id}/latest/`, and writes batch crawl reports.

### Phase 3 — Raw Corpus Audit & Validation

Implemented.

Relevant files:

- `src/ingestion/audit.py`
- `src/services/raw_audit_service.py`
- `scripts/audit_raw_corpus.py`
- `tests/unit/ingestion/test_audit.py`
- `docs/raw_corpus_audit.md`
- `artifacts/reports/audit/raw_corpus_audit.json`

Validates that crawled raw artifacts are complete, readable, not blocked/error pages, and suitable for Cleaning & Normalization.

### Phase 4 — Cleaning & Normalization

Implemented and gate-ready.

Relevant files:

- `src/ingestion/cleaning.py`
- `src/ingestion/cleaning_diagnostics.py`
- `src/services/cleaning_service.py`
- `src/services/cleaning_quality_audit_service.py`
- `scripts/clean_raw_corpus.py`
- `scripts/audit_cleaning_quality.py`
- `tests/unit/ingestion/test_cleaning.py`
- `docs/cleaning_normalization.md`
- `data/interim/`
- `artifacts/reports/cleaning/cleaning_report.json`
- `artifacts/reports/cleaning/cleaning_quality_audit.json`

The full 52-law corpus cleans successfully. Cleaning preserves legal text structure, removes TVPL encoded footer/watermark artifacts, and produces `normalized.json` with article/clause/point markers intact. Cleaner version: `v0.8.0`.

### Phase 5 — Legal Hierarchy Parsing

Implemented and validated.

Relevant files:

- `src/processing/normalized_input.py`
- `src/processing/legal_hierarchy_models.py`
- `src/processing/legal_heading_recognizer.py`
- `src/processing/legal_span_segmenter.py`
- `src/processing/legal_hierarchy_builder.py`
- `src/processing/legal_tree_validator.py`
- `src/processing/legal_parser.py`
- `src/services/legal_parsing_service.py`
- `scripts/parse_legal_hierarchy.py`
- `tests/unit/processing/`
- `tests/unit/services/test_legal_parsing_service.py`
- `docs/legal_parsing.md`
- `data/interim/{LAW_ID}/hierarchy.json`
- `artifacts/reports/parsing/legal_parsing_report.json`

The parser consumes `data/interim/{LAW_ID}/normalized.json`, preserves exact offsets into `normalized_text`, creates a root Law node plus flat hierarchy nodes for Part/Chapter/Section/Article/Clause/Point, and validates the tree before writing. Parser version: `v0.1.0`.

Key design: `nodes` is a flat list linked by `node_id`/`parent_id`/`children`. Parent node `text` includes all descendant text (parent-inclusive design). This enables downstream citation and chunking without reparsing.

## 5. Current Phase

Completed phase:

```text
Phase 6 — Parent-child Chunking
```

Phase 6 creates validated parent-child chunks from the parsed legal hierarchy.
Child units are Clause or Point where available, with Article text preserved as
parent context for downstream retrieval and generation.

This phase consumes `data/interim/{LAW_ID}/hierarchy.json`. It does not embed,
index, retrieve, generate answers, or implement RAG.

Implemented outputs:

```text
data/processed/legal_chunks.jsonl
artifacts/reports/chunking/chunking_report.json
```

Implemented Phase 6 components:

- `src/processing/legal_chunk_models.py`
- `src/processing/legal_chunker.py`
- `src/processing/legal_chunk_validator.py`
- `src/services/chunking_service.py`
- `scripts/chunk_legal_corpus.py`
- `tests/unit/processing/test_legal_chunk_models.py`
- `tests/unit/processing/test_legal_chunker.py`
- `tests/unit/processing/test_legal_chunk_validator.py`
- `tests/unit/services/test_chunking_service.py`
- `tests/unit/services/test_chunk_legal_corpus_cli.py`

Current next phase:

```text
Phase 7 — Processed Chunk Validation & Embedding Readiness
```

Phase 7 validates `data/processed/legal_chunks.jsonl` as the safe
input to Phase 8 embedding/indexing. Phase 7 is a validation gate only;
it does not implement embedding or indexing. Phase 8 should embed only
`text`; keep `parent_text` as retrieval/LLM context payload.

## 6. Next Immediate Tasks

1. Run any final documentation/context review for Phase 6 handoff.
2. Define and implement Phase 7 validation checks over `data/processed/legal_chunks.jsonl`.
3. Confirm embedding-readiness fields, payload strategy, and long parent-text
   handling before Phase 8 indexing.
4. Do not claim RAG readiness until retrieval, generation, and evaluation gates
   are implemented and validated.

## 7. Upcoming Phases

| Phase | Name | Status |
| --- | --- | --- |
| 6 | Parent-child Chunking | **Complete / Validated** |
| 7 | Processed Chunk Validation & Embedding Readiness | **Next** |
| 8 | Embedding & Indexing | Planned |
| 9 | Naive RAG | Future |
| 10 | Advanced RAG | Future |
| 11 | GraphRAG & Agents | Future |
| 12 | Evaluation | Future |
| 13 | API & Deployment | Future |
| 14 | MLOps & Maintenance | Future |

## 8. Do Not Do Yet

- Do not modify Phase 6 generated artifacts unless rerunning the official
  chunking command intentionally.
- Do not implement embedding/indexing before the processed JSONL validation
  gate is defined and passed.
- Do not implement Naive RAG yet.
- Do not implement Advanced RAG yet.
- Do not implement GraphRAG or agents yet.
- Do not build UI or API yet.
- Do not fine-tune any model yet.
- Do not chunk by arbitrary character length.
- Do not mutate `data/raw/`.

## 9. Important Paths

```text
configs/laws/corpus_registry.yml
data/raw/
data/interim/
data/processed/
artifacts/reports/<phase>/
src/core/
src/ingestion/
src/processing/
src/services/
src/indexing/
src/retrieval/
src/generation/
src/agents/
src/api/
src/evaluation/
scripts/
tests/unit/ingestion/
tests/unit/processing/
tests/unit/services/
docs/end_to_end_pipeline.md
docs/project_phase_journal.md
docs/legal_parsing.md
docs/parent_child_chunking.md
docs/processed_jsonl.md
docs/embedding_indexing.md
docs/naive_rag.md
docs/advanced_rag.md
docs/graphrag_agents.md
docs/evaluation.md
```

## 10. Official Pipeline Commands

### Phase 2 — Crawl

```bash
uv run python scripts/crawl_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --output data/raw \
  --report artifacts/reports/crawling/crawl_report.json \
  --only-status pending
```

### Phase 3 — Audit

```bash
uv run python scripts/audit_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --output artifacts/reports/audit/raw_corpus_audit.json
```

### Phase 4 — Clean

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report artifacts/reports/cleaning/cleaning_report.json
```

### Phase 5 — Parse

```bash
uv run python scripts/parse_legal_hierarchy.py \
  --input-dir data/interim \
  --output-dir data/interim \
  --report artifacts/reports/parsing/legal_parsing_report.json
```

### Phase 6 — Chunk

```bash
uv run python scripts/chunk_legal_corpus.py \
  --input-dir data/interim \
  --output data/processed/legal_chunks.jsonl \
  --report artifacts/reports/chunking/chunking_report.json \
  --overwrite \
  --verbose \
  --no-color
```

## 11. Development Commands

```bash
# Setup
uv sync

# Run all tests
uv run pytest

# Run focused tests
uv run pytest tests/unit/ingestion/test_cleaning.py -v
uv run pytest tests/unit/processing/ -v
uv run pytest tests/unit/services/ -v

# Linting
uv run ruff check src tests
uv run ruff format src tests

# Type checking
uv run mypy src
```

## 12. Branch Roadmap

```text
feature/data-crawling           done
feature/raw-corpus-audit        done
feature/cleaning-normalization  done
feature/legal-parser-chunking   current / Phase 6 complete
feature/processed-jsonl         next
feature/embedding-indexing      future
feature/naive-rag               future
feature/advanced-rag            future
feature/graphrag-agents         future
feature/evaluation              future
feature/api-deployment          future
```

Branch guidance:

- Keep branches small and phase-focused.
- Each branch should pass its validation gate before merging.
- Do not mix cleaning, parsing, chunking, and RAG in the same branch.
- Documentation should be updated together with each phase implementation.
