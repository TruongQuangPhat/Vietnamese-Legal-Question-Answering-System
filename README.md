# VnLaw-QA

Vietnamese legal QA/RAG project focused on trusted legal-source ingestion,
deterministic preprocessing, hierarchy-preserving parsing, and citation-safe
retrieval.

VnLaw-QA is not a generic chatbot. The system is designed to answer Vietnamese
legal questions only from a trusted corpus, preserve traceability down to legal
units, and fall back safely when evidence is insufficient.

## Current Status

```text
Current phase: Phase 9C.1 complete — reviewed generation evaluation expanded

Completed:
  Phase 0 — Project Setup and Principles
  Phase 1 — Legal Corpus Registry
  Phase 2 — Registry-driven Crawling
  Phase 3 — Raw Corpus Audit and Validation
  Phase 4 — Cleaning & Normalization
  Phase 5 — Legal Hierarchy Parsing
  Phase 6 — Parent-child Chunking
  Phase 7 — Processed Chunk Validation & Embedding Readiness
  Phase 7.5 — LLM-assisted corpus audit
  Phase 8 — BGE-M3 Embedding & Qdrant Indexing Foundation
  Phase 9A — Dense Retrieval Baseline
  Phase 9B — Fallback-aware Naive RAG Generation
  Phase 9C — Naive RAG Generation Evaluation & Safety Hardening
  Phase 9C.1 — Reviewed Generation Dataset Expansion

Next:
  Review repeatable Phase 9C generation evaluation reports
  Manually inspect semantic faithfulness separately from citation ID coverage
  Keep Phase 10 retrieval improvements separately scoped
```

Phase 9B loads `.env` automatically for `scripts/run_naive_rag.py`.
Non-secret OpenRouter defaults are stored in `configs/llm/openrouter.yml`;
`OPENROUTER_API_KEY` must exist only in the real environment or uncommitted
`.env`. Model precedence is `--model`, then `OPENROUTER_MODEL`, then YAML
`default_model`, then the emergency fallback. Exported environment values are
not overridden, and API keys must never be printed or written to reports.

Run the Phase 9C generation baseline with the lower-cost smoke model:

```bash
uv run --extra qdrant --extra embedding python scripts/evaluate_naive_rag_generation.py \
  --queries data/eval/manual_naive_rag_generation_queries.jsonl \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --provider openrouter \
  --model google/gemini-2.5-flash-lite \
  --output artifacts/reports/retrieval/naive_rag_generation_eval.json
```

The report validates citation ID integrity, not full semantic faithfulness.
The initial live baseline completed with status
`validated_generation_eval_passed`: 3/3 cases passed, citation ID coverage was
1.0, and no unknown/missing citation IDs or secret leaks were detected.

Phase 9C.1 expands the dataset to five unique cases using every currently
reviewed Phase 9A manual query. Three cases remain blocking; marriage
conditions and civil-rights protection are non-blocking manual-review cases
because their allowed retrieval decisions vary. The expanded report adds
caution-evidence and selection-warning review signals. These metrics do not
establish semantic faithfulness or legal correctness.

The expanded live run completed with `expanded_generation_eval_passed`: 5/5
cases passed, citation ID coverage was 1.0, no unknown/missing citation IDs or
secret leaks were detected, and two all-caution cases remain for human review.

Phase 4 is gate-ready:

```text
Registry entries:        52
Raw main.html files:     52
Raw metadata.json files: 52
normalized.json files:   52
cleaned.txt files:       52
Cleaning failures:       0
Warning artifacts:       0
Suspiciously short:      0
Missing article marker:  0
Cleaner version:         v0.8.0
```

Phase 5 is complete and hardened:

```text
Parsed documents:        52
Hierarchy outputs:       52
Parsing failures:        0
Parser version:          v0.1.0
Hierarchy output:        data/interim/{LAW_ID}/hierarchy.json
Parsing report:          artifacts/reports/parsing/legal_parsing_report.json
Remaining caveats:       non-fatal parser warnings documented in the report
```

Phase 6 is complete and validated:

