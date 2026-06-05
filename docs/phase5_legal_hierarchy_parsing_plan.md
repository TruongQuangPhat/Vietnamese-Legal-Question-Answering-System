# Phase 5 Legal Hierarchy Parsing Plan

## Purpose

This document is the approved implementation plan for Phase 5 of VnLaw-QA:
Legal Hierarchy Parsing. It is self-contained so a fresh Codex session can
continue implementation without relying on prior conversation context.

Phase 5 must convert normalized Vietnamese legal text into a deterministic,
validated, traceable hierarchy:

```text
Law
-> Phần
-> Chương
-> Mục
-> Điều
-> Khoản
-> Điểm
```

Intermediate hierarchy levels may be absent. The parser must preserve legal
meaning, exact source offsets, and future citation traceability. It must not
implement parent-child chunking, processed JSONL export, embedding, retrieval,
generation, Advanced RAG, GraphRAG, API, deployment, or any later phase.

## A. Repository Understanding

### Current Project Status

VnLaw-QA is a Vietnamese Legal QA/RAG system, not a generic chatbot. It must
answer only from trusted legal corpus evidence and preserve traceability from
raw legal source to normalized text, parsed hierarchy nodes, future chunks,
retrieval results, and final citations.

Current completed phases:

```text
Phase 0 - Project Setup and Principles       completed
Phase 1 - Legal Corpus Registry              completed
Phase 2 - Registry-driven Crawling           completed
Phase 3 - Raw Corpus Audit and Validation    completed
Phase 4 - Cleaning & Normalization           completed / gate-ready
Production structure scaffold                completed
Artifact/report migration                    completed
Docs/skills/context synchronization          completed
Phase 5 - Legal Hierarchy Parsing            current next phase
```

Phase 5 has not been implemented yet.

The intended pipeline remains:

```text
Corpus Registry
-> Registry-driven Crawling
-> Raw Corpus Audit
-> Cleaning & Normalization
-> Legal Hierarchy Parsing
-> Parent-child Chunking
-> Processed JSONL Validation
-> Embedding / Indexing
-> Naive RAG
-> Advanced RAG
-> GraphRAG
-> Evaluation
-> API / Deployment
-> MLOps / Maintenance
```

### Actual Repository Patterns

Existing implementation conventions to reuse:

- `scripts/` contains thin CLI entrypoints with `argparse`, terminal summaries,
  and exit codes.
- `src/services/` contains orchestration, batch coordination, and report
  construction/writing.
- `src/ingestion/` contains deterministic reusable domain logic.
- `src/processing/` is scaffolded and currently contains no Phase 5 logic.
- Pydantic V2 is used for boundary schemas, especially registry and metadata
  models.
- Dataclasses are used for internal phase records where appropriate.
- JSON reports are written as UTF-8 with `ensure_ascii=False` and indentation.
- Public classes/functions/methods need complete type hints and Google-style
  docstrings.
- Generated data and reports are ignored by git; committed tests must use small
  fixtures rather than depending unconditionally on local ignored corpus data.

Current Phase 5 scaffolding:

```text
src/processing/.gitkeep
tests/unit/processing/.gitkeep
tests/unit/services/.gitkeep
tests/integration/.gitkeep
tests/fixtures/.gitkeep
artifacts/reports/parsing/.gitkeep
```

### Authoritative Phase 5 Input Contract

The authoritative parser input is:

```text
data/interim/{LAW_ID}/normalized.json
```

The parser must operate on exactly:

```python
normalized_text = normalized_artifact["normalized_text"]
```

The human-readable diagnostic/reference artifact is:

```text
data/interim/{LAW_ID}/cleaned.txt
```

`cleaned.txt` may be used only for human-readable inspection, debugging,
pattern analysis, and side-by-side comparison. It must never be used for
offsets, spans, node text, validation, or hierarchy output.

### Confirmed normalized.json Schema

All 52 inspected `normalized.json` files contain:

```text
law_id
law_name
source_url
source_domain
source_type
raw_artifact_path
normalized_text
text_stats
markers
warnings
metadata
candidate_info
```

Confirmed Phase 4 metric locations:

- `metadata.cleaner_version`
- `markers.article_reference_count`
- `markers.article_heading_count`
- `markers.max_heading_article_number`
- `markers.has_heading_article_1`
- `markers.heading_sequence_score`

All 52 normalized artifacts have `metadata.cleaner_version == "v0.8.0"`.

### cleaned.txt Versus normalized_text Findings

All available Phase 4 outputs were inspected:

- 52 law directories exist under `data/interim/`.
- 52/52 have `normalized.json`.
- 52/52 have `cleaned.txt`.
- 52/52 have `cleaned.txt == normalized.json["normalized_text"]` exactly after
  UTF-8 decoding.
- No newline format mismatch was observed.
- No leading/trailing whitespace mismatch was observed.
- No Unicode content mismatch was observed.
- No file contained content missing from the other.

Decision:

- `normalized_text` remains the only source of truth for parsing and offsets.
- `cleaned.txt` is safe for visual inspection in the current corpus.
- `cleaned.txt` must never be used for offsets.
- If future `cleaned.txt` differs from `normalized_text`, emit
  `CLEANED_TEXT_MISMATCH` as a corpus consistency warning and continue parsing
  only from `normalized_text`.

## B. Corpus Pattern Inventory

The parser rules below are based on corpus-wide read-only inspection of all
Phase 4 outputs, plus deeper inspection of:

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

### Summary Table

