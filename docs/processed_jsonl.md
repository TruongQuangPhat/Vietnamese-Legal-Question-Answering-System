# Phase 7 — Processed Chunk Validation & Embedding Readiness

## Overview

Phase 7 validates the Phase 6 corpus-level JSONL output as a safe input for
Phase 8 embedding/indexing. Phase 6 already writes the processed chunk file:

```text
data/processed/legal_chunks.jsonl
```

Phase 7 treats that file as the canonical chunk corpus and verifies that it
is safe for embedding/indexing. It does not recrawl, reclean, reparse, or
rechunk legal text unless a proven upstream blocker is separately approved.
Phase 7 does not implement embedding or indexing — it is a validation gate.

Current result: Phase 7 is complete with 40,389 valid chunks, 0 invalid
chunks, 0 hard errors, and 8,206 accepted non-blocking warnings. The warning
follow-up W1-W3 is closed. The Phase 7.5 semantic audit records a
**Go with watch items** decision in `docs/phase75_llm_corpus_audit.md`.

## Current Input

Validated Phase 6 output:

```text
data/processed/legal_chunks.jsonl
artifacts/reports/chunking/chunking_report.json
artifacts/reports/chunking/full_corpus_validation_report.json
```

Phase 6 validation result:

```text
Laws: 52
Chunks: 40,389
Success with warnings: 18
Failed laws: 0
Empty/repealed chunks: 180
Source-tail markers: 0 in text, 0 in parent_text
Max parent_text length: 14,481 chars
Bad JSONL lines: 0
Duplicate chunk_id: 0
Selection-rule issues: 0
Chunk invariant issues: 0
```

Chunk breakdown:

```text
Article chunks:    1,322
Clause chunks:    20,643
Point chunks:     18,424
Total:            40,389
```

## Validation Goals

Phase 7 confirms the following across the full corpus:

1. Every JSONL line parses as valid JSON.
2. Every row validates as a `LegalChunk` Pydantic model.
3. All required fields are present and non-empty.
4. `chunk_id` is globally unique across the corpus.
5. Report counts reconcile with JSONL row counts.
6. `text_hash` and `parent_text_hash` match SHA-256 of the respective fields.
7. Citations are structurally consistent by chunk level.
8. `source_node_id` and `parent_article_node_id` remain traceable to hierarchy.
9. `text` is the intended embedding content; `parent_text` is retained as Article context.
10. No hard-fail contamination markers are present in `text` or `parent_text`.

## Expected Phase 7 Output

Recommended report path:

```text
artifacts/reports/chunking/processed_jsonl_validation_report.json
```

Recommended report fields:

```text
schema_version
started_at
finished_at
duration_seconds
input_path
chunking_report_path
hierarchy_dir
total_lines
valid_chunks
invalid_chunks
duplicate_chunk_ids
chunks_by_level
chunks_by_law
required_field_failures
hash_mismatches
citation_failures
contamination_failures
contamination_warnings
long_parent_text_summary
repealed_metadata_summary
warnings
errors
```

Phase 7 may also write diagnostic artifacts under:

```text
artifacts/runs/phase7_processed_chunk_validation/
```

## Embedding-Readiness Contract

Phase 8 embedding/indexing must use:

```text
embedding input:  chunk.text
retrieval payload: chunk.parent_text
```

- Embed only `chunk.text`. Do not embed `parent_text` as the primary vector text.
- `parent_text` can be very long (max 14,481 chars in current corpus) and is
  meant for downstream LLM context once a child chunk has been retrieved.
- Do not apply generic text splitters or LangChain splitters to
  `legal_chunks.jsonl`. If LangChain is used later, wrap each JSONL row as a
  Document; do not split it again.

## Payload-Readiness Contract

Phase 8 vector index payload should carry at minimum:

```text
chunk_id
law_id
law_name
level
article_number
clause_number (nullable)
point_label (nullable)
citation
hierarchy_path
source_node_id
parent_article_node_id
parent_chunk_id
text_hash
parent_text_hash
metadata.is_empty_or_repealed
metadata.is_source_unit_repealed
metadata.source_warnings
metadata.caveat_references
```

Preserve `metadata.is_empty_or_repealed` and `metadata.is_source_unit_repealed`
through indexing so retrieval can filter or annotate repealed content.

## Citation Validation Rules

Phase 7 validates **structural citation consistency by level**, not a fixed
law-name/year ordering pattern. The existing Phase 6 citation format is
law-name-first and may vary for VBHN/consolidated texts.