```text
Chunk output:            data/processed/legal_chunks.jsonl
Chunking report:         artifacts/reports/chunking/chunking_report.json
Validated laws:          52/52
Success with warnings:   18
Chunking failures:       0
Total chunks:            40,389
Article chunks:          1,322
Clause chunks:           20,643
Point chunks:            18,424
Empty/repealed chunks:   180
Source-tail markers:     0 in text, 0 in parent_text
Max parent_text length:  14,481 chars
Duplicate chunk_id:      0
Bad JSONL lines:         0
Selection-rule issues:   0
Invariant issues:        0
Validation audit:        artifacts/reports/chunking/full_corpus_validation_report.json
```

Phase 6 preserves Article parent context in `parent_text` and uses
Article/Clause/Point hierarchy units instead of arbitrary token or character
windows. Phase 6 hardening removed VBHN/source-tail leakage from chunk
`text` and `parent_text`, and flags repealed placeholder chunks in metadata.
Phase 7 validates embedding-readiness. Phase 8 embeds only `text`; `parent_text` is stored as retrieval/LLM context payload.

Phase 7 is implementation-complete:

```text
Valid chunks:            40,389
Invalid chunks:          0
Errors:                  0
Warnings:                8,206
Embedding ready:         true
Readiness status:        ready_with_warnings
Validation report:       artifacts/reports/chunking/processed_jsonl_validation_report.json
```

Phase 7 warning follow-up W1-W3 and the Phase 7.5 read-only corpus audit are
complete. Phase 8 indexed all 40,389 chunks into Qdrant collection
`vnlaw_chunks_bgem3_v1_full` using normalized 1024-dimensional
`BAAI/bge-m3` dense vectors, named vector `dense`, cosine distance, and the
`text_only` template. All points were upserted successfully and full index
validation passed for schema, payload, vectors, filters, and retrieval sanity.
Phase 9A adds a read-only dense retrieval baseline that embeds Vietnamese
queries with BGE-M3, searches named vector `dense`, and returns typed
payload-backed legal evidence. It does not generate answers.

Official reports:

```text
artifacts/reports/indexing/20260611_bgem3_v1_full/
```

Qdrant storage and model caches are runtime state and must not be committed.

## Legal Accuracy Rules

- Default trusted source: `https://thuvienphapluat.vn`.
- Prefer VBHN consolidated legal documents when available.
- Preserve source traceability from raw HTML to final citations.
- Preserve legal hierarchy: `Phần / Chương / Mục / Điều / Khoản / Điểm`.
- Do not mutate `data/raw/`; derived artifacts go under `data/interim/`,
  `data/processed/`; official indexing reports go under
  `artifacts/reports/indexing/<run_id>/`.
- Do not use LLMs for deterministic legal preprocessing.
- Do not let future QA generation invent laws, articles, clauses, points, or
  citations.

Required final-answer citation style for future QA:

```text
According to Clause {X}, Article {Y}, {Law Name} {Year or Consolidated Version}: "{quoted legal content}"
```

## Repository Layout

Current scaffolded layout:

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
│   ├── raw/          # immutable crawl artifacts
│   ├── interim/      # normalized artifacts and hierarchy outputs
│   ├── processed/    # validated legal chunk JSONL
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
├── docs/
│   ├── project_phase_journal.md
│   ├── corpus_registry.md
│   ├── raw_corpus_audit.md
│   ├── cleaning_normalization.md
│   └── legal_parsing.md
├── scripts/
│   ├── crawl_raw_corpus.py
│   ├── audit_raw_corpus.py
│   ├── clean_raw_corpus.py
│   └── audit_cleaning_quality.py
├── src/
│   ├── core/
│   ├── ingestion/    # implemented ingestion and cleaning domain logic
│   ├── processing/   # implemented parser and chunking domain logic
│   ├── indexing/     # implemented embedding and Qdrant indexing logic
│   ├── retrieval/    # implemented dense retrieval baseline logic
│   ├── generation/   # future generation/RAG logic
│   ├── services/     # orchestration/reporting
│   ├── api/          # future API
│   ├── evaluation/   # future evaluation logic
│   ├── monitoring/   # future monitoring code
│   └── security/     # future security helpers
└── tests/
    ├── unit/
    │   ├── ingestion/
    │   ├── processing/
    │   ├── indexing/
    │   ├── retrieval/
    │   ├── generation/
    │   ├── services/
    │   └── evaluation/
    ├── integration/
    ├── regression/
    └── fixtures/
