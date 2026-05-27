# Cleaning & Normalization Pipeline

## Overview

The Cleaning & Normalization phase converts audited raw HTML artifacts into normalized Vietnamese legal text while preserving the structural signals required by the Legal Hierarchy Parser.

This phase is not responsible for parsing legal hierarchy, creating chunks, generating embeddings, or building RAG. Its responsibility is narrower and stricter:

```text
raw HTML + source metadata
→ deterministic text extraction
→ Unicode and whitespace normalization
→ legal boundary preservation
→ normalized.json
→ cleaning_report.json
```

The output must be clean enough for parsing, but it must not destroy the original legal structure. In Vietnamese legal documents, the legal hierarchy is often expressed through headings and numbering patterns such as:

```text
Phần ...
Chương ...
Mục ...
Điều 1. ...
1. ...
a) ...
```

Therefore, the cleaner must preserve not only explicit words such as `Điều`, but also numbered clause lines and lettered point labels.

This phase is deterministic and stateless. The same input should always produce the same output. No LLM-based cleaning is allowed.

## Quick Start

### Intended CLI

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report data/reports/cleaning_report.json
```

### Optional Development Run

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report data/reports/cleaning_report.json \
  --min-text-length 10000 \
  --write-txt \
  --verbose
```

### Expected Inputs

Preferred raw artifact layout:

```text
data/raw/{LAW_ID}/latest/main.html
data/raw/{LAW_ID}/latest/metadata.json
```

Fallback flat layout:

```text
data/raw/{LAW_ID}/main.html
data/raw/{LAW_ID}/metadata.json
```

### Expected Outputs

Primary output for each law:

```text
data/interim/{LAW_ID}/normalized.json
```

Optional debug output:

```text
data/interim/{LAW_ID}/cleaned.txt
```

Corpus-level report:

```text
data/reports/cleaning_report.json
```

## Architecture
`scripts/clean_raw_corpus.py` (CLI) $\rightarrow$ `src/services/cleaning_service.py` (Orchestration) $\rightarrow$ `src/ingestion/cleaning.py` (Core Logic)

```text
┌──────────────────────────────┐
│  Raw HTML Artifact           │
│  main.html + metadata.json   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Raw Artifact Discovery      │
│  latest/ layout or flat      │
│  fallback layout             │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Metadata Loader             │
│  law_id, source_url, domain, │
│  source_type, raw path       │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  HTML Content Extraction     │
│  visible legal text only     │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Safe Boilerplate Removal    │
│  navigation, footer, ads,    │
│  repeated non-legal blocks   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Unicode Normalization       │
│  NFC, NBSP, BOM, zero-width  │
│  characters                  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Whitespace Normalization    │
│  spaces, newlines, paragraph │
│  boundaries                  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Legal Boundary Preservation │
│  Điều, Chương, Mục, 1., a)   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Normalized JSON Writer      │
│  data/interim/{LAW_ID}/      │
│  normalized.json             │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  Cleaning Report Writer      │
│  data/reports/               │
│  cleaning_report.json        │
└──────────────────────────────┘
```

## Components

### 1. Raw Artifact Discovery

**Goal**: Locate raw artifacts without recursively scanning the entire raw corpus and without mutating `data/raw`.

The cleaner should discover only immediate child directories under `data/raw`.

Supported layouts:

```text
data/raw/{LAW_ID}/latest/main.html
data/raw/{LAW_ID}/latest/metadata.json
```

```text
data/raw/{LAW_ID}/main.html
data/raw/{LAW_ID}/metadata.json
```

**Responsibilities**:
- Identify `LAW_ID` directories.
- Resolve `main.html` and `metadata.json`.
- Prefer `latest/` layout when both layouts exist.
- Skip or mark failed artifacts that do not contain required files.
- Never modify raw artifacts.

**Output**:
- A list of artifact descriptors containing:
  - `law_id`
  - `main_html_path`
  - `metadata_json_path`
  - `output_dir`

**Validation**:
- `main.html` path exists.
- `metadata.json` path exists.
- Artifact path is traceable in the final output.

### 2. Metadata Loader

**Goal**: Preserve traceability from normalized text back to the raw artifact and legal source.

