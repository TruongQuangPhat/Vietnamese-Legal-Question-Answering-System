# VnLaw-QA Project Phase Journal

## 1. Purpose

This document is the detailed engineering journal for VnLaw-QA. It records
what each completed phase implemented, why the phase exists, how data moves
through the pipeline, which files own the logic, and what validation gates were
used before moving forward.

It replaces the previous crawling-only note. The registry-driven crawling
details are preserved under Phase 2, while later sections document the raw
audit and Cleaning & Normalization work completed so far.

VnLaw-QA is a Vietnamese legal QA/RAG project. The implementation order is
deliberate:

```text
Project setup
→ Corpus registry
→ Registry-driven crawling
→ Raw corpus audit
→ Cleaning & Normalization
→ Legal hierarchy parsing
→ Parent-child chunking
→ Processed JSONL validation
→ Embedding / indexing
→ Naive RAG
→ Advanced RAG
→ GraphRAG
→ Evaluation
→ API / deployment
```

Current status:

```text
Phase 0: Project setup and principles       complete
Phase 1: Legal corpus registry              complete
Phase 2: Registry-driven crawling           complete
Phase 3: Raw corpus audit and validation    complete
Phase 4: Cleaning & Normalization           complete / gate-ready
Phase 5: Legal hierarchy parsing            next
```

## 2. Cross-Phase Principles

The same engineering rules apply across all phases:

- Use `thuvienphapluat.vn` as the trusted source unless a new source is
  explicitly approved and documented.
- Prefer VBHN consolidated documents when available.
- Preserve traceability from every derived artifact back to raw source data.
- Never mutate `data/raw/`; write derived outputs to `data/interim/`,
  `data/processed/`, or `data/reports/`.
- Preserve Vietnamese legal hierarchy:
  `Phần / Chương / Mục / Điều / Khoản / Điểm`.
- Keep deterministic preprocessing before introducing LLM behavior.
- Validate each phase before moving to the next phase.
- Do not jump directly to embedding, RAG, Advanced RAG, or GraphRAG before the
  parser and chunker are reliable.

## 3. Repository Boundaries

The project follows a simple service/domain split:

```text
scripts/        CLI entrypoints, argparse, terminal summaries, exit codes
src/services/   orchestration and report building
src/ingestion/  reusable ingestion and cleaning domain logic
configs/laws/    registry and legal corpus configuration
data/raw/       immutable crawl artifacts
data/interim/   derived intermediate artifacts
data/reports/   audit and validation reports
docs/           phase notes, design docs, validation criteria
tests/          focused unit tests
```

This separation matters because the CLI should stay thin. Business logic lives
in `src/services/` or `src/ingestion/`, and tests should target the reusable
logic rather than terminal formatting.

## 4. Phase 0 — Project Setup and Principles

### Goal

Establish the project mission, working conventions, Python environment, and
documentation surfaces before implementing ingestion.

### Main Outputs

- `pyproject.toml`
- `.env.example`
- `PROJECT_CONTEXT.md`
- `AGENTS.md`
- `.codex/context/PROJECT_CONTEXT.md`
- `.agents/skills/`
- `docs/project_setup.md`

### Design Decisions

- Use Python 3.11+.
- Use `uv run` for project commands.
- Keep raw legal data separate from derived artifacts.
- Treat the system as legal research support, not a generic chatbot.
- Require citations and source traceability for downstream QA.

### Validation

The setup phase is considered complete when the repository has reproducible
commands, clear phase boundaries, and assistant/project instructions that stop
future work from skipping ahead.

## 5. Phase 1 — Legal Corpus Registry

### Goal

Define the trusted corpus before crawling. The registry is the source of truth
for which legal documents the system may fetch and process.

### Main Files

- `configs/laws/corpus_registry.yml`
- `src/ingestion/models.py`
- `src/ingestion/registry.py`
- `tests/unit/ingestion/test_models.py`
- `tests/unit/ingestion/test_registry.py`
- `docs/corpus_registry.md`

### Registry Contract

Each entry records:

```text
law_id
name
tier
group
domain_tags
status
source_domain
source_type
url
effective_date
expiry_date
crawl_status
priority
notes
```

The key engineering choice is stable `law_id` propagation. The same `law_id`
anchors:

```text
registry entry
→ data/raw/{LAW_ID}/
→ data/interim/{LAW_ID}/normalized.json
→ future hierarchy/chunk artifacts
→ future vector/graph payloads
→ final citations
```

### Current Result

