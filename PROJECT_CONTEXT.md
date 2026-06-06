# VnLaw-QA Project Context

This file is intended to help Claude Code, Codex, or any future AI coding assistant quickly understand the current project state before making changes.

## 1. Project Goal

VnLaw-QA is a Vietnamese Legal QA/RAG system. It is not a generic chatbot.

### Architecture
- `scripts/` = CLI entrypoints (parse arguments, call services, print results)
- `src/services/` = pipeline orchestration (coordinate phase execution, build reports)
- `src/ingestion/` = reusable domain logic (crawler, audit, cleaning, storage)

The system must retrieve, process, and answer questions based on Vietnamese legal documents while preserving legal structure, source traceability, and citation integrity. The long-term goal is to build a reliable Legal RAG pipeline that can answer Vietnamese legal questions with grounded evidence, explicit citations, and safe fallback behavior when evidence is insufficient.

The project pipeline is organized as:

```text
Corpus Registry
→ Registry-driven Crawling
→ Raw Corpus Audit
→ Cleaning / Normalization
→ Legal Hierarchy Parsing
→ Parent-child Chunking
→ Processed JSONL Validation
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
- The registry-driven crawler has been implemented.
- The crawling phase has completed successfully.
- The registry contains 52 legal document entries.
- 52/52 legal documents have been crawled successfully.
- Raw artifacts are stored under `data/raw/`.
- Raw Corpus Audit & Validation has been implemented.
- **Phase 4 — Cleaning & Normalization is complete/gate-ready.**
- The cleaned corpus has 52/52 `normalized.json` artifacts and 52/52 optional
  `cleaned.txt` debug artifacts under `data/interim/`.
- Cleaner output uses `cleaner_version` `v0.8.0`.
- Encoded TVPL footer/watermark artifacts are removed from cleaned outputs.
- Article metrics are explicit: `article_reference_count` counts all `Điều N`
  mentions, while `article_heading_count` and `max_heading_article_number`
  describe real article headings.
- Remaining duplicate-style flags such as BLHS_VBHN are diagnostic/semantic
  concerns, not cleaning blockers unless extraction duplication is proven.
- **Phase 5 — Legal Hierarchy Parsing is complete.**
- The parser generated 52/52 official hierarchy artifacts under
  `data/interim/{LAW_ID}/hierarchy.json`.
- The official parsing report is
  `artifacts/reports/parsing/legal_parsing_report.json`.
- The full-corpus Phase 5 run completed with 7 successes, 45 successes with
  warnings, and 0 failures. Remaining warnings are non-fatal parser caveats
  for Phase 6 review.
- The next engineering phase is **Phase 6 — Parent-child Chunking**.

## 4. Implemented Phases

### Phase 0 — Project Setup and Principles

Implemented.

Relevant files:

- `pyproject.toml`
- `CLAUDE.md`
- `PROJECT_CONTEXT.md`
- `.env.example`
- `docs/project_setup.md`

### Phase 1 — Legal Corpus Registry

Implemented.

Relevant files:

- `configs/laws/corpus_registry.yml`
- `docs/corpus_registry.md`

The registry is the source of truth for the legal corpus. It defines each legal document using metadata such as `law_id`, `name`, `tier`, `group`, `domain_tags`, `source_domain`, `source_type`, `url`, `crawl_status`, `priority`, and `notes`.

### Phase 2 — Registry-driven Crawling

Implemented.

Relevant files:

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

Implemented.

Relevant files:

- `src/ingestion/audit.py`
- `scripts/audit_raw_corpus.py`
- `tests/unit/ingestion/test_audit.py`
- `docs/raw_corpus_audit.md`
- `artifacts/reports/audit/raw_corpus_audit.json`

This phase validates that crawled raw artifacts are complete, readable, not blocked/error pages, and suitable for Cleaning & Normalization.

### Phase 4 — Cleaning & Normalization

Implemented and gate-ready.

Relevant files:

- `src/ingestion/cleaning.py`
- `src/services/cleaning_service.py`
- `scripts/clean_raw_corpus.py`
- `src/ingestion/cleaning_diagnostics.py`
- `src/services/cleaning_quality_audit_service.py`
- `scripts/audit_cleaning_quality.py`
- `tests/unit/ingestion/test_cleaning.py`
- `docs/cleaning_normalization.md`
- `data/interim/`
- `artifacts/reports/cleaning/cleaning_report.json`
- `artifacts/reports/cleaning/cleaning_quality_audit.json`

The full 52-law corpus cleans successfully with no warning artifacts, failed
artifacts, suspiciously short outputs, or missing article markers. Cleaning
preserves legal text structure for the Legal Hierarchy Parser and removes known
TVPL encoded footer/watermark artifacts.

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
- `tests/unit/services/`
- `docs/legal_parsing.md`
- `data/interim/{LAW_ID}/hierarchy.json`
- `artifacts/reports/parsing/legal_parsing_report.json`

The parser consumes `data/interim/{LAW_ID}/normalized.json`, preserves exact
offsets into `normalized_text`, creates a root Law node plus flat hierarchy
nodes for Part, Chapter, Section, Article, Clause, and Point, and validates the
tree before writing generated artifacts. It supports titleless Article headings
such as `Điều 1.` and excludes source-law note tails from the main hierarchy.

## 5. Current Phase

Current phase:

```text
Phase 6 — Parent-child Chunking
```

Goal:

Create validated parent-child chunks from the parsed legal hierarchy. Child
units should be Clause or Point where available, with Article text preserved as
parent context for downstream retrieval and generation.

This phase should consume `data/interim/{LAW_ID}/hierarchy.json`. It should not
jump directly to embedding, RAG, Advanced RAG, or GraphRAG.

Expected outputs:

```text
data/processed/legal_chunks.jsonl
artifacts/reports/chunking/
```

Key requirements:

- Read hierarchy artifacts from `data/interim/`.
- Do not mutate `data/raw/`.
- Do not rewrite Phase 5 parsing unless a chunking-blocking parser defect is
  proven.
- Preserve source traceability from hierarchy node metadata and offsets.
- Use legal hierarchy instead of arbitrary token/character windows.
- Validate chunks before any embedding or retrieval work.
- Add focused unit tests.
- Put parser domain logic under `src/processing/`.
- Put chunking orchestration/report building under `src/services/`.
- Put chunking CLI entrypoint under `scripts/`.
- Put chunking unit tests under `tests/unit/processing/`.

Important Vietnamese legal formatting note:

Vietnamese legal documents often do not literally write the words `Khoản` and `Điểm` in the body. Clauses are commonly represented by numbered lines such as `1.`, `2.`, `3.`, and points are commonly represented by lettered labels such as `a)`, `b)`, `c)`. Cleaning must preserve these patterns for the parser.

## 6. Next Immediate Tasks

1. Create or use the branch `feature/legal-parser-chunking`.
2. Design parent-child chunking over `hierarchy.json` inputs.
3. Use Clause or Point as child units where available.
4. Preserve Article text as parent context.
5. Generate processed JSONL only after chunk schema tests pass.
6. Add chunking unit tests before any indexing implementation.
7. Validate chunk correctness on known complex laws such as BLDS_2015,
   BLHS_VBHN, LDD_VBHN, LTTHC, and LVL_2025.

## 7. Do Not Do Yet

- Do not implement Parent-child Chunking until hierarchy parsing passes its
  validation gate.
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
  output: data/processed/
  report: artifacts/reports/chunking/

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
    --report artifacts/reports/cleaning/cleaning_report.json
  ```