The loader should read `metadata.json` and preserve the following fields when available:

```text
law_id
law_name or name
source_url or url
source_domain
source_type
content_hash
crawled_at
raw_artifact_path
```

**Rules**:
- Use metadata as the source of truth for source URL and source type.
- Do not infer legal metadata from the visible HTML if metadata already provides it.
- If metadata lacks optional fields, preserve `null` or omit only when the downstream schema allows it.
- If `law_id` is missing in metadata, use the directory name as fallback and add a warning.

**Validation**:
- `law_id` is available from metadata or directory name.
- `source_url` or `url` is available.
- `raw_artifact_path` is recorded.

### 3. HTML Content Extraction

**Goal**: Extract visible legal text while removing obvious non-content HTML elements.

The extractor should remove or ignore:

```text
<script>
<style>
<noscript>
<iframe>
<form>
button
select
input
svg
hidden elements
irrelevant navigation when safely identifiable
footer blocks when safely identifiable
advertisement blocks when safely identifiable
```

Recommended deterministic parsers:

```text
BeautifulSoup
lxml
html5lib
```

**Extraction strategy**:

1. Try to identify the main legal document container if stable selectors are available.
2. If no reliable container exists, extract visible body text conservatively.
3. Preserve headings, paragraphs, list items, and line boundaries.
4. Avoid aggressive deletion of generic `div` or `span` containers because legal text may appear inside them.

**Output**:
- Extracted visible text with basic line structure.

**Validation**:
- Extracted text is not empty.
- Extracted text contains legal markers when the source is valid.
- No obvious raw HTML tags remain in the extracted text.

### 4. Safe Boilerplate Removal

**Goal**: Remove repeated non-legal page content without damaging legal provisions.

Common boilerplate candidates:

```text
THƯ VIỆN PHÁP LUẬT
Đăng nhập
Đăng ký
Tra cứu pháp luật
Hotline
Liên hệ
Tải về
Văn bản liên quan
Lược đồ
Nội dung MIX
Quảng cáo
```

**Rules**:
- Prefer keeping minor boilerplate over deleting legal content.
- Never remove lines containing strong legal markers unless the rule is deterministic and tested.
- Strong legal markers include:
  - `Điều`
  - `Chương`
  - `Mục`
  - `Phần`
  - `Văn bản hợp nhất`
  - `QUỐC HỘI`
  - `Căn cứ`
- Boilerplate rules should be explicit and testable.

**Validation**:
- Text still contains article markers after boilerplate removal.
- Text does not shrink suspiciously.
- Removal statistics are recorded in `text_stats` or warnings.

### 5. Unicode Normalization

**Goal**: Ensure consistent Vietnamese Unicode representation.

Operations:

```text
Apply Unicode NFC normalization.
Decode HTML entities.
Replace non-breaking spaces with regular spaces.
Remove zero-width characters.
Remove BOM characters.
Remove invalid control characters except useful whitespace.
```

Characters to normalize or remove:

```text
\u00a0  NBSP → regular space
\u200b  zero-width space → remove
\u200c  zero-width non-joiner → remove
\u200d  zero-width joiner → remove
\ufeff  BOM → remove
```

Important rule:

```text
Do not guess corrupted Vietnamese text corrections such as "t�i" → "tải" unless there is a deterministic, tested mapping.
```

If the replacement character `�` appears, the cleaner should add a warning:

```text
encoding_replacement_character_found
```

**Validation**:
- Text is valid UTF-8.
- Vietnamese diacritics are preserved.
- Unwanted control characters are removed.
- Replacement characters are reported, not silently “fixed”.

### 6. Whitespace Normalization

**Goal**: Make text spacing consistent while preserving legal structure.

Operations:

```text
Convert \r\n and \r to \n.
Convert tabs to spaces.
Strip leading and trailing whitespace on each line.
Collapse repeated spaces within each line.
Collapse excessive blank lines.
Preserve paragraph breaks.
Preserve line boundaries around legal headings and numbering.
```

Do not:

```text
Join the entire document into one line.
Remove all newlines.
Merge article headings into previous paragraphs.
Destroy numbering patterns such as "1.", "2.", "a)", "b)".
```

