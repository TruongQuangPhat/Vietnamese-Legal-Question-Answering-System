# VnLaw-QA

Vietnamese legal QA/RAG project focused on trusted legal-source ingestion,
deterministic preprocessing, hierarchy-preserving parsing, and citation-safe
retrieval.

VnLaw-QA is not a generic chatbot. The system is designed to answer Vietnamese
legal questions only from a trusted corpus, preserve traceability down to legal
units, and fall back safely when evidence is insufficient.

## Current Status

```text
Current phase: Phase 5 — Legal Hierarchy Parsing

Completed:
  Phase 0 — Project Setup and Principles
  Phase 1 — Legal Corpus Registry
  Phase 2 — Registry-driven Crawling
  Phase 3 — Raw Corpus Audit and Validation
  Phase 4 — Cleaning & Normalization

Next:
  Implement parser over data/interim/{LAW_ID}/normalized.json
  Preserve Phần / Chương / Mục / Điều / Khoản / Điểm
  Do not implement chunking or RAG before parser validation passes
```

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

## Legal Accuracy Rules

- Default trusted source: `https://thuvienphapluat.vn`.
- Prefer VBHN consolidated legal documents when available.
- Preserve source traceability from raw HTML to final citations.
- Preserve legal hierarchy: `Phần / Chương / Mục / Điều / Khoản / Điểm`.
- Do not mutate `data/raw/`; derived artifacts go under `data/interim/`,
  `data/processed/`, while generated reports go under phase-specific
  `artifacts/reports/<phase>/` directories.
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
│   ├── interim/      # normalized artifacts and future hierarchy outputs
│   ├── processed/    # future JSONL chunks
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
│   ├── processing/   # future parser/chunking domain logic
│   ├── indexing/     # future indexing logic
│   ├── retrieval/    # future retrieval logic
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
│ CURRENT NEXT PHASE           │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Phase 6                      │
│ Parent-child Chunking        │
│ data/interim/*/chunks.jsonl  │
│ PLANNED                      │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Later Phases                 │
│ Embedding → Naive RAG        │
│ → Advanced RAG → GraphRAG    │
│ PLANNED                      │
└──────────────────────────────┘
```

## Current Executable Pipeline

The currently implemented executable path runs from registry and raw artifacts
through Cleaning & Normalization:

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
│ 6. Quality Reports                         │
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

## Phase 5 Target Pipeline

Phase 5 should parse hierarchy only. It should not chunk or embed yet.

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

Recommended first validation laws:

```text
BLDS_2015
BLHS_VBHN
LDD_VBHN
LTTHC
LVL_2025
LANM_2025
LHNGD_VBHN
LTATGT_VBHN
```

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
| `docs/parent_child_chunking.md` | Future parent-child chunking design |
| `docs/processed_jsonl.md` | Future processed JSONL schema |
| `docs/evaluation.md` | Future evaluation strategy |

## Development Boundaries

Do not do yet:

- Do not implement parent-child chunking before parser validation.
- Do not implement processed JSONL export before chunking validation.
- Do not implement embedding/indexing before processed JSONL validation.
- Do not implement Naive RAG, Advanced RAG, or GraphRAG yet.
- Do not mutate `data/raw/`.
- Do not commit credentials, local provider tokens, `.env`, or machine-specific
  config.

## Security Note

Provider credentials must live outside tracked files. Use an untracked local
environment file or shell environment variables for secrets. If a token was ever
committed, remove it from the repository and rotate it before merging.