- Registry contains 52 legal document entries.
- Trusted source policy is limited to `thuvienphapluat.vn`.
- The registry supports tier, group, priority, and crawl status filtering.

### Validation Gate

Phase 1 is valid when:

- all entries have unique `law_id`;
- required fields are present;
- source domains are trusted;
- URLs exist for crawlable entries;
- registry models load without validation errors.

## 6. Phase 2 — Registry-Driven Crawling

### Goal

Fetch raw legal artifacts from the approved registry and store them as immutable raw evidence under `data/raw/`. This phase is intentionally limited to trusted-source crawling, raw artifact persistence, and source metadata capture.

Detailed phase documentation:

- `docs/raw_data_crawling.md`

### Phase Boundary

Phase 2 does:

- load crawl targets from `configs/laws/corpus_registry.yml`;
- validate trusted `thuvienphapluat.vn` URLs;
- apply target filters and skip already-crawled artifacts;
- fetch raw HTML with rate limiting and retry handling;
- write `data/raw/{LAW_ID}/latest/main.html`;
- write `data/raw/{LAW_ID}/latest/metadata.json`;
- preserve raw artifacts for audit, cleaning, parsing, and future citation traceability.

Phase 2 does not audit legal content quality, clean HTML, normalize text, parse legal hierarchy, create chunks, or build retrieval indexes.

### Main Files

- `scripts/crawl_raw_corpus.py`
- `src/services/crawl_service.py`
- `src/ingestion/registry.py`
- `src/ingestion/selector.py`
- `src/ingestion/crawler.py`
- `src/ingestion/rate_limiter.py`
- `src/ingestion/storage.py`
- `src/ingestion/models.py`
- `tests/unit/ingestion/test_crawler.py`
- `tests/unit/ingestion/test_selector.py`
- `tests/unit/ingestion/test_storage.py`

### High-Level Pipeline

```text
corpus_registry.yml
→ CrawlTarget selection
→ trusted domain validation
→ rate-limited HTTP fetch
→ raw artifact storage
→ main.html + metadata.json
→ Raw Corpus Audit
```

### Current Result

- 52/52 registry entries were crawled successfully.
- 52 `data/raw/{LAW_ID}/latest/main.html` files exist.
- 52 `data/raw/{LAW_ID}/latest/metadata.json` files exist.
- Raw artifacts are treated as immutable legal evidence for downstream phases.

### Validation Gate

The crawling phase passes when:

- each registry law has a raw artifact directory;
- successful crawls have `main.html` and `metadata.json`;
- content hashes are recorded;
- source metadata points back to `thuvienphapluat.vn`;
- no downstream phase mutates raw artifacts.

Final Phase 2 gate evidence:

```text
registry entries:        52
latest/main.html files:  52
latest/metadata.json:    52
trusted source domain:   thuvienphapluat.vn
downstream raw mutation: none
```

## 7. Phase 3 — Raw Corpus Audit and Validation

### Goal

Verify that crawled artifacts are usable before cleaning. Crawl success alone is
not enough because an HTTP 200 page can still be an error page, blocked page, or
non-legal content.

### Main Files

- `scripts/audit_raw_corpus.py`
- `src/services/raw_audit_service.py`
- `src/ingestion/audit.py`
- `tests/unit/ingestion/test_audit.py`
- `docs/raw_corpus_audit.md`
- `data/reports/raw_corpus_audit.json`

### User-Facing Command

```bash
uv run python scripts/audit_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --output data/reports/raw_corpus_audit.json
```

### Audit Pipeline

```text
registry law ids
→ raw artifact scanner
→ metadata validator
→ HTML size/readability validator
→ error page detector
→ legal marker checker
→ raw_corpus_audit.json
```

### Checks

For every `LAW_ID`, the auditor verifies:

- `data/raw/{LAW_ID}/latest/main.html` exists;
- `data/raw/{LAW_ID}/latest/metadata.json` exists;
- metadata JSON is readable;
- metadata `law_id` matches the directory and registry;
- source URL/domain are traceable;
- HTML is readable and not suspiciously tiny;
- obvious error/captcha/login pages are flagged;
- basic Vietnamese legal markers are present.

### Why This Phase Matters

This phase protects cleaning and parsing from ingesting invalid evidence. If a
raw artifact is wrong, later normalized text and citations would be unreliable.

### Validation Gate

Phase 3 passes when:

- 52 registry entries are represented in raw artifacts;
- 52 raw artifacts are valid;
- no critical missing files or metadata mismatches remain;
- report output is written to `data/reports/raw_corpus_audit.json`.