**Validation**:
- No tabs remain.
- No lines contain only whitespace.
- No excessive consecutive blank lines remain.
- Article headings remain line-visible and parseable.

### 7. Legal Boundary Preservation

**Goal**: Preserve structural signals needed by the Legal Hierarchy Parser.

Important markers and patterns:

```text
Phần ...
Chương ...
Mục ...
Điều 1. ...
Điều 2. ...
1. ...
2. ...
3. ...
a)
b)
c)
```

Important note:

Vietnamese legal documents often do not literally contain the words `Khoản` and `Điểm` in the body text. Clauses are commonly represented as numbered lines:

```text
1. Nội dung khoản thứ nhất
2. Nội dung khoản thứ hai
```

Points are commonly represented as lettered lines:

```text
a) Nội dung điểm a
b) Nội dung điểm b
```

Therefore, marker detection should include pattern-based checks:

```text
Article marker:
Điều\s+\d+

Clause numbering:
^\s*\d+\.

Point labeling:
^\s*[a-zđ]\)
```

**Rules**:
- Preserve line breaks before article headings.
- Preserve line breaks before numbered clauses when possible.
- Preserve line breaks before lettered points when possible.
- Missing clause or point patterns should be a warning only when the document is expected to contain them.
- Missing article markers should always be a warning.

**Validation**:
- `article_count_estimate` is computed.
- `contains_article` is computed.
- `contains_clause_numbering` is computed.
- `contains_point_labeling` is computed.
- Missing `Điều` patterns are reported in the cleaning report.

### 8. Normalized JSON Writer

**Goal**: Write a structured normalized artifact for each legal document.

Primary output:

```text
data/interim/{LAW_ID}/normalized.json
```

Optional debug output:

```text
data/interim/{LAW_ID}/cleaned.txt
```

The normalized JSON must preserve:
- source traceability
- normalized legal text
- text statistics
- legal marker summary
- warnings
- cleaner metadata

### 9. Cleaning Report Writer

**Goal**: Produce a corpus-level report for cleaning quality and parsing readiness.

Output:

```text
data/reports/cleaning_report.json
```

This report is the validation gate for moving into Legal Hierarchy Parsing.

## Pipeline Execution Flow

1. Parse CLI arguments.
2. Discover raw artifacts from `data/raw`.
3. For each artifact:
   1. Resolve `main.html` and `metadata.json`.
   2. Load source metadata.
   3. Read `main.html` as UTF-8.
   4. Extract visible legal text from HTML.
   5. Remove safe boilerplate.
   6. Normalize Unicode.
   7. Normalize whitespace.
   8. Preserve legal boundaries and numbering patterns.
   9. Detect legal markers.
   10. Build normalized output object.
   11. Write `normalized.json`.
   12. Optionally write `cleaned.txt`.
4. Aggregate item-level statuses.
5. Write `cleaning_report.json`.
6. Print a compact CLI summary.

Example CLI summary:

```text
Cleaning & Normalization Summary
--------------------------------
Input artifacts:          52
Successfully cleaned:     52
Warning artifacts:        0
Failed artifacts:         0
Suspiciously short texts: 0
Missing article markers:  0
Output directory:         data/interim
Report:                   data/reports/cleaning_report.json
```

## Data Models / Output Schema

### Normalized JSON

Primary output:

```text
data/interim/{LAW_ID}/normalized.json
```

Schema:

```json
{
  "law_id": "BLDS_2015",
  "law_name": "Bộ luật Dân sự 2015",
  "source_url": "https://thuvienphapluat.vn/...",
  "source_domain": "thuvienphapluat.vn",
  "source_type": "html",
  "raw_artifact_path": "data/raw/BLDS_2015/latest/main.html",
  "normalized_text": "...",
  "text_stats": {
    "raw_html_size_bytes": 123456,
    "extracted_text_chars": 110000,
    "normalized_text_chars": 98765,
    "line_count": 3000
  },
  "markers": {
    "contains_part": false,
    "contains_chapter": true,
    "contains_section": true,
    "contains_article": true,
    "contains_clause_numbering": true,
    "contains_point_labeling": true,
    "article_count_estimate": 689
  },
  "warnings": [],
  "metadata": {
    "cleaner_version": "v0.1"
  }
}
```