| Category | Observed Forms And Frequency | True-Positive Evidence | False-Positive / Ambiguity Risk | Recommended Rule | Warning / Error Behavior |
|---|---:|---|---|---|---|
| Part | `Phần thứ ...`: 6 docs, 38 occurrences. Any `Phần` line: 9 docs, 43 occurrences. `Phần I`: 0 observed. | `BLDS_2015`: `Phần thứ nhất` then next line `QUY ĐỊNH CHUNG`. | `markers.contains_part` is unreliable because prose mentions trigger it. | Support line-anchored `Phần thứ <word>` now. Keep `Phần <Roman>` future-compatible but mark not observed. | Ambiguous `Phần` line becomes `UNUSUAL_HEADING_PATTERN`, not error. |
| Chapter | `Chương I`: 51 docs, 591 occurrences. Any `Chương`: 52 docs, 605 occurrences. Inline/bãi bỏ variants: 4 docs, 13 occurrences. | Most laws use next-line title, e.g. `Chương I` then uppercase title. | Constitution has `Chương II.` punctuation. VBHN headings may contain footnote/bãi bỏ. | Support `Chương <Roman>[.]`, optional footnote marker, title on same or next title-like line. | Unusual chapter title association is warning. |
| Section | `Mục N. TITLE`: 41 docs, 531 occurrences. `Mục N` without title: 0 observed. | Section titles are same-line in sampled laws. | Low risk, but source notes/appendices can contain table-like headings. | Support only line-anchored `Mục <number>. <title>` in baseline. | `Mục N` without title is future consideration warning. |
| Article | `Điều N. title`: all 52 docs. Bracket headings `Điều N.[x]`: 17 docs, 88 occurrences. Suffixes like `217a`: 14 docs. No exact `Điều N` without dot observed. | BLDS has 689 headings and max 689. | Naive `Điều` scan finds source-law notes in 28 docs and overcounts. | Require line anchor and dot or `.[footnote]`; reject `Điều N của Luật...` and `Điều N và Điều M...`; apply source-note exclusion. | Article count/max mismatches are warnings unless no Article found. |
| Clause | Plain `N. text`: 52 docs, 24,593 occurrences. Footnote form `N.[x] text`: 36 docs, 799 occurrences. Dot-no-space `N.text`: 1 doc, 13 occurrences. | Standard Article bodies use numbered clauses. | Source notes contain clause-like lines. Appendix/table regions also contain numeric rows. Missing whitespace appears in `LCT_2018`. | Accept `N. text` and `N.[x] text` inside Article. Treat `N.text` as ambiguous but parse if local sequence proves it is a Clause. Reject outside Article/source-note/appendix zones. | Ambiguous numeric lines emit `AMBIGUOUS_CLAUSE_CANDIDATE`. |
| Point | Plain `a) text`: 51 docs, 18,325 occurrences. Footnote form `d)[3] text`: 33 docs, 221 occurrences. Uppercase labels: 0 observed. | Standard points occur under numbered Clauses. | Earlier direct Article -> Point suspicion dropped from 611 to 8 after recognizing `N.[x]` Clauses. Remaining cases often follow malformed `1.text` or `1 text`. | Accept `[a-zđ])` and `[a-zđ])[footnote]` only under active Clause. No direct Article -> Point in baseline. | Point-like line outside Clause emits warning and remains in containing Article text. |
| Source-law notes | Intro lines: 28 docs, 86 occurrences. Article-like lines inside notes: 30. Clause-like lines inside notes: 288. | Examples begin `Điều 74 và Điều 75 của Luật... quy định như sau:`. | These create false Articles and duplicate numbering if not excluded. | Recognize source-note intro lines and enter source-note exclusion mode for hierarchy headings. | Source-note excluded content is not a legal hierarchy node; if it affects expected Article coverage, emit warning. |
| Appendices | 1 doc, 5 appendix headings: `LDT_VBHN`. | `PHỤ LỤC`, `Phụ lục I`, etc. | Appendix contains many numbered rows that look like Clauses. | Do not model appendix in Phase 5 schema. Stop Article/Clause/Point recognition inside appendix regions unless future schema adds `appendix`. | Emit `TRAILING_UNCLASSIFIED_TEXT` or `UNUSUAL_HEADING_PATTERN`. |
| Tables | 3 docs, 11 table-like markers: `STT`, etc. | `LDT_VBHN` has appendix tables. | Numeric rows can look like Clauses; cleaning has lost table structure. | Treat table-like/appendix zones as excluded from Clause/Point recognition. | Ambiguous table rows become warnings, not nodes. |
| Signatures | 13 docs, 30 signature-like lines. | `CHỦ TỊCH QUỐC HỘI...`, `Nơi nhận:`. | Some legal provisions mention `Chủ tịch`, especially Constitution, so signature detection must not be global heading logic. | Use signature-like lines only as trailing-boundary candidates after final Article/source-note context, not inside body. | Trailing text warning only if it affects Article metrics. |
| Footnotes | 44 docs, 4,610 lines containing `[n]`. | Headings and Clause/Point labels often include footnote markers. | Footnotes inside labels break naive regex. | Support optional `[\d+]` after Article/Clause/Point marker punctuation. Preserve marker in text; exclude from semantic number/title. | Unsupported footnote placement is `UNUSUAL_HEADING_PATTERN`. |
| Ambiguous numbered lists | Dot-no-space: 1 doc/13 lines. Number-space-no-dot: 10 docs/555 lines, many from tables/appendices. | `1.Chủ tịch...` is likely malformed Clause in `LCT_2018`; `1 Tòa án...` in `LPS_VBHN` is likely malformed Clause. | Many number-space-no-dot examples are table rows, not Clauses. | Baseline supports dot-no-space only when inside Article and sequence/context confirms Clause. Number-space-no-dot remains ambiguous unless targeted fixtures prove support. | Ambiguous lines warn and are not silently promoted. |

