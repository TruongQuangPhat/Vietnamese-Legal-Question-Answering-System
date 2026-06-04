# Codex Mirror Notice

This file is a Codex-compatible mirror of `PROJECT_CONTEXT.md`. The original content is preserved below.

# VnLaw-QA Project Context

This file is intended to help Claude Code, Codex, or any future AI coding assistant quickly understand the current project state before making changes.

## 1. Project Goal

VnLaw-QA is a Vietnamese Legal QA/RAG system. It is not a generic chatbot.

### Architecture

- `scripts/` = CLI entrypoints (parse arguments, call services, print results)
- `src/services/` = pipeline orchestration (coordinate phase execution, build reports)
- `src/ingestion/` = reusable domain logic (crawler, audit, cleaning, storage)

The system must retrieve, process, and answer questions based on Vietnamese legal documents while preserving legal structure, source traceability, and citation integrity.

The long-term goal is to build a reliable Legal RAG pipeline that can answer Vietnamese legal questions with grounded evidence, explicit citations, and safe fallback behavior when evidence is insufficient.

The project pipeline is organized as:

```text
Corpus Registry → Registry-driven Crawling → Raw Corpus Audit → Cleaning / Normalization → Legal Hierarchy Parsing → Parent-child Chunking → Processed JSONL Validation → Embedding / Indexing → Naive RAG → Advanced RAG → GraphRAG → Evaluation → API / Deployment → MLOps / Maintenance
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
- The next engineering phase is **Phase 5 — Legal Hierarchy Parsing**.

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
- `scripts/audit_raw_corpus.py`
- `tests/unit/ingestion/test_audit.py`
- `docs/raw_corpus_audit.md`
- `artifacts/reports/audit/raw_corpus_audit.json`

This phase validates that crawled raw artifacts are complete, readable, not blocked/error pages, and suitable for Cleaning & Normalization.

### Phase 4 — Cleaning & Normalization

Implemented and gate-ready. Relevant files:

- `src/ingestion/cleaning.py`
- `src/services/cleaning_service.py`
- `scripts/clean_raw_corpus.py`
- `src/ingestion/cleaning_diagnostics.py`
- `src/services/cleaning_quality_audit_service.py`
- `scripts/audit_cleaning_quality.py`
- `tests/unit/ingestion/test_cleaning.py`
- `docs/cleaning_normalization.md`
- `data/interim/{LAW_ID}/normalized.json`
- `data/interim/{LAW_ID}/cleaned.txt`
- `artifacts/reports/cleaning/cleaning_report.json`
- `artifacts/reports/cleaning/cleaning_quality_audit.json`

The full 52-law corpus cleans successfully with no warning artifacts, failed artifacts, suspiciously short outputs, or missing article markers. Cleaning preserves legal text structure for the Legal Hierarchy Parser and removes known TVPL encoded footer/watermark artifacts.

## 5. Current Phase

Current phase:

```text
Phase 5 — Legal Hierarchy Parsing
```

Goal: Extract deterministic Vietnamese legal hierarchy from the normalized corpus:

```text
Phần → Chương → Mục → Điều → Khoản → Điểm
```

This phase should consume `data/interim/{LAW_ID}/normalized.json`.

It should not jump directly to embedding, RAG, Advanced RAG, or GraphRAG.

Expected outputs:

```text
data/interim/{LAW_ID}/hierarchy.json
artifacts/reports/parsing/legal_parsing_report.json
```

Key requirements:

- Read normalized artifacts from `data/interim/`.
- Do not mutate `data/raw/`.
- Do not rewrite cleaning behavior unless a parser-blocking cleaning defect is proven.
- Preserve source traceability from normalized artifact metadata.
- Preserve legal markers and numbering patterns:
  - Phần
  - Chương
  - Mục
  - Điều
  - numbered clause lines such as `1.`, `2.`, `3.`
  - point labels such as `a)`, `b)`, `c)`
- Build a hierarchy tree before chunking.
- Validate parser output before any embedding or retrieval work.
- Add focused unit tests.
- Put parser domain logic under `src/processing/`.
- Put parser orchestration/report building under `src/services/`.
- Put parser CLI entrypoint under `scripts/`.
- Put parser unit tests under `tests/unit/processing/`.

Important Vietnamese legal formatting note:

Vietnamese legal documents often do not literally write the words `Khoản` and `Điểm` in the body. Clauses are commonly represented by numbered lines such as `1.`, `2.`, `3.`, and points are commonly represented by lettered labels such as `a)`, `b)`, `c)`. Cleaning must preserve these patterns for the parser.

## 6. Next Immediate Tasks

1. Create or use the branch `feature/legal-parser-chunking`.
2. Design the legal hierarchy parser over `normalized.json` inputs.
3. Preserve hierarchy levels:
   - Phần
   - Chương
   - Mục
   - Điều
   - numbered clause lines like `1.`, `2.`, `3.`
   - point labels like `a)`, `b)`, `c)`
4. Generate `data/interim/{LAW_ID}/hierarchy.json`.
5. Generate `artifacts/reports/parsing/legal_parsing_report.json`.
6. Add parser unit tests before any chunking implementation.
7. Validate parser correctness on known complex laws such as BLDS_2015, BLHS_VBHN, LDD_VBHN, LTTHC, and LVL_2025.

## 7. Do Not Do Yet

- Do not implement Parent-child Chunking until hierarchy parsing passes its validation gate.
- Do not implement Processed JSONL export yet.
- Do not implement embedding/indexing yet.
- Do not implement Naive RAG yet.
- Do not implement Advanced RAG yet.
- Do not implement GraphRAG or agents yet.
- Do not build UI yet.
- Do not implement API/deployment work yet.
- Do not fine-tune any model yet.
- Do not chunk by arbitrary character length.
- Do not use LLM-based cleaning.
- Do not mutate `data/raw/`.

## 8. Important Paths

```text
configs/laws/corpus_registry.yml
data/raw/
data/interim/
data/processed/
artifacts/reports/<phase>/
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