### Cleaning Report

Output:

```text
data/reports/cleaning_report.json
```

Schema:

```json
{
  "summary": {
    "total_artifacts": 52,
    "successfully_cleaned": 52,
    "warning_artifacts": 0,
    "failed": 0,
    "suspiciously_short_texts": 0,
    "missing_article_marker": 0,
    "output_dir": "data/interim"
  },
  "items": [
    {
      "law_id": "BLDS_2015",
      "status": "success",
      "output_path": "data/interim/BLDS_2015/normalized.json",
      "normalized_text_chars": 98765,
      "line_count": 3000,
      "article_count_estimate": 689,
      "warnings": [],
      "errors": []
    }
  ]
}
```

### Optional Cleaned Text

Optional debug output:

```text
data/interim/{LAW_ID}/cleaned.txt
```

This file should contain only normalized legal text. It is useful for manual inspection but should not replace `normalized.json` as the primary pipeline artifact.

## CLI Reference

### Main Command

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report data/reports/cleaning_report.json
```

### Optional Arguments

```bash
--min-text-length 10000
```

Minimum normalized text length before an artifact is marked suspicious.

```bash
--write-txt
```

Write optional `cleaned.txt` files for manual debugging.

```bash
--verbose
```

Print item-level details.

### Example: Process All Laws

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report data/reports/cleaning_report.json \
  --write-txt
```

### Example: Development Run With Verbose Logging

```bash
uv run python scripts/clean_raw_corpus.py \
  --raw-dir data/raw \
  --output-dir data/interim \
  --report data/reports/cleaning_report.json \
  --min-text-length 10000 \
  --verbose
```

## Testing

Tests should be placed in:

```text
tests/unit/ingestion/test_cleaning.py
```

Use `tmp_path`. Do not use network calls. Do not depend on real `data/raw`.

### Required Unit Tests

- `test_remove_script_style_noscript()`
- `test_unicode_normalization_to_nfc()`
- `test_remove_zero_width_characters()`
- `test_normalize_non_breaking_spaces()`
- `test_collapse_excessive_whitespace()`
- `test_preserve_article_heading()`
- `test_preserve_clause_numbering()`
- `test_preserve_point_labeling()`
- `test_detect_legal_markers()`
- `test_generate_normalized_json()`
- `test_generate_cleaning_report()`
- `test_warn_when_text_is_suspiciously_short()`
- `test_warn_when_article_marker_missing()`
- `test_warn_when_replacement_character_found()`
- `test_handle_missing_main_html_gracefully()`
- `test_handle_invalid_or_unreadable_html_gracefully()`

### Integration Test

A lightweight integration test may use a small synthetic HTML page that mimics a TVPL legal document.

It should verify:

```text
raw HTML
→ extracted text
→ normalized text
→ normalized.json
→ cleaning_report.json
```

without touching real network resources.

## Error Handling

| Error | Behavior |
|------|----------|
| Missing `main.html` | Mark artifact as failed; continue other artifacts |
| Missing `metadata.json` | Mark artifact as failed; continue other artifacts |
| Invalid metadata JSON | Mark artifact as failed; include error in report |
| HTML read error | Mark artifact as failed; include path and exception |
| HTML parse error | Attempt robust parsing; if unrecoverable, mark failed |
| Text suspiciously short | Mark as warning, not failure |
| Missing article marker | Mark as warning, not failure |
| Replacement character found | Mark as warning |
| Output directory not writable | Fail fast with clear error |
| Report writing failure | Fail fast with clear error |