### Supported Pattern Set For Baseline

Observed and supported:

- `Phần thứ ...`
- `Chương <Roman>`
- `Mục N. title`
- `Điều N. title`
- `Điều N.[x] title`
- Article suffixes like `N[a-z]`
- `N. text`
- `N.[x] text`
- `[a-zđ]) text`
- `[a-zđ])[x] text`

Observed but ambiguous:

- `N.text`
- `N text`
- Article-like headings inside source-law notes
- Point-like lines after malformed Clause markers
- appendix/table numbered rows

Not observed, future consideration only:

- `Phần I`
- `Chương thứ ...`
- uppercase `ĐIỀU N`
- uppercase Point labels
- no-dot Article headings

## C. Schema Contract Review

The proposed `hierarchy.json` schema is feasible with actual repository data.

Directly available fields:

- `law_id`
- `cleaner_version`
- `source_file`
- metadata fields from `normalized.json`
- Phase 4 Article metrics from `markers`

Parser-produced fields:

- `schema_version`
- `parser_version`
- `root_node_id`
- `warnings`
- `nodes`

Nullable node fields:

- `number`: null only for root Law.
- `title`: null when no semantic title is safely associated.
- `parent_id`: null only for root Law.
- issue fields `node_id`, `start_offset`, `end_offset`: nullable for
  document/global issues.

Required top-level metadata:

- `law_name`
- `source_url`
- `source_domain`
- `source_type`
- `raw_artifact_path`
- `article_heading_count`
- `max_heading_article_number`
- `has_heading_article_1`
- `heading_sequence_score`

Important compatibility decision:

- `source_type` must preserve the actual source content type from
  `normalized.json`, currently `"html"`.
- Do not write `"vbhn"` into `source_type`.
- If legal document classification is later required, add a separate
  `legal_document_type` field in a future schema version.

No schema blocker was found.

### Canonical hierarchy.json Schema

```json
{
  "schema_version": "1.0",
  "parser_version": "v0.1.0",
  "cleaner_version": "v0.8.0",
  "law_id": "BLDS_2015",
  "source_file": "data/interim/BLDS_2015/normalized.json",
  "root_node_id": "BLDS_2015__root",
  "metadata": {
    "law_name": "Bộ luật Dân sự 2015",
    "source_url": "https://...",
    "source_domain": "thuvienphapluat.vn",
    "source_type": "html",
    "raw_artifact_path": "data/raw/BLDS_2015/latest/main.html",
    "article_heading_count": 689,
    "max_heading_article_number": 689,
    "has_heading_article_1": true,
    "heading_sequence_score": 1.0
  },
  "warnings": [],
  "nodes": []
}
```

Required top-level fields:

```text
schema_version
parser_version
cleaner_version
law_id
source_file
root_node_id
metadata
warnings
nodes
```

### Canonical LegalNode Schema

```json
{
  "node_id": "BLDS_2015__root__part_thu_nhat__chapter_I__article_1",
  "level": "article",
  "number": "1",
  "title": "Phạm vi điều chỉnh",
  "text": "Điều 1. Phạm vi điều chỉnh\n...",
  "start_offset": 103,
  "end_offset": 500,
  "parent_id": "BLDS_2015__root__part_thu_nhat__chapter_I",
  "children": [],
  "metadata": {}
}
```

Required node fields:

```text
node_id
level
number
title
text
start_offset
end_offset
parent_id
children
metadata
```

Allowed levels:

```text
law
part
chapter
section
article
clause
point
```

Rules:

- `nodes` is a flat list.
- `children` contains node ID strings.
- root is included in `nodes`.
- every non-root node has a valid parent.
- document-level metadata is not repeated on every node.
- mutable Pydantic fields must use `default_factory`.

### Root Node Contract

```json
{
  "node_id": "BLDS_2015__root",
  "level": "law",
  "number": null,
  "title": "Bộ luật Dân sự 2015",
  "text": "<entire normalized_text>",
  "start_offset": 0,
  "end_offset": 100000,
  "parent_id": null,
  "children": [],
  "metadata": {}
}
```

Required invariants:

```text
root.node_id == root_node_id
root.level == "law"
root.number == null
root.parent_id == null
root.start_offset == 0
root.end_offset == len(normalized_text)
root.text == normalized_text
```

### Canonical legal_parsing_report.json Schema

```json
{
  "schema_version": "1.0",
  "parser_version": "v0.1.0",
  "started_at": "2026-06-05T10:00:00Z",
  "finished_at": "2026-06-05T10:01:00Z",
  "duration_seconds": 60.0,
  "input_dir": "data/interim",
  "output_dir": "data/interim",
  "total_documents": 52,
  "successful": 49,
  "success_with_warnings": 3,
  "failed": 0,
  "nodes_by_level": {},
  "validation_summary": {},
  "results": [],
  "warnings": [],
  "errors": []
}
```

Required report fields:

```text
schema_version
parser_version
started_at
finished_at
duration_seconds
input_dir
output_dir
total_documents
successful
success_with_warnings
failed
nodes_by_level
validation_summary
results
warnings
errors
```

Per-law result structure:

```json
{
  "law_id": "BLDS_2015",
  "status": "success",
  "input_path": "data/interim/BLDS_2015/normalized.json",
  "output_path": "data/interim/BLDS_2015/hierarchy.json",
  "duration_seconds": 1.23,
  "node_count": 2500,
  "counts_by_level": {},
  "has_article_1": true,
  "max_article_number": 689,
  "expected_article_heading_count": 689,
  "article_heading_count_matches": true,
  "expected_max_heading_article_number": 689,
  "max_article_number_matches": true,
  "warnings": [],
  "errors": []
}
```

