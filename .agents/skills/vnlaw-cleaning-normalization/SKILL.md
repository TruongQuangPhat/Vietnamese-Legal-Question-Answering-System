---
name: vnlaw-cleaning-normalization
description: Use for Vietnamese legal text cleaning, Unicode normalization, whitespace normalization, OCR issue handling, HTML cleanup, and normalization tests before legal parsing.
---

# Cleaning and Normalization Skill

Use this skill before legal parsing or chunking.

## Current Status

Phase 4 Cleaning & Normalization is complete/gate-ready. The final validated
corpus has 52/52 `normalized.json` artifacts and 52/52 optional `cleaned.txt`
debug artifacts. Cleaner outputs use `cleaner_version` `v0.8.0`, remove known
encoded TVPL footer/watermark artifacts, and report article references
separately from real article headings.

Use this skill for maintenance or regression fixes in cleaning. Phase 5 Legal
Hierarchy Parsing and Phase 6 Parent-child Chunking are complete and hardened;
Phase 7 validation and Phase 7.5 semantic audit are complete. Do not expand
cleaning work unless a downstream-blocking defect is proven with direct-text
examples and regression tests.

## Purpose

Vietnamese legal text may contain encoding issues, non-breaking spaces, zero-width characters, inconsistent punctuation, HTML artifacts, and OCR-like spacing errors.

Normalize these issues without changing legal meaning or destroying legal hierarchy.

## Core Rules

- Preserve legal wording.
- Preserve Article, Clause, and Point markers.
- Preserve hierarchy boundaries.
- Preserve numbering.
- Preserve Vietnamese diacritics.
- Normalize whitespace carefully.
- Normalize Unicode to NFC unless a test proves otherwise.
- Keep normalization deterministic and tested.

## Must Preserve

Normalized text must preserve markers such as:

```text
PHẦN
CHƯƠNG
MỤC
Điều 1.
1.
a)
đ)
```

Do not collapse the whole document into one line before parsing.

## Normalization Pattern

```python
NORMALIZE_MAP = {
    "Đ iều": "Điều",
    "Kho ản": "Khoản",
    "\u200b": "",
    "\xa0": " ",
}
```

Use Unicode normalization:

```python
import unicodedata

text = unicodedata.normalize("NFC", text)
```

## Expected Components

```text
src/ingestion/cleaning.py
src/ingestion/cleaning_diagnostics.py
src/services/cleaning_service.py
src/services/cleaning_quality_audit_service.py
scripts/corpus/clean_raw_corpus.py
scripts/corpus/audit_cleaning_quality.py
tests/unit/ingestion/test_cleaning.py
```

Recommended functions/classes:

```text
extract_legal_text_from_html
extract_text_with_block_boundaries
normalize_unicode
normalize_whitespace
repair_line_fragments
trim_to_legal_body
remove_encoded_footer_artifacts
compute_cleaned_text_markers
```

## OOP and Docstring Rules

- Use a small focused normalizer class or pure functions with clear contracts.
- Public functions/classes must have Google-style docstrings.
- Docstrings must state what is preserved and what is modified.
- Add examples for tricky Vietnamese legal markers.

## Tests

Add tests for:

- Vietnamese diacritics;
- letter `đ`;
- Roman numerals;
- non-breaking spaces;
- zero-width spaces;
- broken legal markers;
- HTML entities;
- Article/Clause/Point boundaries;
- line breaks required for hierarchy detection.

## Do Not

- Do not translate legal text.
- Do not alter statute wording.
- Do not remove numbering.
- Do not merge legal units that must remain separate.
- Do not remove line breaks needed for hierarchy detection.
- Do not apply aggressive cleanup without regression tests.
