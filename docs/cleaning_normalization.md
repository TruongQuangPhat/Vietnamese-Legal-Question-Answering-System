# Cleaning & Normalization Pipeline

## Overview

The Cleaning & Normalization phase transforms raw HTML artifacts into clean, UTF-8 encoded Vietnamese legal text while preserving the legal hierarchy boundaries (Điều, Khoản, Điểm). This stage prepares text for the Legal Hierarchy Parser by removing boilerplate, normalizing Unicode, and maintaining structural markers.

Cleaning is deterministic and stateless — the same input always produces the same output. This ensures reproducibility and enables incremental processing.

## Quick Start

**Intended CLI** (design phase, not yet implemented):

```bash
uv run python -m src.processing.cleaner \
  --input-dir data/raw \
  --output-dir data/interim \
  --law-ids BLDS_2015 LDD_2024  # or omit for all 52
```

**Expected workflow**:
1. Input: `data/raw/{law_id}/latest/main.html`
2. Output: `data/interim/{law_id}/cleaned.txt` (or `cleaned.json` with offsets)
3. Logs: structured JSON with cleaning statistics (boilerplate removed, characters normalized).

## Architecture

```
┌──────────────────────┐
│  Raw HTML Artifact   │
│  (from crawler)      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  HTML Content        │
│  Extraction          │
│  (remove script/style)│
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Boilerplate         │
│  Removal             │
│  (nav, ads, footer)  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Unicode             │
│  Normalization       │
│  (NFC, Vietnamese)   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Whitespace          │
│  Normalization       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Legal Boundary      │
│  Preservation        │
│  (Điều/Khoản/Điểm)   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Normalized Legal    │
│  Text                │
└──────────────────────┘
```

## Components

### 1. HTML Content Extraction

**Input**: Raw HTML file from `data/raw/{law_id}/latest/main.html`.

**Process**:
- Parse HTML with `lxml` or `html5lib` (robust to malformed markup).
- Extract text content while discarding:
  - `<script>`, `<style>` blocks
  - Navigation menus, sidebars, footers
  - Advertisements, pop-ups
  - Forms, buttons
- Preserve semantic structure where possible (headings, paragraphs, lists).

**Output**: Plain text with basic structure (newlines, indentation).

**Validation**:
- Extracted text length > 1KB (non-empty).
- No leftover HTML tags in text (except entities converted to characters).

### 2. Boilerplate Removal

**Goal**: Remove repetitive non-legal content that appears on all pages.

**Targets**:
- Header/footer text: "Thu viện pháp luật", "Hotline", "Đăng nhập"
- Navigation links: "Trang chủ", "Tìm kiếm", "Liên hệ"
- Copyright notices, timestamps
- Promotional content

**Method**:
- Pattern-based removal (regex) for known boilerplate strings.
- Optional: use a boilerplate detection library (e.g., `readability-lxml`).
- Preserve any content that appears to be legal text (contains "Điều", "Luật", "Bộ luật").

**Validation**:
- Post-clean text still contains legal markers ("Điều", "Khoản", "Điểm").
- Boilerplate removal reduces text size by expected amount (10–30%).

### 3. Unicode Normalization

**Goal**: Ensure consistent Vietnamese diacritics and prevent garbled characters.

**Process**:
- Apply Unicode NFC normalization (composed form).
- Fix common encoding errors:
  - Replace mis-encoded Vietnamese characters (e.g., "t�i" → "tải")
  - Normalize combining diacritics
- Remove zero-width characters (`​`, `‌`, `‍`, `﻿`).
- Validate UTF-8; if decode fails, attempt recovery with `errors='replace'` and log warning.

**Validation**:
- Text is valid UTF-8.
- No control characters in [0x00–0x1F] except allowed whitespace (`\n`, `\t`, `\r`).
- Vietnamese diacritics render correctly (spot-check common words: "pháp", "luật", "nhà nước").

### 4. Whitespace Normalization

**Goal**: Consistent spacing without collapsing legal structure.

**Process**:
- Collapse multiple consecutive spaces into single space.
- Normalize newlines: convert `\r\n` and `\r` to `\n`.
- Trim leading/trailing whitespace on each line.
- Preserve paragraph breaks (detect multiple newlines as paragraph separators).
- Remove trailing whitespace at line ends.

**Validation**:
- No tabs (`\t`) remaining (converted to spaces).
- No more than 2 consecutive newlines (paragraph boundary).
- No lines with only whitespace.

### 5. Legal Boundary Preservation

**Goal**: Keep Vietnamese legal heading markers intact and detectable.

**Critical markers** (must survive cleaning):
- "Điều" followed by number (e.g., "Điều 123")
- "Khoản" followed by number or letter (e.g., "Khoản 2", "Khoản a")
- "Điểm" followed by letter (e.g., "Điểm a", "Điểm b")
- "Phần", "Chương", "Mục" with their numbers/titles

**Enforcement**:
- Do not split lines at these markers arbitrarily.
- Ensure markers are on their own line or clearly separated by whitespace.
- If boilerplate removal accidentally deletes a marker, flag as warning.

**Validation**:
- At least one "Điều" pattern exists in cleaned text (regex: `r"Điều\s+\d+"`).
- All "Điều" occurrences are followed by content (not orphaned).

## Pipeline Execution Flow

1. Read raw HTML from `data/raw/{law_id}/latest/main.html`.
2. Extract text content (strip tags, keep visible text).
3. Remove boilerplate using pattern database.
4. Normalize Unicode (NFC, fix encoding, remove zero-width).
5. Normalize whitespace (collapse spaces, standardize newlines).
6. Verify legal markers present; if missing, log warning but continue.
7. Write to `data/interim/{law_id}/cleaned.txt` (UTF-8).
8. Optionally write `cleaned.json` with metadata (character offsets, statistics).