The cleaner should continue processing independent artifacts even if one law fails.

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|------|----------------|--------------|-----------------|
| `normalized_text` is empty | Extraction selected the wrong container or source HTML is invalid | Compare raw size and extracted text length | Improve extraction strategy or inspect audit report |
| Text is too short | Boilerplate removal too aggressive | Check `suspiciously_short_texts` in report | Relax boilerplate rules |
| `Điều` markers missing | Legal headings removed or extraction selected wrong area | Check `missing_article_marker` count | Preserve article heading lines and improve extraction |
| Clause numbering missing | Whitespace normalization merged numbered lines | Search for `1.` / `2.` patterns | Preserve line breaks before numbered clauses |
| Point labels missing | Cleaner removed lettered list structure | Search for `a)` / `b)` patterns | Preserve list item boundaries |
| Vietnamese text is corrupted | Encoding issue in raw HTML or decode stage | Search for `�` in normalized text | Add warning, review crawler encoding, avoid guessing corrections |
| HTML tags remain | Extraction did not strip markup correctly | Search for `<div`, `<span`, `<p` | Improve HTML text extraction |
| Too much boilerplate remains | Patterns too conservative | Inspect optional `cleaned.txt` | Add safe boilerplate rules |
| Parser fails downstream | Cleaning destroyed hierarchy boundary | Compare normalized text around `Điều` headings | Adjust legal boundary preservation rules |

## Best Practices

- Keep cleaning deterministic.
- Do not use LLM-based cleaning.
- Do not mutate `data/raw`.
- Run cleaning only after raw audit has passed.
- Prefer keeping minor boilerplate over deleting legal provisions.
- Preserve line boundaries around `Điều`, numbered clauses, and point labels.
- Use `normalized.json` as the primary artifact.
- Use `cleaned.txt` only as optional debug output.
- Track warnings instead of silently fixing uncertain text.
- Treat `�` as a warning, not as a string to guess-correct.
- Keep source metadata and traceability with every normalized artifact.
- Do not parse legal hierarchy in this phase.
- Do not create chunks in this phase.
- Do not embed or index text in this phase.

## Validation Gate

The Cleaning & Normalization phase is complete/gate-ready. Final validation
confirmed:

```text
52/52 valid audited artifacts produce normalized.json
52/52 optional cleaned.txt debug artifacts were generated in final validation
normalized_text is UTF-8 readable
article markers and Article 1 headings are preserved
article references and real article headings are separately reported
numbered clause patterns are preserved when present
point label patterns are preserved when present
no obvious HTML tags remain
known encoded TVPL footer/watermark artifacts are removed
cleaning_report.json is generated with no warning or failed artifacts
```

The next phase is Legal Hierarchy Parsing. Do not proceed directly to chunking,
embedding, RAG, Advanced RAG, or GraphRAG before parser correctness is validated.

## Changelog

### Version 0.8.0

- Completed the Phase 4 Cleaning & Normalization gate for the 52-law corpus.
- Added robust start trimming while preserving early Article 1 bodies.
- Added conservative line-fragment repair for Vietnamese legal text.
- Added block-aware TVPL HTML extraction so inline spans/fonts do not create
  artificial line breaks.
- Added targeted source-law/amendment pre-body note trimming.
- Removed known encoded TVPL footer/watermark artifact lines.
- Clarified article metrics:
  - `article_reference_count` counts all `Điều N` mentions.
  - `article_heading_count` counts real article heading lines.
  - `max_heading_article_number` reports the highest real heading number.
- Updated cleaner metadata to `cleaner_version` `v0.8.0`.

### Version 0.1

- Defined deterministic cleaning and normalization pipeline.
- Changed primary output from `cleaned.txt` to `normalized.json`.
- Added optional `cleaned.txt` debug artifact.
- Added corpus-level `cleaning_report.json`.
- Added Vietnamese legal marker preservation rules.
- Clarified that clause and point structures are often represented by `1.`, `2.`, `a)`, `b)` rather than literal words `Khoản` and `Điểm`.
- Added Unicode, whitespace, metadata, and traceability requirements.
- Added validation gate for Legal Hierarchy Parsing readiness.

## Related Documentation

| Document | Status | Description |
|----------|--------|-------------|
| `docs/end_to_end_pipeline.md` | Existing | High-level project pipeline overview |
| `docs/crawling.md` | Existing | Registry-driven crawling implementation |
| `docs/project_setup.md` | Existing | Environment setup and coding standards |
| `docs/corpus_registry.md` | Existing | Corpus registry schema and design |
| `docs/raw_corpus_audit.md` | Existing | Raw artifact audit and validation |
| `docs/legal_parsing.md` | Planned | Legal hierarchy parsing algorithm |
| `docs/parent_child_chunking.md` | Planned | Parent-child chunking design |
| `docs/processed_jsonl.md` | Planned | JSONL export schema and validation |
