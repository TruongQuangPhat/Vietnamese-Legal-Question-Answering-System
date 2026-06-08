---
name: vnlaw-project-structure
description: Use when creating, reorganizing, reviewing, or enforcing the VnLaw-QA repository layout, module responsibilities, and Claude Code project boundaries.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# Project Structure Skill

Use this skill to enforce repository organization and module boundaries.

Current status: Phases 0-6 are complete and hardened. Phase 6 Parent-child
Chunking produced `data/processed/legal_chunks.jsonl`; Phase 7 Processed Chunk Validation & Embedding Readiness
Validation is next. Phase 8+ files listed below are placement guidance unless
they already exist in the repository.

## Canonical Layout

```text
VnLaw-QA/
├── configs/                     # YAML configuration (non-secret)
│   ├── laws/                    # Corpus registry and legal configs
│   │   └── corpus_registry.yml
│   ├── sources/
│   ├── ingestion/
│   ├── processing/
│   ├── indexing/
│   ├── retrieval/
│   ├── generation/
│   └── evaluation/
├── data/                        # All data artifacts
│   ├── raw/                     # Immutable crawled HTML + metadata
│   ├── interim/                 # Normalized JSON + cleaned text
│   ├── processed/               # Chunked / index-ready corpus
│   ├── indexes/                 # Retrieval indexes
│   └── eval/                    # Evaluation datasets
├── artifacts/                   # Generated outputs (not committed)
│   ├── reports/                 # Phase reports
│   │   ├── crawling/
│   │   ├── audit/
│   │   ├── cleaning/
│   │   ├── parsing/
│   │   ├── chunking/
│   │   ├── indexing/
│   │   ├── retrieval/
│   │   ├── generation/
│   │   └── evaluation/
│   ├── traces/                  # Execution traces
│   │   ├── crawling/
│   │   ├── audit/
│   │   ├── cleaning/
│   │   ├── parsing/
│   │   ├── retrieval/
│   │   └── generation/
│   ├── runs/                    # Experiment / benchmark runs
│   │   ├── experiments/
│   │   ├── benchmarks/
│   │   └── evaluations/
│   ├── metrics/                 # Computed metrics
│   │   ├── indexing/
│   │   ├── retrieval/
│   │   ├── generation/
│   │   └── evaluation/
│   └── logs/
├── src/                         # Production source code
│   ├── __init__.py
│   ├── core/                    # Config, exceptions, logging
│   │   ├── config.py
│   │   └── exceptions.py
│   ├── ingestion/               # Phase 1-4: crawl, audit, clean
│   │   ├── crawler.py
│   │   ├── audit.py
│   │   ├── cleaning.py
│   │   ├── cleaning_diagnostics.py
│   │   ├── models.py
│   │   ├── registry.py
│   │   ├── selector.py
│   │   ├── storage.py
│   │   └── rate_limiter.py
│   ├── processing/              # Phase 5-6 implemented; Phase 7 planned
│   │   ├── normalized_input.py
│   │   ├── legal_heading_recognizer.py
│   │   ├── legal_span_segmenter.py
│   │   ├── legal_hierarchy_builder.py
│   │   ├── legal_hierarchy_models.py
│   │   ├── legal_tree_validator.py
│   │   ├── legal_parser.py
│   │   └── legal_chunk*.py      # Phase 6 chunking modules
│   ├── indexing/                # Phase 8: embedding, Qdrant
│   ├── retrieval/               # Phase 9-10: retrieval, reranking
│   ├── generation/              # Phase 9-11: LLM, prompts, answers
│   ├── services/                # Orchestration layer (all phases)
│   │   ├── crawl_service.py
│   │   ├── raw_audit_service.py
│   │   ├── cleaning_service.py
│   │   ├── cleaning_quality_audit_service.py
│   │   ├── legal_parsing_service.py
│   │   ├── chunking_service.py  # Phase 6 orchestration
│   │   └── ...                  # Phase 7+ services added only when started
│   ├── api/                     # Phase 13: FastAPI
│   ├── evaluation/              # Phase 12: RAGAS, metrics
│   ├── monitoring/              # Phase 14: monitoring
│   └── security/                # Phase 14: security
├── scripts/                     # CLI entrypoints
│   ├── crawl_raw_corpus.py
│   ├── audit_raw_corpus.py
│   ├── clean_raw_corpus.py
│   ├── audit_cleaning_quality.py
│   ├── parse_legal_hierarchy.py
│   ├── chunk_legal_corpus.py    # Phase 6 CLI
│   └── ...                      # Phase 7+ scripts added only when started
├── tests/                       # Test suite
│   ├── __init__.py
│   ├── unit/                    # Unit tests
│   │   ├── ingestion/
│   │   ├── processing/
│   │   ├── services/
│   │   └── ...
│   ├── integration/             # Integration tests
│   ├── regression/              # Regression tests
│   └── fixtures/                # Test data
├── docs/                        # Documentation
│   ├── project_phase_journal.md
│   ├── end_to_end_pipeline.md
│   ├── corpus_registry.md
│   ├── project_setup.md
│   ├── raw_data_crawling.md
│   ├── raw_corpus_audit.md
│   ├── cleaning_normalization.md
│   ├── legal_parsing.md
│   ├── parent_child_chunking.md
│   ├── processed_jsonl.md
│   ├── embedding_indexing.md
│   ├── naive_rag.md
│   ├── advanced_rag.md
│   ├── graphrag_agents.md
│   ├── evaluation.md
│   ├── api_deployment.md
│   └── mlops_maintenance.md
├── docker/                      # Docker configs
├── deployment/                  # Deployment configs
├── monitoring/                  # Monitoring configs
├── .github/workflows/           # CI/CD
├── pyproject.toml
├── CLAUDE.md
├── PROJECT_CONTEXT.md
├── README.md
└── .env.example
```

