# Phase 7 Processed Chunk Validation Plan

## Objective

Validate `data/processed/legal_chunks.jsonl` as a hierarchy-preserving,
citation-traceable, and embedding-ready corpus before Phase 8 indexing begins.

## Progress

- [x] Slice 1: validation models, configuration, issue codes, and report structures.
- [x] Slice 2: streaming JSONL parsing, schema/required-field checks, uniqueness,
  per-line validity counts, and level/law distributions.
- [x] Slice 3A: `text` and `parent_text` hash integrity validation.
- [x] Slice 3B: count reconciliation against the Phase 6 chunking report.
- [ ] Slice 3C and later: not started.

## Slice 3B Result

- `total_chunks` is reconciled against JSONL `total_lines`.
- Optional `chunks_by_level` report entries are reconciled as hard failures.
- Optional `chunks_by_law` law-count differences are warning-only.
- Missing, unreadable, invalid, incomplete, or malformed report data produces
  structured warnings without changing per-line valid/invalid chunk counts.
- No separate count-reconciliation source or test module was created.

## Changed Files

- `src/processing/processed_jsonl_validator.py`
- `tests/unit/processing/test_processed_jsonl_validator.py`
- `phase7_processed_chunk_validation_plan.md`

## Verification

- [x] Python compilation passed.
- [x] Phase 7 model and validator tests passed: 83 tests.
- [x] Ruff lint passed.
- [x] Ruff format check passed.
- [x] Git diff whitespace check passed.
- [x] Protected data and generated report paths remained unchanged.

Commands:

```bash
uv run python -m py_compile src/processing/processed_jsonl_validator.py
uv run pytest tests/unit/processing/test_processed_jsonl_validation_models.py tests/unit/processing/test_processed_jsonl_validator.py -q
uv run ruff check src/processing/processed_jsonl_validation_models.py src/processing/processed_jsonl_validator.py tests/unit/processing/test_processed_jsonl_validation_models.py tests/unit/processing/test_processed_jsonl_validator.py
uv run ruff format --check src/processing/processed_jsonl_validation_models.py src/processing/processed_jsonl_validator.py tests/unit/processing/test_processed_jsonl_validation_models.py tests/unit/processing/test_processed_jsonl_validator.py
git diff --check
git status --short data/raw data/interim data/reports data/processed artifacts/reports
git status --short
```