Allowed statuses:

```text
success
success_with_warnings
failed
```

## D. Risks And Open Decisions

- Clause ambiguity:
  - Decision: support plain and footnote numbered Clauses; treat malformed
    `N.text` as warning-backed candidate only when local Article context and
    sequence make it very likely.
- Point ambiguity:
  - Decision: no direct Article -> Point baseline. Remaining point-like lines
    outside Clause are warnings unless malformed preceding Clause support
    resolves them.
- Title-line association:
  - Decision: Part/Chapter may consume one next line as title only when the line
    is title-like, non-heading, non-Clause, non-Point, non-source-note, and not
    body prose. Section/Article titles are same-line in baseline.
- Source-note rejection:
  - Decision: source-note intro lines enter an excluded tail/source-note region.
    Article/Clause/Point candidates in that region are not hierarchy nodes.
- Duplicate numbering:
  - Decision: duplicate sibling node IDs get deterministic occurrence suffixes
    and structured warnings.
- Article suffixes:
  - Decision: support lowercase suffixes as part of Article number, e.g.
    `"217a"`.
- `cleaned.txt` mismatches:
  - Decision: warn with `CLEANED_TEXT_MISMATCH`; never switch parser input.
- Performance/artifact size:
  - BLDS rough parent-inclusive span estimate:
    - normalized chars: 368,085
    - recognized rough nodes: law 1, part 6, chapter 27, section 39,
      article 689, clause 1,418, point 312
    - duplicated node text chars estimate: 2,044,965
    - ratio: about 5.56x normalized text before JSON overhead
    - read-only scan duration: about 0.02s
  - Decision: Phase 5 report should measure per-law parse duration,
    normalized size, output hierarchy size, size ratio, and approximate peak
    memory where practical.

No unresolved schema decisions block the first implementation slice.

## E. Proposed Architecture

### Processing Modules

`src/processing/legal_hierarchy_models.py`

- `LegalNodeLevel(StrEnum)`
- `StructuredParsingIssue(BaseModel)`
- `LegalNode(BaseModel)`
- `LegalHierarchyMetadata(BaseModel)`
- `LegalHierarchyDocument(BaseModel)`
- `LegalParsingResult(BaseModel)`
- `LegalParsingReport(BaseModel)`
- `ValidationSummary(BaseModel)`

Purpose: canonical schemas, issue contracts, report contracts, and mutable
defaults via `default_factory`.

`src/processing/normalized_input.py`

- `load_normalized_artifact(path: Path) -> NormalizedLegalArtifact`
- `compare_cleaned_text(cleaned_path: Path, normalized_text: str) -> StructuredParsingIssue | None`

Purpose: typed normalized input loading and diagnostic consistency check.

`src/processing/legal_heading_recognizer.py`

- `RecognizedHeading`
- `LegalHeadingRecognizer`

Responsibilities:

- line iteration with exact offsets;
- line-anchored regex matching;
- source-note/appendix/table exclusion hints;
- semantic title extraction.

`src/processing/legal_span_segmenter.py`

- `LegalSpanSegmenter`

Responsibilities:

- source-string immutable span calculation;
- parent-inclusive spans;
- trailing/source-note exclusion boundaries.

`src/processing/legal_hierarchy_builder.py`

- `LegalHierarchyBuilder`

Responsibilities:

- root node construction;
- parent selection;
- child ID lists;
- deterministic node IDs;
- collision suffix warnings.

`src/processing/legal_tree_validator.py`

- `LegalTreeValidator`

Responsibilities:

- tree integrity;
- offset validation;
- Phase 4 metric comparison;
- warning/error classification.

`src/processing/legal_parser.py`

- `LegalParser`

Responsibilities:

- compose input, recognizer, segmenter, builder, validator;
- return `LegalHierarchyDocument` plus structured issues.

### Service Module

`src/services/legal_parsing_service.py`

- `LegalParsingServiceConfig`
- `LegalParsingService`
- `run_legal_parsing_pipeline(config) -> LegalParsingReport`

Responsibilities:

- batch law discovery;
- selected law IDs;
- output/write policy;
- failed-document isolation;
- report aggregation.

### CLI Module

`scripts/parse_legal_hierarchy.py`

Responsibilities:

- CLI options;
- console summary;
- exit codes only.

### Data Flow

```text
normalized.json + optional cleaned.txt diagnostic
-> typed input
-> heading recognition
-> span segmentation
-> hierarchy building
-> validation
-> optional hierarchy write
-> batch report
```

## F. Exact Files To Add Or Modify

### Files To Add

```text
src/processing/__init__.py
src/processing/normalized_input.py
src/processing/legal_hierarchy_models.py
src/processing/legal_heading_recognizer.py
src/processing/legal_span_segmenter.py
src/processing/legal_hierarchy_builder.py
src/processing/legal_tree_validator.py
src/processing/legal_parser.py
src/services/legal_parsing_service.py
scripts/parse_legal_hierarchy.py
tests/fixtures/legal_hierarchy/article_only.txt
tests/fixtures/legal_hierarchy/part_chapter_titles.txt
tests/fixtures/legal_hierarchy/footnote_markers.txt
tests/fixtures/legal_hierarchy/source_note_tail.txt
tests/fixtures/legal_hierarchy/malformed_numbering.txt
tests/unit/processing/test_normalized_input.py
tests/unit/processing/test_legal_hierarchy_models.py
tests/unit/processing/test_legal_heading_recognizer.py
tests/unit/processing/test_legal_span_segmenter.py
tests/unit/processing/test_legal_hierarchy_builder.py
tests/unit/processing/test_legal_tree_validator.py
tests/unit/processing/test_legal_parser.py
tests/unit/services/test_legal_parsing_service.py
tests/integration/test_legal_hierarchy_corpus.py
```