## 8. Phase 4 — Cleaning & Normalization

### Goal

Convert audited raw HTML into deterministic normalized Vietnamese legal text
without parsing hierarchy yet.

The cleaner must remove obvious non-legal artifacts while preserving legal
structure markers needed by the parser:

```text
Phần
Chương
Mục
Điều
numbered clause lines: 1., 2., 3.
point labels: a), b), c)
```

### Main Files

- `scripts/clean_raw_corpus.py`
- `scripts/audit_cleaning_quality.py`
- `src/services/cleaning_service.py`
- `src/services/cleaning_quality_audit_service.py`
- `src/ingestion/cleaning.py`
- `src/ingestion/cleaning_diagnostics.py`
- `tests/unit/ingestion/test_cleaning.py`
- `docs/cleaning_normalization.md`
- `data/interim/{LAW_ID}/normalized.json`
- `data/interim/{LAW_ID}/cleaned.txt`
- `data/reports/cleaning_report.json`
- `data/reports/cleaning_quality_audit.json`

### User-Facing Commands

Clean corpus:

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report data/reports/cleaning_report.json \
  --write-txt \
  --audit
```

Run cleaning diagnostics:

```bash
uv run python scripts/audit_cleaning_quality.py \
  --raw-dir data/raw \
  --interim-dir data/interim \
  --report-dir data/reports \
  --registry configs/laws/corpus_registry.yml
```

### Cleaning Pipeline

```text
data/raw/{LAW_ID}/latest/main.html
metadata.json
→ raw artifact discovery
→ metadata loading
→ preferred TVPL content selection
→ block-aware HTML text extraction
→ legal body start trimming
→ Unicode normalization
→ conservative whitespace and line-fragment repair
→ encoded footer/watermark artifact removal
→ quality marker computation
→ normalized.json
→ optional cleaned.txt
→ cleaning_report.json
```

### Key Problems Found and Fixed

#### 8.1 Start Trimming Defects

Some documents had Article 1 near the beginning, but earlier logic sometimes
trimmed forward to a later amendment/source-law section.

Fix:

- prefer early real Article 1 evidence;
- avoid selecting late `Luật sửa đổi...` sections as body start;
- preserve official legal headers when keeping them is safer than trimming too
  aggressively.

Validated on cases such as:

```text
LANM_2025
LVL_2025
LNO_VBHN
LXD_VBHN
```

#### 8.2 Conservative Line-Fragment Repair

Raw extracted text included fragmented legal terms such as:

```text
Điều
32.

đ
iều

m
ục
```

Fix:

- repair safe fragments like `Điều\n32.` → `Điều 32.`;
- repair intra-word Vietnamese splits such as `đ\niều`, `m\nục`,
  `Vi\nệc`;
- preserve Article headings, clause boundaries, and point labels.

#### 8.3 Block-Aware HTML Extraction

TVPL legal body HTML often uses inline-heavy structures:

```html
<p>Qu<span>ốc</span> hội ban hành Luật.</p>
<p>Cơ quan, t<span>ổ</span><span> chức</span>, cá nhân.</p>
```

Using `get_text(separator="\n")` on inline-heavy nodes created artificial
newlines:

```text
Qu
ốc
t
ổ
chức
```

Fix:

- preserve line breaks for block elements such as `p`, `div`, `tr`, `td`,
  `table`, `li`, `h1`-`h6`;
- join inline elements such as `span`, `font`, `b`, `i`, `u`, `a` without
  artificial newlines;
- keep legal paragraph and heading boundaries parseable.

#### 8.4 Source-Law / Amendment Pre-Body Notes

Some VBHN documents started with unwanted source-law notes before the actual
main body:

```text
Luật số ... sửa đổi, bổ sung ...
Căn cứ Hiến pháp ...; Quốc hội ban hành Luật ...
Chương I
Điều 1. ...
```

Fix:

- recognize combined `Căn cứ Hiến pháp ...; Quốc hội ban hành Luật ...` lines
  as valid body starts;
- reject narrow amendment/source-law note patterns before the real body;
- preserve `Chương I` and `Điều 1`.

Validated on:

```text
LHNGD_VBHN
LTATGT_VBHN
```

#### 8.5 Encoded TVPL Footer / Watermark Artifacts

Some cleaned outputs contained encoded non-legal footer artifacts near the end:

```text
VABWAFAATABf...
LdABoAHUAdgBpAGUAbgBwAGgAYQBwAGwAdQBhAHQALgB2AG4A
```

Fix:

- remove standalone base64-like TVPL watermark/footer lines;
- preserve legal signatures such as `CHỦ TỊCH QUỐC HỘI ...`;
- preserve legal numbers, dates, law IDs, table codes, and abbreviations.

#### 8.6 Article Metric Clarity

The old metric name `article_count_estimate` was misleading because it counted
all `Điều N` mentions, including references.

Current marker fields:

```text
article_reference_count       all Điều N mentions, including references
article_heading_count         real article heading lines
max_heading_article_number    highest real article heading number
has_heading_article_1         whether real Article 1 heading exists
heading_sequence_score        continuity score for real headings
```

Compatibility fields may remain, but reports must not present
`article_count_estimate` as the number of actual articles.

Example:

```text
BLDS_2015:
article_reference_count = 829
article_heading_count = 689
max_heading_article_number = 689
```

This means BLDS has 689 real article headings, while cross-references raise the
reference count.

### Final Phase 4 Validation

Final tests:

```text
uv run pytest tests/unit/ingestion/test_cleaning.py -v  → 57 passed
uv run pytest tests/unit/ingestion -q                  → 159 passed
```

Final corpus metrics:

```text
registry entries:        52
raw main.html files:     52
raw metadata.json files: 52
normalized.json files:   52
cleaned.txt files:       52
successfully cleaned:    52
warning artifacts:       0
failed artifacts:        0
suspiciously short:      0
missing article marker:  0
```

Known historical cases are now valid:

```text
BLDS_2015       reaches Điều 689; article metrics clarified
LANM_2025       no longer suspiciously short; Article 1 preserved
LHNGD_VBHN      unwanted pre-body amendment note removed
LTATGT_VBHN     unwanted pre-body amendment note removed
BLHS_VBHN       duplicate-style repetition treated as non-blocking unless
                proven to be extraction duplication
