# Raw Corpus Audit & Validation System

## Overview

The Raw Corpus Audit & Validation phase ensures that crawled artifacts are complete, correct, and ready for downstream processing. Crawling success alone is not sufficient — we must verify that each of the 52 `law_id` directories contains valid HTML content, accurate metadata, and traceable source URLs.

Audit happens **after crawling** and **before cleaning/normalization**. It is a mandatory validation gate that prevents corrupted, empty, or error-page artifacts from entering the pipeline.

## Why Audit Matters

Crawling can produce artifacts that look valid but are actually:
- Empty or near-empty HTML (blocked by captcha, login wall, error page)
- Wrong `law_id` due to crawler bug
- Missing metadata or mismatched `source_url`
- Non-UTF-8 encoded files
- Garbled Vietnamese text (encoding issues)

If these artifacts pass undetected, they will cause parsing failures, broken citations, and invalid chunks later. Audit catches these issues early with deterministic checks.

## Quick Start

**Implemented CLI**:

```bash
uv run python scripts/corpus/audit_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --output artifacts/reports/audit/raw_corpus_audit.json
```

The script reads the registry, scans `data/raw/{law_id}/latest/`, validates `main.html` and `metadata.json`, and produces an audit report.

## Architecture
`scripts/corpus/audit_raw_corpus.py` (CLI) $\rightarrow$ `src/services/raw_audit_service.py` (Orchestration) $\rightarrow$ `src/ingestion/audit.py` (Domain Logic)

```
┌──────────────────────┐
│  Corpus Registry     │
│  (52 law_id entries) │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Registry Law ID     │
│  Loader              │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Raw Artifact        │
│  Scanner             │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Metadata Validator  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  HTML Validator      │
│  (size, encoding)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Error Page Detector │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Legal Text Marker   │
│  Checker             │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Audit Report        │
│  Writer (JSON)       │
└──────────────────────┘
```

## Components

### 1. Registry Law ID Loader

Loads all `law_id` values from `configs/laws/corpus_registry.yml`. This is the authoritative list of expected artifacts.

**Output**: Set of 52 law identifiers.

**Validation**: Count must be exactly 52. All `law_id` must match pattern (e.g., `[A-Z_]+_\d{4}`).

### 2. Raw Artifact Scanner

Scans `data/raw/` directory structure.

**Expected layout**:
```
data/raw/
└── {law_id}/
    └── latest/
        ├── main.html
        └── metadata.json
```

**Checks**:
- `{law_id}` directory exists for every registry entry.
- `latest/` subdirectory exists.
- `main.html` exists and is a regular file.
- `metadata.json` exists and is a valid JSON file.

### 3. Metadata Validator

Reads `metadata.json` and validates:

- `law_id` matches registry entry.
- `name` matches registry entry name (case-insensitive allowed).
- `source_domain` contains `thuvienphapluat.vn`.
- `url` matches the registry `url` (exact string match).
- `crawl_status` is `"success"`.
- `content_hash` is non-empty (SHA256 or similar).
- Required keys: `law_id`, `name`, `source_domain`, `source_type`, `url`, `crawl_status`, `crawled_at`, `content_hash`.

**Failure conditions**:
- Missing required key.
- `law_id` mismatch → indicates crawler saved to wrong directory.
- `source_domain` not trusted.
- `url` mismatch → crawler used different URL than registry.

### 4. HTML Validator

Validates `main.html` file:

- File size > 1KB (reject empty or placeholder pages).
- File is readable as UTF-8 (no decoding errors).
- File size > 10KB is expected for full law text; warnings for 1–10 KB.
- No null bytes in first 1KB (indicates binary or corrupted).

**Note**: The auditor does **not** read or interpret HTML content beyond encoding and size checks.

### 5. Error Page Detector

Detects obvious error pages without parsing HTML content (per restrictions). Heuristics:

- File size < 2KB → likely error page (captcha, login, 404).
- File contains common error strings in first 500 bytes (e.g., "404 Not Found", "captcha", "access denied", "bạn cần đăng nhập").
- If size > 2KB but < 5KB, flag for manual review (suspicious).

This is a best-effort detection; low false positive rate is acceptable.

### 6. Legal Text Marker Checker

Quick sanity check: does the file contain Vietnamese legal markers?

Search for at least one occurrence of:
- "Điều" (Article)
- "Luật" (Law)
- "Bộ luật" (Code)

in the first 2KB. If none found, flag as `warnings` (not necessarily invalid, but unusual).

This helps catch completely non-legal HTML that somehow passed crawling.

### 7. Audit Report Writer

Produces `artifacts/reports/audit/raw_corpus_audit.json` with structured results.

## Pipeline Execution Flow

1. Load registry → extract 52 `law_id` values.
2. For each `law_id`:
   - Check `data/raw/{law_id}/latest/` exists.
   - Verify `main.html` presence and basic validity (size, UTF-8).
   - Load `metadata.json` and validate fields against registry.
   - Run error page detection on HTML.
   - Run legal text marker check.
   - Record status: `valid`, `invalid`, or `warning`.
3. Summarize counts: total registry entries, raw artifacts found, valid/invalid count, missing, extra.
4. Write JSON report.

## Data Models / Output Schema

### Audit Report Schema

```json
{
  "summary": {
    "registry_entries": 52,
    "raw_artifacts_found": 52,
    "valid_artifacts": 52,
    "invalid_artifacts": 0,
    "missing_artifacts": 0,
    "extra_artifacts": 0,
    "missing_main_html": 0,
    "missing_metadata_json": 0,
    "invalid_metadata_json": 0,
    "suspicious_small_html": 0,
    "possible_error_pages": 0
  },
  "missing_in_raw": [],
  "extra_in_raw": [],
  "items": [
    {
      "law_id": "BLDS_2015",
      "status": "valid",
      "artifact_dir": "data/raw/BLDS_2015/latest",
      "main_html_exists": true,
      "metadata_json_exists": true,
      "html_size_bytes": 123456,
      "metadata_valid": true,
      "source_url": "https://thuvienphapluat.vn/...",
      "issues": [],
      "warnings": []
    },
    {
      "law_id": "LLP_2022",
      "status": "invalid",
      "artifact_dir": "data/raw/LLP_2022/latest",
      "main_html_exists": true,
      "metadata_json_exists": false,
      "html_size_bytes": 543,
      "metadata_valid": null,
      "source_url": null,
      "issues": [
        "missing_metadata_json"
      ],
      "warnings": [
        "html_size_suspiciously_small",
        "likely_error_page"
      ]
    }
  ]
}
```

**Status values**:
- `valid`: All checks passed, no issues.
- `invalid`: One or more critical issues (missing files, metadata mismatch, invalid JSON).
- `warning`: Passed but with non-critical concerns (small HTML, missing legal markers).

**Issue codes**:
- `missing_main_html`
- `missing_metadata_json`
- `invalid_metadata_json` (JSON parse error)
- `metadata_law_id_mismatch`
- `metadata_url_mismatch`
- `metadata_source_domain_untrusted`
- `html_not_utf8`
- `html_size_suspiciously_small`
- `likely_error_page`
- `no_legal_markers` (warning only)

### Success Criteria

Audit passes if:
- `summary["missing_artifacts"] == 0`
- `summary["extra_artifacts"] == 0`
- `summary["invalid_artifacts"] == 0`
- All 52 registry entries have `status: "valid"`

Any `invalid` items block progression to cleaning/normalization. `warning` items may proceed but should be reviewed.

## CLI Reference

### `scripts/corpus/audit_raw_corpus.py`

**Implemented interface**:

```bash
uv run python scripts/corpus/audit_raw_corpus.py \
  --registry configs/laws/corpus_registry.yml \
  --raw-dir data/raw \
  --output artifacts/reports/audit/raw_corpus_audit.json
```