Validation rules:

- **Article chunks** (`level == "article"`): citation must contain
  `Điều {article_number}`.
- **Clause chunks** (`level == "clause"`): citation must contain
  `Khoản {clause_number}` and `Điều {article_number}`.
- **Point chunks** (`level == "point"`): citation must contain
  `Điểm {point_label}`, `Khoản {clause_number}`, and `Điều {article_number}`.

Do not require a fixed law-name/year ordering. Do not fail citations that use
VBHN/consolidated naming conventions.

## Contamination Marker Policy

Split contamination markers into two severity classes:

### Hard-fail markers (validation fails if found in `text` or `parent_text`)

- `XÁC THỰC VĂN BẢN HỢP NHẤT`
- `Nơi nhận:`
- `Lưu:`
- `Văn bản này được hợp nhất`

### Warning-only markers (emitted as warnings, do not fail validation)

- `BỘ TRƯỞNG`
- `CHỦ NHIỆM`
- `CHỦ TỊCH QUỐC HỘI`
- `TM. QUỐC HỘI`
- `KT. BỘ TRƯỞNG`

Warning-only markers must not fail validation automatically because they may
appear in valid legal content (e.g., signature blocks in law texts).

## Long `parent_text` Policy

Phase 6 preserves whole Article context in `parent_text`. Phase 7 measures
and classifies `parent_text` length for downstream context packing:

- **Short** (`parent_text` <= 4,000 chars): no special handling needed.
- **Medium** (4,001–10,000 chars): standard LLM context window.
- **Long** (10,001–20,000 chars): may require truncation or summarization at
  retrieval time depending on the LLM context window.
- **Very long** (> 20,000 chars): flag for manual review; current corpus has
  0 such chunks.

Do not split `parent_text` arbitrarily. Context packing decisions belong to
Phase 9–10 retrieval/generation, not Phase 7.

## Repealed/Empty Metadata Policy

Phase 6 flags chunks with:

- `metadata.is_empty_or_repealed`: the source Article is empty, repealed, or a
  placeholder.
- `metadata.is_source_unit_repealed`: the selected source unit (Article, Clause,
  or Point) itself contains a repealed placeholder.

Phase 7 must:

- Count and report the distribution of these flags.
- Verify that all 180 empty/repealed chunks from Phase 6 are accounted for.
- Ensure these flags are preserved in the validation report for Phase 8
  filtering decisions.

## Non-goals

Phase 7 should not implement:

- embedding or vector generation;
- Qdrant collection setup or indexing;
- BM25 or sparse retrieval;
- reranking;
- Naive RAG, Advanced RAG, or GraphRAG;
- API endpoints or backend services;
- LLM generation or prompt engineering;
- legal text splitting or chunking.

## Proposed Files

Files to be created during Phase 7 implementation:

- `src/processing/processed_jsonl_validation_models.py` — Pydantic models for
  Phase 7 validation report and issue codes.
- `src/processing/processed_jsonl_validator.py` — Core validator: reads JSONL,
  validates each chunk, checks hashes, citations, contamination, uniqueness.
- `src/services/processed_jsonl_validation_service.py` — Orchestration service:
  runs validator, reconciles with Phase 6 report, writes validation report.
- `scripts/validate_processed_jsonl.py` — CLI entrypoint.
- `tests/unit/processing/test_processed_jsonl_validator.py` — Unit tests.
- `tests/unit/services/test_processed_jsonl_validation_service.py` — Service tests.
- `configs/processing/processed_jsonl_validation.yml` — Config: thresholds,
  paths, long-text limits, contamination markers.
- `docs/processed_jsonl.md` — This document.

## Implementation Slices

1. **Validation models/config** — Define `ProcessedJsonlValidationReport`,
   `ValidationIssueCode`, and config schema.
2. **Core JSONL validator** — Stream-parse JSONL, validate each row as
   `LegalChunk`, check required fields, uniqueness, hashes, offsets.
3. **Citation and contamination checks** — Structural citation validation by
   level; hard-fail and warning-only contamination marker detection.
4. **Report reconciliation** — Cross-check counts, level distribution, and
   law distribution against `chunking_report.json`.
5. **Embedding-readiness checks** — Verify `text`/`parent_text` contract,
   measure `parent_text` length distribution, flag very-long contexts.