```

Final decision:

```text
Phase 4 Cleaning & Normalization is complete/gate-ready.
```

## 9. Current Next Phase — Legal Hierarchy Parsing

The next phase should consume:

```text
data/interim/{LAW_ID}/normalized.json
```

The parser should produce:

```text
data/interim/{LAW_ID}/hierarchy.json
data/reports/legal_parsing_report.json
```

Parser responsibilities:

- detect `Phần`, `Chương`, `Mục`, `Điều`;
- map numbered lines to clauses when they belong under an Article;
- map lettered labels to points when they belong under a Clause;
- preserve offsets/source traceability where possible;
- avoid arbitrary token or character chunking;
- validate hierarchy before any chunking work starts.

Recommended first validation laws:

```text
BLDS_2015
BLHS_VBHN
LDD_VBHN
LTTHC
LVL_2025
LANM_2025
```

Do not proceed to Parent-child Chunking, embedding, RAG, Advanced RAG, or
GraphRAG until legal hierarchy parsing has its own validation gate.

## 10. Commands Reference

Official commands used through the completed phases:

```bash
uv run python scripts/crawl_raw_corpus.py --help
uv run python scripts/audit_raw_corpus.py --help
uv run python scripts/clean_raw_corpus.py --help
uv run python scripts/audit_cleaning_quality.py --help
uv run pytest tests/unit/ingestion -q
```

Completed full validation commands:

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report data/reports/cleaning_report.json \
  --write-txt \
  --audit

uv run python scripts/audit_cleaning_quality.py \
  --raw-dir data/raw \
  --interim-dir data/interim \
  --report-dir data/reports \
  --registry configs/laws/corpus_registry.yml
```

## 11. Related Documentation

| Document | Role |
|---|---|
| `PROJECT_CONTEXT.md` | Current project state and phase boundary |
| `AGENTS.md` | Codex workflow, safety, and project rules |
| `docs/corpus_registry.md` | Registry design and corpus metadata |
| `docs/raw_corpus_audit.md` | Raw artifact audit gate |
| `docs/cleaning_normalization.md` | Cleaning and normalization details |
| `docs/legal_parsing.md` | Planned/current legal hierarchy parser design |
| `docs/parent_child_chunking.md` | Future chunking design |
| `docs/processed_jsonl.md` | Future processed artifact schema |
| `docs/evaluation.md` | Future evaluation strategy |

## 12. Maintenance Notes

- Keep this journal factual. Do not document planned behavior as implemented.
- When a phase passes, record the validation command and gate evidence.
- Keep phase-specific deep dives in their own docs; use this file as the
  chronological project notebook.
- If a later parser issue exposes a real cleaning defect, fix cleaning with a
  focused regression test and update Phase 4 notes here.