### Files To Modify

```text
src/core/exceptions.py
```

Add `LegalParsingError` deriving from `VnLawError` if shared exception hierarchy
is preferred.

Documentation files to modify only after implementation and validation pass:

```text
README.md
PROJECT_CONTEXT.md
docs/legal_parsing.md
docs/project_phase_journal.md
```

### Files To Inspect Only

```text
data/interim/*/normalized.json
data/interim/*/cleaned.txt
artifacts/reports/cleaning/*.json
configs/laws/corpus_registry.yml
existing Phase 1-4 source/tests/docs
```

### Files Explicitly Not To Touch

```text
data/raw/
existing data/interim/*/normalized.json
existing data/interim/*/cleaned.txt
data/reports/
existing generated artifacts/reports/*
.claude/
Claude settings
CLAUDE.md unless explicitly requested later
PROJECT_CONTEXT.md until documentation update step
```

## G. Detailed Recognition And Hierarchy Rules

### Immutable Source-String Rule

The parser must load exactly:

```python
normalized_text = normalized_artifact["normalized_text"]
```

Before offset calculation, the parser must not:

- call `.strip()` on the full source text;
- normalize Unicode again;
- replace newlines;
- collapse whitespace;
- remove blank lines;
- alter punctuation;
- change casing;
- rewrite footnote markers.

Recognition helpers may normalize copied candidate strings for comparison or
ID generation only. They must preserve the original source string and source
offsets.

Required invariant:

```python
node.text == normalized_text[node.start_offset:node.end_offset]
```

### Line Handling

- Iterate with regex line spans or explicit offset tracking.
- Candidate strings may be stripped only for recognition.
- Offsets always refer to original `normalized_text`.

### Title Semantics

`title` stores semantic title text only.

Example:

```text
Source:
Điều 1. Phạm vi điều chỉnh

number:
"1"

title:
"Phạm vi điều chỉnh"

text:
"Điều 1. Phạm vi điều chỉnh\n..."
```

Part/Chapter next-line title association may use one following line only when
that line:

- is not another recognized heading;
- is not a Clause or Point candidate;
- is not ordinary body prose;
- is not a signature/footer/source-law note;
- satisfies a corpus-supported title-like rule.

Tests must prevent an Article heading from being consumed as a Chapter or Part
title.

### Part Recognition

Supported:

```text
^Phần\s+thứ\s+\S+\s*$
```

Case-insensitive.

Future-compatible but not observed:

```text
^Phần\s+[IVXLC]+\b
```

Title source: next non-empty title-like line if present.

### Chapter Recognition

Supported:

```text
^Chương\s+[IVXLC]+\.?\s*$
^Chương\s+[IVXLC]+\[\d+\]\s+\(được bãi bỏ\)$
```

Title source: next non-empty title-like line, unless same-line title exists.

### Section Recognition

Supported:

```text
^Mục\s+(\d+)\.\s+(.+)$
```

Title source: same line.

### Article Recognition

Supported:

```text
^Điều\s+(\d+[a-z]?)\.(?:\[(\d+)\])?\s+(.+)$
```

Rules:

- title is semantic content after marker and optional footnote;
- support Article suffixes such as `4a`, `217a`;
- reject source-note intros:
  - `Điều N của Luật...`
  - `Điều N và Điều M của Luật...`
  - lines ending or continuing with `quy định như sau:`;
- no-dot Article headings are future consideration only.

### Clause Recognition

Certain Clause candidate:

- active Article exists;
- not in source-note/appendix/table excluded region;
- line matches:

```text
^(\d+)\.(?:\[\d+\])?\s+\S
```

Ambiguous Clause candidate:

- `^(\d+)\.\S` inside Article with plausible local sequence;
- malformed `N text` only if fixture-driven and not table-like.

Rejected Clause candidate:

- before first Article;
- inside source notes;
- inside appendices/tables;
- date/table row patterns;
- unrelated enumeration.

Ambiguous numeric lines emit `AMBIGUOUS_CLAUSE_CANDIDATE` and must not be
silently promoted.

### Point Recognition

Certain Point candidate:

- active Clause exists;
- line matches:

```text
^([a-zđ])\)(?:\[\d+\])?\s+\S
```

Rejected Point candidate:

- outside Clause;
- uppercase labels, unless future corpus evidence appears;
- parenthetical prose not line anchored.

Baseline rule:

```text
No direct Article -> Point relation.
```

Point-like lines outside Clause emit `POINT_LIKE_LINE_OUTSIDE_CLAUSE` and
remain in the containing Article text.

### Source-Law Note Handling

Detect source-note intro lines such as:

```text
Điều 74 và Điều 75 của Luật Giá số 16/2023/QH15, ... quy định như sau:
Điều 3 của Luật số 81/2025/QH15 sửa đổi, bổ sung ..., quy định như sau:
```

From source-note intro to EOF, or to a validated later main hierarchy boundary,
suppress Article/Clause/Point node creation.

Source-note text:

- remains in root text;
- may be excluded from the final Article span by ending the final Article before
  the source-note boundary;
- does not become a legal hierarchy node in Phase 5.

### Appendix/Table/Signature Handling