## Data Directory Contract

```text
data/raw/{law_id}/latest/main.html       # Crawled HTML (immutable)
data/raw/{law_id}/latest/metadata.json   # Crawl metadata (immutable)
data/interim/{law_id}/normalized.json    # Cleaned + normalized text
data/interim/{law_id}/cleaned.txt        # Optional debug artifact
data/interim/{law_id}/hierarchy.json     # Parsed legal hierarchy (Phase 5)
data/processed/legal_chunks.jsonl        # Validated Phase 6 chunk corpus
data/indexes/                            # Qdrant indexes (Phase 8)
data/eval/                               # Evaluation datasets (Phase 12)
```

## Module Responsibilities

### `src/core/`

```text
settings (Pydantic V2 BaseSettings)
custom exceptions (VnLawError hierarchy)
structured logging
shared domain types
```

### `src/ingestion/` (Phase 1-4)

```text
registry    → corpus registry YAML loading + validation
crawler     → async HTTP crawling with rate limiting
audit       → raw artifact quality validation
cleaning    → HTML extraction, Unicode normalization, legal text cleaning
storage     → raw artifact file management
selector    → crawl target filtering
models      → ingestion Pydantic models
```

### `src/processing/` (Phase 5-7)

```text
normalized_input              → parser input validation
legal_heading_recognizer      → regex-based heading detection
legal_span_segmenter          → heading-to-span conversion
legal_hierarchy_builder       → tree construction from segments
legal_hierarchy_models        → Pydantic models for hierarchy nodes
legal_tree_validator          → tree integrity validation
legal_parser                  → per-document parser facade
future chunk_models           → Pydantic models for legal chunks
future legal_chunker          → hierarchy-to-chunk conversion
future processed_jsonl_writer → JSONL output + validation
```

### `src/services/` (All phases - orchestration)

```text
crawl_service                  → crawl pipeline orchestration
raw_audit_service              → audit pipeline orchestration
cleaning_service               → cleaning pipeline orchestration
cleaning_quality_audit_service → cleaning diagnostics
legal_parsing_service          → parsing pipeline orchestration
future chunking_service        → chunking pipeline orchestration
future processed_jsonl_service → JSONL export + validation
```

### `src/indexing/` (Phase 8)

```text
embedder    → BGE-M3 dense+sparse embedding
vector_store → Qdrant collection management
```

### `src/retrieval/` (Phase 9-10)