## Data Models / Output Schema

### Cleaned Text File (`cleaned.txt`)

Plain UTF-8 text file. Example excerpt:

```
Luật Đất đai 2024

Điều 1. Phạm vi điều chỉnh

Luật này quy định về quản lý nhà nước đối với đất đai, quyền và nghĩa vụ của Nhà nước, tổ chức, cá nhân có liên quan đến đất đai.

Điều 2. Giải thích thuật ngữ

Trong Luật này, các thuật ngữ được giải thích như sau:
1. "Đất đai" bao gồm đất mặt tiền, đất nền...
2. "Quyền sử dụng đất" là quyền của tổ chức, cá nhân...
```

### Optional Cleaned JSON (`cleaned.json`)

If metadata offsets are needed for downstream parsing:

```json
{
  "law_id": "LDD_2024",
  "source_file": "data/raw/LDD_2024/latest/main.html",
  "cleaning_stats": {
    "original_size_bytes": 456789,
    "cleaned_size_bytes": 345678,
    "boilerplate_removed_bytes": 111111,
    "normalization_issues_fixed": 0,
    "warnings": []
  },
  "paragraph_offsets": [
    {"start": 0, "end": 125, "text": "Luật Đất đai 2024\n"},
    {"start": 126, "end": 289, "text": "Điều 1. Phạm vi điều chỉnh\n"}
  ]
}
```

## CLI Reference

### Intended Main Command

```bash
uv run python -m src.processing.cleaner \
  --input-dir data/raw \
  --output-dir data/interim \
  [--law-ids LAW_ID [LAW_ID ...]] \
  [--format txt|json] \
  [--log-level INFO]
```

**Arguments**:
- `--input-dir`: Root directory containing `{law_id}/latest/main.html` (default: `data/raw`)
- `--output-dir`: Where to write `cleaned.txt` or `cleaned.json` (default: `data/interim`)
- `--law-ids`: Specific laws to process; if omitted, process all found in input dir.
- `--format`: Output format (`txt` for plain text, `json` for enriched).
- `--log-level`: Logging verbosity.

## Testing

**Unit tests**:
- `test_unicode_normalization()`: Vietnamese diacritics preserved, NFC applied.
- `test_whitespace_normalization()`: tabs → spaces, newlines normalized, trailing whitespace removed.
- `test_boilerplate_removal()`: known boilerplate strings removed, legal text retained.
- `test_legal_marker_detection()`: regex finds "Điều \d+", "Khoản \d+", "Điểm [a-z]".

**Integration test**:
- Given a sample raw HTML from the corpus, cleaner produces `cleaned.txt` > 1KB.
- Cleaned text contains at least one "Điều" pattern.
- Cleaned text is valid UTF-8; `open(..., encoding="utf-8")` succeeds.

## Error Handling

- **HTML parse error**: Log warning, attempt recovery with different parser; if fails, mark artifact as `invalid`.
- **File not found**: Raise `FileNotFoundError` with clear message; abort processing for that `law_id`.
- **Output directory not writable**: `OSError`; abort.
- **Unicode decode error**: Attempt `errors='replace'`, log warning, continue.

All errors include `law_id` and file path in structured log.

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| Cleaned text < 1KB | Boilerplate removal too aggressive OR source HTML was empty | Compare original HTML size; spot-check content | Adjust boilerplate patterns; ensure source HTML is valid |
| Vietnamese diacritics corrupted | Unicode normalization failed or wrong encoding | Look for "t�i", "ph�p" in output | Ensure UTF-8 throughout; fix source encoding in crawler |
| No "Điều" found in output | Legal marker removed by boilerplate remover | Search for "Điều" in original HTML | Refine boilerplate patterns to preserve legal headings |
| Many zero-width chars remain | Normalization step skipped or incomplete | Check for `​` in output | Ensure zero-width char removal runs |
| Output file empty | Write error or permission issue | Check file size on disk | Verify output directory permissions; check disk space |
| Parser downstream fails | Cleaning produced unexpected line breaks | Inspect `cleaned.txt` manually | Adjust whitespace normalization rules |

## Best Practices

- **Determinism** — same input must produce identical output every time.
- **Preserve legal markers** — never remove "Điều", "Khoản", "Điểm" even if they appear in boilerplate; better to keep false positive than lose structure.
- **Log statistics** — track bytes removed, normalization fixes applied; aids debugging.
- **Validate early** — run marker detection after cleaning; if zero markers found, flag immediately.
- **Keep intermediate files** — `data/interim/` may be kept for audit; document their purpose.
- **Stateless operation** — cleaner should not depend on previous runs or external state.

## Changelog

### Version 0.1 (2026-05-21)

- Created initial cleaning & normalization documentation.
- Defined components: HTML extraction, boilerplate removal, Unicode normalization, whitespace cleanup, legal boundary preservation.
- Provided pipeline box diagram and intended CLI.
- Specified output formats (txt, optional json with offsets).
- Documented validation criteria and testing strategy.
- Added troubleshooting for common cleaning failures.

## Related Documentation

| Document | Status | Description |
|----------|--------|-------------|
| `docs/crawling.md` | Existing | Registry-driven crawling implementation |
| `docs/project_setup.md` | Implemented | Environment setup and coding standards |
| `docs/corpus_registry.md` | Implemented | Corpus registry schema and design |
| `docs/raw_corpus_audit.md` | Designed | Raw artifact audit procedure |
| `docs/legal_parsing.md` | Planned | Legal hierarchy parsing algorithm |
| `docs/parent_child_chunking.md` | Planned | Parent-child chunking design |
| `docs/processed_jsonl.md` | Planned | JSONL export schema and validation |