- Appendices are observed but not represented in the Phase 5 schema.
- Once an appendix region is detected, do not create Article/Clause/Point nodes
  inside it unless a future schema adds `appendix`.
- Table-like zones such as `STT` are excluded from Clause/Point recognition.
- Signature-like lines are only trailing-boundary candidates after final legal
  body/source-note context. They must not be used as global heading logic
  because legal provisions can mention `Chủ tịch`.

### Span Semantics

Use Python slicing semantics:

```text
start_offset is inclusive
end_offset is exclusive
text == normalized_text[start_offset:end_offset]
```

Text ownership:

- root contains the entire normalized text;
- parent spans include descendant spans;
- Article text includes Clause and Point text;
- Clause text includes Point text;
- child spans are contained inside parent spans;
- sibling spans are ordered and do not overlap;
- parent-child overlap is valid;
- sibling overlap is an error.

Node end rules:

- root ends at `len(normalized_text)`;
- non-root node starts at heading/marker line offset;
- node ends at the next same-or-higher-level legal heading in the same
  recognition region;
- source-note/appendix trailing regions may end the current legal node without
  becoming nodes.

### Direct Parent Text For Future Phase 6

Phase 5 stores parent-inclusive text only. If Phase 6 needs direct parent text
without descendants, it can derive it by subtracting child spans from the
parent span using `children`, `start_offset`, and `end_offset`. No Phase 5
schema change is needed.

### Deterministic Node IDs

Base rules:

```text
root:
{law_id}__root

other nodes:
{parent_node_id}__{level}_{normalized_number}
```

Examples:

```text
BLDS_2015__root
BLDS_2015__root__part_thu_nhat
BLDS_2015__root__part_thu_nhat__chapter_I
BLDS_2015__root__part_thu_nhat__chapter_I__article_1
BLDS_2015__root__part_thu_nhat__chapter_I__article_1__clause_1
BLDS_2015__root__part_thu_nhat__chapter_I__article_1__clause_1__point_đ
```

Normalization:

- `Phần thứ nhất` -> `part_thu_nhat`.
- Roman numerals are preserved as seen, e.g. `chapter_I`.
- Article suffixes are preserved, e.g. `article_217a`.
- Vietnamese Point label `đ` is preserved as UTF-8 in IDs unless a future
  storage system requires ASCII.

Collision rule:

```text
__occurrence_2
__occurrence_3
```

Collision suffixes are assigned by document order. Emit
`NODE_ID_COLLISION_RESOLVED` whenever a suffix is required.

## H. Structured Warning And Error Contract

Shared issue structure:

```json
{
  "code": "ARTICLE_COUNT_MISMATCH",
  "message": "Parsed article count differs from Phase 4 heading count.",
  "law_id": "BLDS_2015",
  "node_id": null,
  "start_offset": null,
  "end_offset": null,
  "context": {
    "expected": 689,
    "actual": 688
  }
}
```

Required fields:

```text
code
message
law_id
node_id
start_offset
end_offset
context
```

Nullable fields:

- `node_id`
- `start_offset`
- `end_offset`

These are nullable for document-level or global issues.

### Error Codes

```text
NO_ARTICLES_FOUND
INVALID_TREE
INVALID_OFFSET
TEXT_OFFSET_MISMATCH
ORPHAN_NODE
PARENT_CYCLE
UNRESOLVED_DUPLICATE_NODE_ID
SCHEMA_VALIDATION_FAILED
GLOBAL_INPUT_OR_OUTPUT_FAILURE
```

### Warning Codes

```text
ARTICLE_COUNT_MISMATCH
MAX_ARTICLE_NUMBER_MISMATCH
NODE_ID_COLLISION_RESOLVED
POINT_LIKE_LINE_OUTSIDE_CLAUSE
AMBIGUOUS_CLAUSE_CANDIDATE
CLEANED_TEXT_MISMATCH
UNUSUAL_HEADING_PATTERN
TRAILING_UNCLASSIFIED_TEXT
SOURCE_NOTE_EXCLUDED
APPENDIX_EXCLUDED
```

## I. Detailed Test Plan

Committed tests must use small fixtures under:

```text
tests/fixtures/legal_hierarchy/
```

The default test suite must not depend unconditionally on ignored local corpus
files under `data/interim/`.

Real-corpus validation must be optional:

- marked with `pytest.mark.corpus`;
- skipped when local corpus data is unavailable; or
- executed through a dedicated local validation command.

### Test Groups

`tests/unit/processing/test_normalized_input.py`

- fixture: minimal normalized artifact JSON and matching/mismatching
  `cleaned.txt`.
- expected: exact contract load; `CLEANED_TEXT_MISMATCH` warning on mismatch.
- gate: parser input safety.

`tests/unit/processing/test_legal_hierarchy_models.py`

- fixture: in-memory models.
- expected: schema validation, independent mutable defaults, issue
  serialization, root contract.
- gate: canonical schema stability.

`tests/unit/processing/test_legal_heading_recognizer.py`

- fixture: `part_chapter_titles.txt`, `footnote_markers.txt`,
  `source_note_tail.txt`.
- expected: Part/Chapter next-line titles; Section same-line title; Article
  suffix; footnote markers; cross-reference/source-note rejection.
- gate: safe recognition.

`tests/unit/processing/test_legal_span_segmenter.py`

- fixture: synthetic mixed hierarchy.
- expected: exact offsets, source immutability, parent containment, sibling
  non-overlap.
- gate: offset correctness.

`tests/unit/processing/test_legal_hierarchy_builder.py`

- fixture: recognized spans.
- expected: Article-only, missing intermediate levels, deterministic IDs,
  collision suffixes.