```

Target production layout, scaffolded with `.gitkeep` and implemented incrementally by phase:

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

The target layout is scaffolded now so future phases have stable homes. Empty
directories contain only `.gitkeep`; implementation logic is still phase-gated.

Architecture boundary:

```text
┌──────────────────────┐
│ scripts/             │
│ CLI, argparse, exit  │
│ codes, console text  │
└──────────┬───────────┘
           │ calls
           ▼
┌──────────────────────┐
│ src/services/        │
│ pipeline orchestration│
│ report composition   │
└──────────┬───────────┘
           │ uses
           ▼
┌──────────────────────┐
│ src/ingestion/       │
│ reusable domain      │
│ logic and models     │
└──────────────────────┘
```

## End-to-End Pipeline

Implemented and planned pipeline:

```text
┌──────────────────────────────┐
│ Phase 1                      │
│ Legal Corpus Registry        │
│ configs/laws/*.yml            │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Phase 2                      │
│ Registry-driven Crawling     │
│ data/raw/{LAW_ID}/latest/    │
│ artifacts/reports/crawling/  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Phase 3                      │
│ Raw Corpus Audit             │
│ artifacts/reports/audit/*.json    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Phase 4                      │
│ Cleaning & Normalization     │
│ data/interim/*/normalized.json│
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Phase 5                      │
│ Legal Hierarchy Parsing      │
│ data/interim/*/hierarchy.json│
│ COMPLETE AND HARDENED        │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Phase 6                      │
│ Parent-child Chunking        │
│ data/processed/legal_chunks.jsonl │
│ COMPLETE AND VALIDATED       │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Later Phases                 │
│ JSONL validation → Embedding │
│ → Naive RAG                  │
│ → Advanced RAG → GraphRAG    │
│ PLANNED                      │
└──────────────────────────────┘
```

## Current Executable Pipeline

The currently implemented executable path runs from registry and raw artifacts
through Legal Hierarchy Parsing:

```text
┌────────────────────────────────────────────┐
│ 1. Corpus Registry                         │
│ configs/laws/corpus_registry.yml            │
│ 52 law_id entries                          │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ 2. Raw Artifacts                           │
│ data/raw/{LAW_ID}/latest/main.html         │
│ data/raw/{LAW_ID}/latest/metadata.json     │
│ immutable legal evidence                   │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ 3. Raw Corpus Audit                        │
│ validate file presence, metadata, source,  │
│ size, encoding, error-page markers         │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ 4. Cleaning & Normalization                │
│ preferred TVPL selector                    │
│ block-aware HTML extraction                │
│ Unicode/whitespace normalization           │
│ legal body trimming                        │
│ safe line-fragment repair                  │
│ encoded artifact cleanup                   │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ 5. Normalized Artifacts                    │
│ data/interim/{LAW_ID}/normalized.json      │
│ data/interim/{LAW_ID}/cleaned.txt          │
│ cleaner_version: v0.8.0                    │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ 6. Legal Hierarchy Parsing                 │
│ data/interim/{LAW_ID}/hierarchy.json       │
│ artifacts/reports/parsing/legal_parsing_report.json │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ 7. Quality Reports                         │
│ artifacts/reports/cleaning/cleaning_report.json          │
│ artifacts/reports/cleaning/cleaning_quality_audit.json   │
│ artifacts/reports/cleaning/raw_vs_cleaning_comparison... │
└────────────────────────────────────────────┘
```

## Phase 4 Cleaning Logic Summary

The cleaner is intentionally conservative. It fixes known TVPL extraction
issues without changing legal meaning.

```text
┌──────────────────────────────┐
│ Raw HTML                     │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Preferred legal body selector│
│ e.g. #divContentDoc .content1│
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Block-aware extraction       │
│ block tags keep boundaries   │
│ inline tags join naturally   │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Start detection / trimming   │
│ preserve Article 1           │
│ skip amendment pre-body notes│
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Unicode normalization        │
│ NFC, NBSP, BOM, zero-width   │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Whitespace and fragment fix  │
│ preserve Điều / 1. / a)      │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Encoded TVPL artifact cleanup│
│ remove watermark/footer lines│
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Markers and metadata         │
│ refs vs headings clarified   │
└──────────────────────────────┘
```

Important marker fields in `normalized.json`:

```text
article_reference_count       all "Điều N" mentions, including references
article_heading_count         real article heading lines
max_heading_article_number    highest real heading number
has_heading_article_1         whether real Article 1 heading exists
heading_sequence_score        continuity score for real headings
```

Example:

```text
BLDS_2015:
  article_reference_count = 829
  article_heading_count = 689
  max_heading_article_number = 689
```

This means BLDS has 689 real article headings. The larger reference count is
expected because the law references other articles internally.

## Phase 5 Legal Hierarchy Parsing

Phase 5 parses hierarchy only. It does not chunk or embed.

```text
┌────────────────────────────────────────────┐
│ Input                                      │
│ data/interim/{LAW_ID}/normalized.json      │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Heading Recognizer                         │
│ Phần / Chương / Mục / Điều                 │
│ numbered clause lines: 1., 2., 3.          │
│ point labels: a), b), c)                   │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Span Segmenter                             │
│ assign text ranges to legal units          │
│ preserve source offsets where practical    │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Hierarchy Builder                          │
│ parent-child links                         │
│ Law → Part → Chapter → Section             │
│ → Article → Clause → Point                 │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Parser Validator                           │
│ no orphan nodes                            │
│ no impossible overlaps                     │
│ Article 1 and known max article preserved  │
│ parser report generated                    │
└────────────────────┬───────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────┐
│ Output                                     │
│ data/interim/{LAW_ID}/hierarchy.json       │
│ artifacts/reports/parsing/legal_parsing_report.json     │
└────────────────────────────────────────────┘
```

Official command:

```bash
uv run python scripts/parse_legal_hierarchy.py \
  --input-dir data/interim \
  --output-dir data/interim \
  --report artifacts/reports/parsing/legal_parsing_report.json \
  --overwrite \
  --verbose
```

The full corpus run completed with 52 total documents, 6 successes, 46
successes with warnings, and 0 failures. No validator failures, no RED audit
cases, no ORANGE audit cases, no source-tail leakage, no
AMBIGUOUS_CLAUSE_CANDIDATE warnings, and no POINT_LIKE_LINE_OUTSIDE_CLAUSE
warnings. Remaining non-fatal warnings (SOURCE_NOTE_EXCLUDED, EMPTY_ARTICLE_NODE,
NODE_ID_COLLISION_RESOLVED, ARTICLE_COUNT_MISMATCH, MAX_ARTICLE_NUMBER_MISMATCH)
are preserved in the parsing report for Phase 6 reference.

## Phase 6 Parent-child Chunking

Phase 6 chunks the validated legal hierarchy into a single corpus JSONL file.
It does not embed, index, retrieve, or generate answers.

```text
Input:   data/interim/{LAW_ID}/hierarchy.json
Output:  data/processed/legal_chunks.jsonl
Report:  artifacts/reports/chunking/chunking_report.json
Audit:   artifacts/reports/chunking/full_corpus_validation_report.json
```

Official command:

```bash
uv run python scripts/chunk_legal_corpus.py \
  --input-dir data/interim \
  --output data/processed/legal_chunks.jsonl \
  --report artifacts/reports/chunking/chunking_report.json \
  --overwrite \
  --verbose \
  --no-color
```

Result:

```text
34 laws succeeded
18 laws succeeded with warnings
0 failed laws
40,389 chunks
180 empty/repealed chunks flagged
0 source-tail markers in text
0 source-tail markers in parent_text
max parent_text length: 14,481 chars
0 bad JSONL lines
0 duplicate chunk IDs
0 selection-rule issues
0 chunk invariant issues
```

Chunk selection policy:

- Article without Clause/Point children -> article-level chunk.
- Clause without Point children -> clause-level chunk.
- Clause with Point children -> one point-level chunk per Point.
- `text` is the embedding unit.
- `parent_text` is the full Article context for downstream RAG.
- `metadata.is_empty_or_repealed` flags empty/repealed placeholders.
- `metadata.is_source_unit_repealed` flags repealed Article/Clause/Point units.

## Setup

Requirements:

- Python `>=3.11`
- `uv`

Install dependencies:

```bash
uv sync
```

Run the main ingestion unit tests:

```bash
uv run pytest tests/unit/ingestion -q
```

Run linting:

```bash
uv run ruff check .
```

## Official Commands

Validate processed chunks for a future controlled reindexing run:

```bash
uv run python scripts/validate_processed_jsonl.py \
  --input data/processed/legal_chunks.jsonl \
  --config configs/processing/processed_jsonl_validation.yml \
  --output /tmp/processed_jsonl_validation_report.json \
  --pretty
```

Use `--fail-on-warnings` in strict CI environments. Warning-only reports exit
with code 0 by default and code 2 in strict mode.

Inspect crawler:

```bash
uv run python scripts/crawl_raw_corpus.py --help
```

Crawl raw corpus:

```bash
uv run python scripts/crawl_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --output data/raw \
  --report artifacts/reports/crawling/crawl_report.json \
  --only-status pending
```

Audit raw corpus:

```bash
uv run python scripts/audit_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --output artifacts/reports/audit/raw_corpus_audit.json
```

Clean and normalize corpus:

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report artifacts/reports/cleaning/cleaning_report.json \
  --write-txt \
  --audit
```

Run cleaning diagnostics:

```bash
uv run python scripts/audit_cleaning_quality.py \
  --raw-dir data/raw \
  --interim-dir data/interim \
  --report-dir artifacts/reports/cleaning \
  --registry configs/laws/corpus_registry.yml
```

Focused cleaning tests:

```bash
uv run pytest tests/unit/ingestion/test_cleaning.py -v
```

All ingestion tests:

```bash
uv run pytest tests/unit/ingestion -q
```

## Data Artifacts

Raw artifacts:

```text
data/raw/{LAW_ID}/latest/main.html
data/raw/{LAW_ID}/latest/metadata.json
```

Normalized artifacts:

```text
data/interim/{LAW_ID}/normalized.json
data/interim/{LAW_ID}/cleaned.txt
```

Reports:

```text
artifacts/reports/crawling/crawl_report.json
artifacts/reports/audit/raw_corpus_audit.json
artifacts/reports/cleaning/cleaning_report.json
artifacts/reports/cleaning/cleaning_quality_audit.json
artifacts/reports/cleaning/raw_vs_cleaning_comparison.json
artifacts/reports/cleaning/html_pattern_audit.json
artifacts/reports/cleaning/selector_candidate_audit.json
artifacts/reports/cleaning/pattern_groups.json
```

## Documentation Map

| Document | Purpose |
|---|---|
| `PROJECT_CONTEXT.md` | Current project state and phase boundary |
| `AGENTS.md` | Codex workflow, safety, and project rules |
| `docs/project_phase_journal.md` | Chronological phase notebook and pipeline decisions |
| `docs/raw_data_crawling.md` | Detailed Phase 2 raw data crawling pipeline |
| `docs/corpus_registry.md` | Registry schema and trusted corpus rules |
| `docs/raw_corpus_audit.md` | Raw artifact audit gate |
| `docs/cleaning_normalization.md` | Cleaning pipeline and validation details |
| `docs/legal_parsing.md` | Phase 5 parser design |
| `docs/parent_child_chunking.md` | Implemented Phase 6 parent-child chunking design and command |
| `docs/processed_jsonl.md` | Phase 7 processed chunk validation & embedding-readiness notes |
| `docs/phase75_llm_corpus_audit.md` | Phase 7.5 semantic corpus audit and Phase 8 guardrails |
| `docs/phase7_warning_resolution_decision.md` | Final warning treatment and Phase 8 go/no-go decision |
| `docs/phase8_embedding_indexing_tracker.md` | Completed Phase 8 implementation, indexing, and validation record |
| `docs/embedding_indexing.md` | Phase 8 design background |
| `docs/phase9_retrieval_naive_rag_tracker.md` | Phase 9 retrieval and fallback-aware Naive RAG status |
| `docs/naive_rag.md` | Implemented dense retrieval and fallback-aware Naive RAG baseline |
| `docs/evaluation.md` | Future evaluation strategy |

## Development Boundaries

Do not do yet:

- Do not modify raw or interim corpus artifacts without explicit approval.
- Do not mutate `data/processed/legal_chunks.jsonl`.
- Do not commit Qdrant storage, model caches, or other runtime state.
- Do not bypass the evidence gate, implement Advanced RAG, or implement
  GraphRAG without a separately scoped task.
- Do not mutate `data/raw/`.
- Do not commit credentials, local provider tokens, `.env`, or machine-specific
  config.

## Security Note

Provider credentials must live outside tracked files. Use an untracked local
environment file or shell environment variables for secrets. If a token was ever
committed, remove it from the repository and rotate it before merging.