The current repository should stay phase-focused, but agents should understand
the intended production direction:

```text
VnLaw-QA/
├── configs/{laws,sources,ingestion,processing,indexing,retrieval,generation,evaluation}/
├── data/{raw,interim,processed,indexes,eval}/
├── artifacts/
│   ├── reports/{crawling,audit,cleaning,parsing,chunking,indexing,retrieval,generation,evaluation}/
│   ├── traces/{crawling,cleaning,parsing,retrieval,generation}/
│   ├── runs/{experiments,benchmarks,evaluations}/
│   ├── metrics/{retrieval,generation,evaluation}/
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

Do not create empty future-phase directories early. Add them only when their
phase starts and keep the current boundary: CLI in `scripts/`, orchestration in
`src/services/`, reusable domain logic in focused `src/` modules.

## 9. Official Pipeline Commands

Official user-facing commands for the ingestion pipeline:

- Crawl raw legal corpus:

```bash
uv run python scripts/crawl_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --output data/raw \
  --report artifacts/reports/crawling/crawl_report.json \
  --only-status pending
```

- Audit raw corpus:

```bash
uv run python scripts/audit_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --output artifacts/reports/audit/raw_corpus_audit.json
```

- Clean and normalize corpus:

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report artifacts/reports/cleaning/cleaning_report.json \
  --write-txt \
  --audit
```

- Audit cleaning quality:

```bash
uv run python scripts/audit_cleaning_quality.py \
  --raw-dir data/raw \
  --interim-dir data/interim \
  --report-dir artifacts/reports/cleaning \
  --registry configs/laws/corpus_registry.yml
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

Phase 5 — Legal Hierarchy Parsing is the active engineering focus.

Key design constraints:

- Must consume `data/interim/{LAW_ID}/normalized.json` only.
- Must not mutate `data/raw/`.
- Must preserve `Phần / Chương / Mục / Điều / Khoản / Điểm` hierarchy.
- Must validate hierarchy before any chunking or embedding work.
- Must add focused parser unit tests covering at least three law templates and edge cases (Roman numerals, Vietnamese `đ`, mixed clause styles).

## 13. Out-of-Scope Reminders

These are explicitly deferred until their respective phase gates are met:

- Parent-child chunking
- Processed JSONL export
- Embedding / indexing (Qdrant)
- Neo4j graph construction
- Naive RAG baseline
- Advanced RAG (hybrid search, RRF, reranking)
- GraphRAG and multi-agent retrieval
- API / deployment (FastAPI)
- Fine-tuning / MLOps
- UI work