- gate: tree construction.

`tests/unit/processing/test_legal_tree_validator.py`

- fixture: valid/invalid hierarchy documents.
- expected: catches duplicate IDs, orphan nodes, cycles, invalid offsets, text
  mismatch, invalid parent chain.
- gate: safety before writing artifacts.

`tests/unit/processing/test_legal_parser.py`

- fixture: complete synthetic normalized artifact.
- expected: end-to-end hierarchy document with root, Articles, Clauses, Points,
  warnings.
- gate: parser facade.

`tests/unit/services/test_legal_parsing_service.py`

- fixture: temp input/output directories.
- expected: batch aggregation, failed-document isolation, output-path behavior,
  overwrite behavior, validate-only behavior.
- gate: production orchestration.

`tests/integration/test_legal_hierarchy_corpus.py`

- marked `pytest.mark.corpus`.
- skipped if `data/interim` is unavailable.
- expected: priority laws parse in temp output and match Phase 4 Article metrics
  where source-note exclusion is stable.
- gate: local real-corpus validation only.

Performance test:

- fixture: BLDS local corpus when available or synthetic large document.
- expected: duration and hierarchy-size ratio recorded, not hard-failing except
  on extreme regression.
- gate: artifact-size awareness.

Required coverage list:

1. normalized input contract.
2. `cleaned.txt` versus `normalized_text` comparison.
3. hierarchy schema.
4. independent mutable defaults.
5. root contract.
6. Article-only document.
7. Part and Chapter titles on next line.
8. `Mục` same-line title.
9. Article semantic title extraction.
10. Article suffixes.
11. cross-reference rejection.
12. source-law note rejection.
13. Clause detection.
14. nested numbered-list ambiguity.
15. Point detection.
16. Point-like line outside Clause.
17. exact offsets.
18. source text immutability.
19. parent span containment.
20. sibling non-overlap.
21. deterministic IDs.
22. deterministic collision suffixes.
23. warning/error serialization.
24. validation failures.
25. parsing report aggregation.
26. failed-document isolation.
27. optional real-corpus validation.
28. performance and output-size measurement.

## J. Detailed Validation Plan

1. Synthetic unit tests
   - command: `uv run pytest tests/unit/processing -q`
   - acceptance: all pass; no corpus dependency.
   - stop condition: any schema/offset failure.

2. Fixture integration tests
   - command: `uv run pytest tests/unit/services -q`
   - acceptance: service report and temp outputs valid.
   - stop condition: failed isolation or overwrite behavior wrong.

3. Optional local corpus validation
   - command: `uv run pytest tests/integration -q -m corpus`
   - acceptance: skipped if corpus absent; passes if corpus present.
   - protected paths: output only to pytest temp dirs.

4. Priority-law validation
   - command: parse selected laws to `/tmp/vnlaw_phase5_validation`.
   - laws:
     `BLDS_2015 BLHS_VBHN LDD_VBHN LTTHC LVL_2025 LANM_2025 LHNGD_VBHN LTATGT_VBHN`
   - acceptance: no failed docs; warnings reviewed.

5. Full 52-law validation
   - command: CLI with `--validate-only` first.
   - acceptance: zero hard failures; expected warnings classified.

6. Parsing report audit
   - inspect report schema, counts, warnings, errors.
   - acceptance: totals match selected document count; `nodes_by_level` and
     validation summary are consistent.

7. Performance and artifact-size audit
   - measure:
     - normalized text size;
     - hierarchy JSON size;
     - size ratio;
     - parse duration;
     - approximate memory.
   - BLDS is priority large-law benchmark.
   - acceptance: no uncontrolled blow-up beyond reviewed threshold.

## K. Proposed CLI

Intended command:

```bash
uv run python scripts/parse_legal_hierarchy.py \
  --input-dir data/interim \
  --output-dir data/interim \
  --report artifacts/reports/parsing/legal_parsing_report.json
```

Selected laws:

```bash
uv run python scripts/parse_legal_hierarchy.py \
  --input-dir data/interim \
  --output-dir data/interim \
  --report artifacts/reports/parsing/legal_parsing_report.json \
  --law-ids BLDS_2015 LDD_VBHN
```

Options:

- `--input-dir`
  - default: `data/interim`
  - purpose: directory containing `{LAW_ID}/normalized.json`.
- `--output-dir`
  - default: `data/interim`
  - purpose: directory where `{LAW_ID}/hierarchy.json` will be written.
- `--report`
  - default: `artifacts/reports/parsing/legal_parsing_report.json`
  - purpose: write batch parsing report.
- `--registry`
  - default: `configs/laws/corpus_registry.yml`
  - purpose: validate selected law IDs and preserve registry order where useful.
- `--law-ids`
  - default: all discovered/registry laws.
  - purpose: parse selected laws.
- `--overwrite`
  - default: false.
  - purpose: existing `hierarchy.json` blocks writing unless this flag is set.
- `--validate-only`
  - default: false.
  - purpose: parse and validate without writing per-law hierarchy files.
- `--fail-on-warning`
  - default: false.
  - purpose: return nonzero if any warnings exist.
- `--verbose`
  - default: false.
  - purpose: print per-law details.

Exit codes:

- `0`: successful, warnings allowed unless `--fail-on-warning`.
- `1`: failed docs, or warnings when `--fail-on-warning`.
- `2`: global crash/config/input/output failure.

Batch isolation:

- one failed law must not stop the rest of the batch;
- global input/output failures may stop the batch and produce
  `GLOBAL_INPUT_OR_OUTPUT_FAILURE`.