**Arguments**:
- `--registry`: Path to corpus registry YAML (default: `configs/laws/corpus_registry.yml`)
- `--raw-dir`: Root directory containing `{law_id}` folders (default: `data/raw`)
- `--output`: Output JSON report path (default: `artifacts/reports/audit/raw_corpus_audit.json`)

**Exit codes**:
- `0`: Audit passed (zero invalid, zero missing).
- `1`: Audit failed (critical issues found).
- `2`: Usage error or exception.

## Testing

**Unit tests**:
- `test_metadata_validator()`: valid metadata passes, mismatched `law_id` fails.
- `test_html_validator()`: UTF-8 detection, size thresholds.
- `test_error_page_detection()`: known error page patterns detected.

**Integration test**:
- Given a known-good `data/raw/` with 52 entries, `audit_raw_corpus.py` returns `summary.valid_artifacts == 52` and exit code 0.
- Given missing directory, report includes `missing_in_raw` and exit code 1.
- Given corrupted `metadata.json`, report includes `invalid_metadata_json`.

## Error Handling

- **Registry not found**: `FileNotFoundError`; exit 2.
- **YAML parse error**: `yaml.YAMLError`; exit 2 with error message.
- **Output directory not writable**: `OSError`; exit 2.
- **Individual artifact errors**: logged per-item; do not abort entire audit.

All errors are captured in the JSON report's `items[].issues` list.

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| Audit reports missing artifacts | Crawl incomplete or wrong `raw-dir` | Verify `data/raw/` has 52 subdirectories | Rerun crawler for missing `law_id`; check `--raw-dir` path |
| All items show `metadata_json_exists: false` | Metadata not written by crawler | Inspect `data/raw/{law_id}/latest/` | Fix crawler to output `metadata.json`; check permissions |
| `metadata_law_id_mismatch` for many laws | Crawler used wrong `law_id` when saving | Compare `metadata.json["law_id"]` vs directory name | Fix crawler logic to use registry `law_id` consistently |
| `likely_error_page` for a specific law | Site blocked crawl (captcha, rate limit) | Download HTML manually to inspect | Adjust crawler headers, rate limits; may need manual review |
| `html_not_utf8` | Encoding detection failed | Run `file -I data/raw/{law_id}/latest/main.html` | Ensure crawler saves as UTF-8; recrawl if necessary |
| Audit exit code 0 but warnings present | Small HTML or missing legal markers | Review `warnings` array in report | Manually inspect suspicious artifacts; may be acceptable |

## Best Practices

- **Never skip audit** — treat it as a mandatory gate; do not proceed to cleaning if any `invalid` items exist.
- **Run audit immediately after crawling** — catch issues while crawl context is fresh.
- **Review warnings** — while not blocking, warnings indicate potential quality issues that deserve human review.
- **Keep audit report in version control?** No — generated files under `artifacts/reports/audit/` should be gitignored; regenerate after each crawl.
- **Idempotency** — running audit twice on same raw corpus should produce identical reports (deterministic checks).
- **Fail fast on missing registry** — if registry file is missing, abort immediately; do not guess.

## Changelog

### Version 0.1 (2026-05-21)

- Created initial raw corpus audit documentation.
- Defined audit components: registry loader, artifact scanner, metadata validator, HTML validator, error detector, legal text marker.
- Specified audit report JSON schema with summary and per-item details.
- Provided success criteria (52 valid artifacts, zero missing/invalid).
- Documented intended CLI interface and testing strategy.
- Added troubleshooting for common audit failures.

## Related Documentation

| Document | Status | Description |
|----------|--------|-------------|
| `docs/project_phase_journal.md` | Existing | Project phase journal and pipeline notes |
| `docs/project_setup.md` | Implemented | Environment setup and coding standards |
| `docs/corpus_registry.md` | Implemented | Corpus registry schema and design |
| `docs/cleaning_normalization.md` | Existing | HTML-to-text and Unicode normalization |
| `docs/legal_parsing.md` | Existing | Legal hierarchy parsing algorithm |