6. **Report writer** — Serialize the complete Pydantic report as UTF-8 JSON.
7. **CLI** — argparse entrypoint with configurable paths, pretty/quiet modes,
   and explicit warning exit policy.
8. **Full corpus validation run** — Execute against 40,389 chunks, review
   report, update docs.

## Execution Progress

- [x] Step 1 - Documentation/context update
- [x] Step 2 - Validation models/config
- [x] Step 3 - Core JSONL validator
- [x] Step 4 - Report reconciliation and embedding-readiness checks
- [x] Step 5 - Report writer
- [x] Step 6 - CLI
- [x] Step 7 - Full corpus validation run
- [x] Step 8 - Docs/context final update

## Commands

Run Phase 6 chunking first if outputs need to be regenerated:

```bash
uv run python scripts/chunk_legal_corpus.py \
  --input-dir data/interim \
  --output data/processed/legal_chunks.jsonl \
  --report artifacts/reports/chunking/chunking_report.json \
  --overwrite \
  --verbose \
  --no-color
```

Run Phase 7 validation:

```bash
uv run python scripts/validate_processed_jsonl.py \
  --input data/processed/legal_chunks.jsonl \
  --config configs/processing/processed_jsonl_validation.yml \
  --output artifacts/reports/chunking/processed_jsonl_validation_report.json \
  --pretty
```

Exit codes:

- `0`: `pass`, or `pass_with_warnings` under the default policy.
- `1`: `fail`.
- `2`: `pass_with_warnings` when `--fail-on-warnings` is enabled.

Use `--quiet` to suppress the normal terminal summary. The current full-corpus
result is `ready_with_warnings`: all 40,389 chunks are valid and embedding
ready, while 8,206 warnings remain deferred for a separate policy review.

Basic quantity check:

```bash
uv run python -c "import json; from pathlib import Path; p=Path('data/processed/legal_chunks.jsonl'); print(sum(1 for _ in p.open(encoding='utf-8')))"
```

## Acceptance Criteria

Phase 7 passes when:

- `processed_jsonl_validation_report.json` exists and is valid JSON.
- `invalid_chunks == 0`.
- `duplicate_chunk_ids == 0`.
- `hash_mismatches == 0`.
- `required_field_failures == 0`.
- `contamination_failures == 0` (warnings are acceptable).
- `chunks_by_level` totals reconcile with Phase 6 `chunking_report.json`.
- `chunks_by_law` totals reconcile with Phase 6 `chunking_report.json`.
- `repealed_metadata_summary` accounts for all 180 empty/repealed chunks.
- `long_parent_text_summary` shows 0 chunks exceeding 20,000 chars.
- All 52 laws are represented in `chunks_by_law`.

## Reviewer Checklist

- [ ] All 40,389 JSONL rows parse and validate as `LegalChunk`.
- [ ] No duplicate `chunk_id` values.
- [ ] All `text_hash` values match SHA-256 of `text`.
- [ ] All `parent_text_hash` values match SHA-256 of `parent_text`.
- [ ] Citation structural checks pass for all levels.
- [ ] No hard-fail contamination markers in any `text` or `parent_text`.
- [ ] Warning-only contamination markers are logged but do not cause failures.
- [ ] `chunks_by_level` and `chunks_by_law` match Phase 6 report.
- [ ] `parent_text` length distribution is documented.
- [ ] Repealed/empty metadata flags are preserved and counted.
- [ ] Report schema is documented and versioned.
- [ ] No Phase 7 code implements embedding, indexing, retrieval, or generation.

## Phase 8 Handoff Notes

After Phase 7 passes:

- Phase 8 should embed only `chunk.text`.
- Phase 8 should store `chunk.parent_text` as the retrieval/LLM context payload.
- Phase 8 should preserve `metadata.is_empty_or_repealed` and
  `metadata.is_source_unit_repealed` in the vector index payload for filtering.
- Phase 8 should not apply generic text splitters to `legal_chunks.jsonl`.
- Phase 8 should design context packing for long `parent_text` deliberately,
  using the `long_parent_text_summary` from the Phase 7 report.
- Phase 8 should preserve warning distribution as audit metadata.
- Phase 8 should not collapse distinct chunks solely because their direct text
  is identical; IDs and citations remain authoritative.
- Phase 8 must define deterministic legal-status/effective-date enrichment
  before claiming time-aware filtering.
- A fresh Phase 7 run must block indexing on hard errors or
  `embedding_ready=false`.