## 10. Development Commands

Environment setup:

```bash
uv sync
```

Run tests:

```bash
uv run pytest
```

Run linting:

```bash
uv run ruff check .
```

Inspect crawler CLI (internal/package):

```bash
uv run python scripts/crawl_raw_corpus.py --help
```

Run raw corpus audit:

```bash
uv run python scripts/audit_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --output artifacts/reports/audit/raw_corpus_audit.json
```

Run Cleaning & Normalization:

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report artifacts/reports/cleaning/cleaning_report.json
```

Optional debug text output:

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report artifacts/reports/cleaning/cleaning_report.json \
  --write-txt
```

Focused cleaning tests:

```bash
uv run pytest tests/unit/ingestion/test_cleaning.py -v
```

## 10. Documentation Map

- `PROJECT_CONTEXT.md` gives the current project state and current phase.
- `CLAUDE.md` gives coding, workflow, and assistant rules.
- `docs/end_to_end_pipeline.md` gives the full roadmap.
- `docs/project_phase_journal.md` is the chronological project notebook for
  completed phases, pipeline decisions, and validation gates.
- `docs/raw_data_crawling.md` explains Phase 2 raw data crawling in detail.
- `docs/raw_corpus_audit.md` explains the raw audit phase.
- `docs/cleaning_normalization.md` explains the completed Cleaning & Normalization phase.
- `docs/legal_parsing.md` explains the current Legal Hierarchy Parsing phase.
- `docs/parent_child_chunking.md` explains the planned Parent-child Chunking phase.
- `docs/processed_jsonl.md` explains the planned processed JSONL schema and validation phase.
- `docs/evaluation.md` explains the future evaluation strategy.

## 11. Branch Roadmap

```text
feature/data-crawling                done
feature/raw-corpus-audit             done
feature/cleaning-normalization       done
feature/legal-parser-chunking        current
feature/processed-jsonl-validation   planned
feature/embedding-indexing           future
feature/naive-rag                    future
feature/advanced-rag                 future
feature/graphrag-agents              future
feature/evaluation                   future
feature/api-deployment               future
```

Branch guidance:

- Keep branches small and phase-focused.
- Each branch should pass its validation gate before merging.
- Do not mix cleaning, parsing, chunking, and RAG in the same branch.
- Documentation should be updated together with each phase implementation.

## 12. Current Phase Validation Gate

The Cleaning & Normalization phase has passed with:

```text
52/52 valid audited artifacts produce normalized.json
52/52 optional cleaned.txt debug artifacts were generated in final validation
normalized_text is UTF-8 readable
article markers and Article 1 headings are preserved
article references and real article headings are separately reported
numbered clause patterns are preserved when present
point label patterns are preserved when present
known encoded TVPL watermark/footer artifacts are removed
artifacts/reports/cleaning/cleaning_report.json is generated with no critical failures
```

Legal Hierarchy Parsing may start next. Do not proceed to chunking, embedding,
RAG, Advanced RAG, or GraphRAG until parser output passes its own validation
gate.

## 13. Notes for Future AI Assistants

Before making changes:

1. Read `PROJECT_CONTEXT.md`.
2. Read `CLAUDE.md`.
3. Read the relevant phase documentation under `docs/`.
4. Inspect existing code patterns in `src/ingestion/`, `scripts/`, and `tests/unit/ingestion/`.
5. Do not scan large raw directories recursively.
6. Do not read all raw HTML files manually.
7. Do not implement future phases early.
8. Keep source traceability and legal hierarchy preservation as first-class requirements.