Report behavior:

- report is written for every run unless a global failure prevents report
  writing;
- `--validate-only` still writes a report but does not write `hierarchy.json`.

## L. Step-By-Step Future Implementation Checklist

1. Step 1 - Input contract and cleaned comparison
   - Objective: safe input loading.
   - Files: `normalized_input.py`, `test_normalized_input.py`.
   - Implementation: typed load from `normalized.json`, compare optional
     `cleaned.txt`.
   - Command: `uv run pytest tests/unit/processing/test_normalized_input.py -q`.
   - Acceptance: exact equality and mismatch warning tested.
   - Risks: none to corpus; uses fixtures.
   - Non-goals: no hierarchy parser.

2. Step 2 - Canonical schemas and issues
   - Files: `legal_hierarchy_models.py`, schema tests.
   - Implementation: Pydantic models, enums, issue codes.
   - Acceptance: root/node/report schema validates.
   - Non-goals: no recognition.

3. Step 3 - Heading recognizer
   - Files: `legal_heading_recognizer.py`, recognizer tests.
   - Implementation: line-anchored recognition with footnote/source-note
     handling.
   - Acceptance: observed supported patterns pass; unobserved patterns only
     future-compatible warnings.
   - Risks: source-note boundary false positives.

4. Step 4 - Clause/Point recognition refinement
   - Files: same recognizer tests.
   - Implementation: certain/ambiguous/rejected candidate classification.
   - Acceptance: `N.[x]`, `a)[x]`, malformed `N.text`, point outside Clause
     covered.
   - Non-goals: no direct Article -> Point.

5. Step 5 - Span segmentation
   - Files: `legal_span_segmenter.py`.
   - Implementation: parent-inclusive spans and trailing/source-note
     boundaries.
   - Acceptance: exact slicing invariant passes.

6. Step 6 - Hierarchy builder and IDs
   - Files: `legal_hierarchy_builder.py`.
   - Implementation: root, parent lookup, children, deterministic IDs.
   - Acceptance: collision suffix warning tested.

7. Step 7 - Validator
   - Files: `legal_tree_validator.py`.
   - Implementation: structural, offset, and metric checks.
   - Acceptance: invalid trees fail deterministically.

8. Step 8 - Parser facade
   - Files: `legal_parser.py`.
   - Implementation: compose components and return validated document.
   - Acceptance: synthetic end-to-end parse passes.

9. Step 9 - Batch service and report
   - Files: `legal_parsing_service.py`.
   - Implementation: law discovery, selected IDs, overwrite/validate-only
     policy, report aggregation.
   - Acceptance: temp-dir service tests pass.

10. Step 10 - CLI
    - Files: `scripts/parse_legal_hierarchy.py`.
    - Implementation: options and exit codes described in the CLI section.
    - Acceptance: CLI help and service tests pass.

11. Step 11 - Priority corpus validation
    - Files: no committed data changes.
    - Implementation: run to `/tmp` first.
    - Acceptance: priority laws parse with reviewed warnings.

12. Step 12 - Full corpus output and documentation
    - Requires explicit approval.
    - Files: generated `hierarchy.json`, parsing report, docs updates.
    - Acceptance: full 52-law gate passes.
    - Non-goals: chunking/RAG.

## M. What Will Be Implemented

Will implement:

- normalized input loader;
- `cleaned.txt` comparison diagnostic;
- Pydantic hierarchy/report schemas;
- structured warning/error models;
- line-anchored heading recognizer;
- source-note/appendix/table exclusion;
- Clause/Point candidate classification;
- exact span segmentation;
- deterministic hierarchy builder;
- deterministic node IDs with collision suffixes;
- validator;
- parser facade;
- batch parsing service;
- CLI;
- unit tests, service tests, optional corpus tests;
- performance and artifact-size reporting.

Strict non-goals:

- parent-child chunking;
- processed JSONL;
- embedding/indexing;
- Qdrant;
- retrieval/reranking;
- generation/RAG;
- Advanced RAG;
- GraphRAG;
- API/deployment;
- LLM-based parsing;
- cleaning rewrites;
- mutation of `data/raw`;
- mutation of existing normalized artifacts during tests;
- docs updates before parser validation, except this approved plan document.

## N. Recommended First Implementation Slice

Smallest safe first slice:

- Add:
  - `src/processing/normalized_input.py`
  - `src/processing/legal_hierarchy_models.py`
  - `src/processing/legal_heading_recognizer.py`
  - fixture files under `tests/fixtures/legal_hierarchy/`
  - tests for input contract, cleaned comparison, schemas, structured issues,
    and heading recognition.

Include:

- normalized input loader;
- `cleaned.txt` comparison diagnostic;
- canonical Pydantic models;
- structured warning/error models;
- synthetic fixtures;
- minimal recognizer for Part/Chapter/Section/Article plus source-note
  rejection.

Exclude:

- span segmentation;
- hierarchy building;
- validation service;
- CLI;
- full-corpus parsing;
- writing any `hierarchy.json`.

## Execution Progress

- [x] Step 1 — Input contract and cleaned comparison
- [x] Step 2 — Canonical schemas and issues
- [x] Step 3 — Heading recognizer
- [x] Step 4 — Clause/Point recognition refinement
- [x] Step 5 — Span segmentation
- [ ] Step 6 — Hierarchy builder and IDs
- [ ] Step 7 — Validator
- [ ] Step 8 — Parser facade
- [ ] Step 9 — Batch service and report
- [ ] Step 10 — CLI
- [ ] Step 11 — Priority corpus validation
- [ ] Step 12 — Full corpus output and documentation