```text
vector_store  → Qdrant hybrid search
reranker      → cross-encoder reranking
filters       → metadata + time-aware filtering
confidence    → confidence scoring
```

### `src/generation/` (Phase 9-11)

```text
llm_client      → provider abstraction (Anthropic, OpenAI, vLLM)
prompts         → legal QA prompt templates
context_packer  → evidence packet assembly
citation_validator → citation integrity checks
answer_formatter  → structured answer output
fallback_policy   → low-confidence fallback
```

### `src/agents/` (Phase 11)

```text
router          → intent classification
vector_explorer → Qdrant evidence retrieval
graph_explorer  → Neo4j traversal
orchestrator    → multi-agent evidence merging
```

### `src/api/` (Phase 13)

```text
main.py        → FastAPI app factory
dependencies.py → DI container
schemas.py     → request/response Pydantic models
routes/        → endpoint handlers
  qa.py
  health.py
  admin.py
```

### `src/evaluation/` (Phase 12)

```text
ragas_evaluator  → RAGAS metrics
citation_evaluator → legal citation metrics
golden_loader    → golden QA dataset loading
```

### `src/monitoring/` / `src/security/` (Phase 14)

```text
monitoring → metrics, tracing, alerting
security   → PII redaction, audit logging
```

## Phase-to-Module Mapping

```text
Phase 0  Setup           → pyproject.toml, CLAUDE.md, PROJECT_CONTEXT.md
Phase 1  Registry        → configs/laws/, src/ingestion/registry.py
Phase 2  Crawling        → src/ingestion/crawler.py, scripts/crawl_raw_corpus.py
Phase 3  Audit           → src/ingestion/audit.py, scripts/audit_raw_corpus.py
Phase 4  Cleaning        → src/ingestion/cleaning.py, scripts/clean_raw_corpus.py
Phase 5  Parsing         → src/processing/, scripts/parse_legal_hierarchy.py
Phase 6  Chunking        → src/processing/chunk_models.py, legal_chunker.py
                            src/services/chunking_service.py, scripts/chunk_legal_corpus.py
Phase 7  JSONL           → src/processing/processed_jsonl_writer.py
                            src/services/processed_jsonl_service.py
Phase 8  Indexing        → src/indexing/, scripts/build_embedding_index.py
Phase 9  Naive RAG       → src/retrieval/, src/generation/, src/api/
Phase 10 Advanced RAG   → src/retrieval/ (hybrid, RRF, reranker)
Phase 11 GraphRAG        → src/agents/, src/retrieval/graph_store.py
Phase 12 Evaluation      → src/evaluation/, tests/evaluation/
Phase 13 API             → src/api/, deployment/
Phase 14 MLOps           → src/monitoring/, src/security/, docker/
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

Tests mirror source modules:

```text
tests/unit/ingestion/       → src/ingestion/
tests/unit/processing/      → src/processing/
tests/unit/services/        → src/services/
tests/unit/indexing/        → src/indexing/
tests/unit/retrieval/       → src/retrieval/
tests/unit/generation/      → src/generation/
tests/unit/agents/          → src/agents/
tests/unit/api/             → src/api/
tests/unit/evaluation/      → src/evaluation/
tests/integration/
tests/regression/
tests/fixtures/
```

## CLI Pattern

All scripts follow the same pattern:

```text
scripts/{phase}_*.py
  ├── argparse CLI (--input-dir, --output-dir, --report, --law-ids, --verbose)
  ├── calls service layer
  ├── prints terminal summary
  └── returns exit code (0=success, 1=failure, 2=warning, 3=service error)
```

Entry point pattern:

```python
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def main(argv: list[str] | None = None) -> int:
    ...

if __name__ == "__main__":
    raise SystemExit(main())
```

## Branch Naming

```text
feature/data-crawling           done
feature/raw-corpus-audit        done
feature/cleaning-normalization  done
feature/legal-parser-chunking   current
feature/processed-jsonl         planned
feature/embedding-indexing      future
feature/naive-rag               future
feature/advanced-rag            future
feature/graphrag-agents         future
feature/evaluation              future
feature/api-deployment          future
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
- Do not add implementation logic to scaffolded future-phase directories before their phase starts.
