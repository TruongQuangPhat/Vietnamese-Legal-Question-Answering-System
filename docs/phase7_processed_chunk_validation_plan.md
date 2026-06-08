# Phase 7 — Processed Chunk Validation & Embedding Readiness

## 1. Purpose

Phase 7 is a **validation gate** that confirms `data/processed/legal_chunks.jsonl`
is safe to use as input for Phase 8 embedding/indexing. It does not implement
embedding, indexing, retrieval, or generation.

The gate verifies JSONL correctness, `LegalChunk` schema compliance, count
reconciliation with the Phase 6 chunking report, traceability back to the legal
hierarchy, hash/offset integrity, embedding-readiness, payload-readiness,
contamination absence, and long-`parent_text` context-packing risk.

## 2. Current Inputs

| Artifact | Path | Description |
|----------|------|-------------|
| Chunk corpus | `data/processed/legal_chunks.jsonl` | 40,389 validated legal chunks |
| Chunking report | `artifacts/reports/chunking/chunking_report.json` | Phase 6 batch report |
| Full-corpus validation | `artifacts/reports/chunking/full_corpus_validation_report.json` | Phase 6 hardening audit |
| Hierarchy inputs | `data/interim/{LAW_ID}/hierarchy.json` | 52 hierarchy files for traceability |

Corpus snapshot (Phase 6 output):

```text
Laws: 52
Total chunks: 40,389
Article chunks: 1,322
Clause chunks: 20,643
Point chunks: 18,424
Empty/repealed chunks: 180
Source-tail markers: 0 in text, 0 in parent_text
Max parent_text length: 14,481 chars
Duplicate chunk_id: 0
Bad JSONL lines: 0
```

## 3. Expected Outputs

| Artifact | Path | Description |
|----------|------|-------------|
| Validation report | `artifacts/reports/chunking/processed_jsonl_validation_report.json` | Phase 7 gate result |
| Diagnostic runs | `artifacts/runs/phase7_processed_chunk_validation/` | Optional per-run diagnostics |

## 4. Scope

Phase 7 validates:

1. JSONL correctness — every line parses as valid JSON.
2. `LegalChunk` schema correctness — every row passes Pydantic validation.
3. Required fields — all mandatory fields are present and non-empty.
4. `chunk_id` uniqueness — globally unique across the full corpus.
5. Count/report consistency — JSONL row counts match `chunking_report.json`.
6. Hash/offset integrity — `text_hash` and `parent_text_hash` are correct SHA-256.
7. Citation structural consistency — valid by chunk level (see §10).
8. Traceability — `source_node_id` and `parent_article_node_id` are coherent.
9. Embedding-readiness — `text` is the embedding input; `parent_text` is context.
10. Payload-readiness — fields required for Phase 8 vector index are present.
11. Contamination absence — no hard-fail markers in `text` or `parent_text`.
12. Repealed/empty metadata — flags are preserved and counted.
13. Long `parent_text` — measured and classified for context-packing risk.

## 5. Non-goals

Phase 7 does **not** implement:

- embedding or vector generation;
- Qdrant collection setup or indexing;
- BM25, sparse retrieval, or hybrid search;
- reranking;
- Naive RAG, Advanced RAG, or GraphRAG;
- Neo4j graph construction or traversal;
- API endpoints or backend services;
- LLM generation, prompt engineering, or answer formatting;
- legal text splitting, rechunking, or reprocessing;
- re-crawling, re-cleaning, re-parsing, or re-chunking.

## 6. Phase 6 Dependency Summary

Phase 7 depends on Phase 6 outputs only. No upstream re-processing is required
unless a proven blocker is found during validation.

| Phase 6 output | Phase 7 usage |
|-----------------|---------------|
| `data/processed/legal_chunks.jsonl` | Primary validation input |
| `artifacts/reports/chunking/chunking_report.json` | Count reconciliation |
| `artifacts/reports/chunking/full_corpus_validation_report.json` | Cross-reference |
| `data/interim/{LAW_ID}/hierarchy.json` | Traceability verification (optional) |

Phase 6 guarantees consumed by Phase 7:

- 0 bad JSONL lines
- 0 duplicate `chunk_id`
- 0 source-tail markers in `text` and `parent_text`
- 180 empty/repealed chunks flagged in metadata
- `parent_text` max length: 14,481 chars

## 7. Validation Checks

| # | Check | Severity | Description |
|---|-------|----------|-------------|
| 1 | JSONL parse | Error | Every line parses as valid JSON |
| 2 | Schema validation | Error | Every row validates as `LegalChunk` |
| 3 | Required fields | Error | All mandatory fields present and non-empty |
| 4 | `chunk_id` uniqueness | Error | Globally unique across corpus |
| 5 | Count reconciliation | Error | JSONL counts match `chunking_report.json` |
| 6 | `text_hash` integrity | Error | SHA-256 of `text` matches `text_hash` |
| 7 | `parent_text_hash` integrity | Error | SHA-256 of `parent_text` matches `parent_text_hash` |
| 8 | Offset containment | Error | `start_offset`/`end_offset` within Article offsets |
| 9 | Citation — article | Error | Article chunks contain `Điều {article_number}` |
| 10 | Citation — clause | Error | Clause chunks contain `Khoảng {clause_number}` and `Điều {article_number}` |
| 11 | Citation — point | Error | Point chunks contain `Điểm {point_label}`, `Khoản {clause_number}`, `Điều {article_number}` |
| 12 | Hard-fail contamination | Error | No hard-fail markers in `text` or `parent_text` |
| 13 | Warning contamination | Warning | Warning-only markers logged but do not fail |
| 14 | `is_empty_or_repealed` count | Warning | Count matches Phase 6 (180) |
| 15 | `parent_text` length | Warning | Classify and flag > 20,000 chars |
| 16 | `chunk_kind` consistency | Warning | `chunk_kind` matches `level` |
| 17 | `parent_chunk_id` format | Warning | Format is `{article_node_id}__parent` |
| 18 | `source_file` traceability | Info | Path points to existing `hierarchy.json` |

## 8. Embedding-Readiness Contract

Phase 8 must follow this contract:

```text
embedding input:  chunk.text
retrieval payload: chunk.parent_text
```

Rules:

- Embed **only** `chunk.text`. Do not embed `parent_text` as the primary vector.
- `parent_text` is the full Article text for LLM context after retrieval.
- Do not apply generic text splitters (e.g., LangChain `RecursiveCharacterTextSplitter`)
  to `legal_chunks.jsonl`. Each JSONL row is already a legally coherent unit.
- If LangChain is used in Phase 8+, wrap each JSONL row as a `Document`; do not
  split it further.

## 9. Payload-Readiness Contract

Phase 8 vector index payload must carry at minimum:

| Field | Source | Purpose |
|-------|--------|---------|
| `chunk_id` | `LegalChunk.chunk_id` | Unique retrieval key |
| `law_id` | `LegalChunk.law_id` | Law-level filtering |
| `law_name` | `LegalChunk.law_name` | Display |
| `level` | `LegalChunk.level` | Hierarchy level |
| `article_number` | `LegalChunk.article_number` | Citation display |
| `clause_number` | `LegalChunk.clause_number` | Citation display (nullable) |
| `point_label` | `LegalChunk.point_label` | Citation display (nullable) |
| `citation` | `LegalChunk.citation` | Full citation string |
| `hierarchy_path` | `LegalChunk.hierarchy_path` | Display path |
| `source_node_id` | `LegalChunk.source_node_id` | Hierarchy traceability |
| `parent_article_node_id` | `LegalChunk.parent_article_node_id` | Article grouping |
| `parent_chunk_id` | `LegalChunk.parent_chunk_id` | Parent context lookup |
| `text_hash` | `LegalChunk.text_hash` | Dedup / integrity |
| `parent_text_hash` | `LegalChunk.parent_text_hash` | Dedup / integrity |
| `metadata.is_empty_or_repealed` | `LegalChunk.metadata` | Filtering |
| `metadata.is_source_unit_repealed` | `LegalChunk.metadata` | Filtering |
| `metadata.source_warnings` | `LegalChunk.metadata` | Caveat display |
| `metadata.caveat_references` | `LegalChunk.metadata` | Caveat display |

## 10. Citation Validation Rules

Phase 7 validates **structural citation consistency by level**. It does not
enforce a fixed law-name/year ordering. The existing Phase 6 citation format is
law-name-first and may vary for VBHN/consolidated texts.

| Chunk level | Required citation elements |
|-------------|---------------------------|
| `article` | Must contain `Điều {article_number}` |
| `clause` | Must contain `Khoản {clause_number}` and `Điều {article_number}` |
| `point` | Must contain `Điểm {point_label}`, `Khoản {clause_number}`, and `Điều {article_number}` |

Validation approach:

- Extract the expected element strings from the citation field using the
  chunk's `article_number`, `clause_number`, and `point_label` fields.
- Check that each required element string appears in the citation.
- Do not check law name, year, or ordering — those vary by document type.

## 11. Contamination Marker Policy

### Hard-fail markers (validation fails if found in `text` or `parent_text`)

| Marker | Reason |
|--------|--------|
| `XÁC THỰC VĂN BẢN HỢP NHẤT` | VBHN certification tail — should be excluded |
| `Nơi nhận:` | Distribution header — should be excluded |
| `Lưu:` | Filing marker — should be excluded |
| `Văn bản này được hợp nhất` | VBHN processing note — should be excluded |

### Warning-only markers (logged as warnings, do not fail validation)

| Marker | Reason |
|--------|--------|
| `BỘ TRƯỞNG` | May appear in valid signature blocks |
| `CHỦ NHIỆM` | May appear in valid signature blocks |
| `CHỦ TỊCH QUỐC HỘI` | May appear in valid signature blocks |
| `TM. QUỐC HỘI` | May appear in valid signature blocks |
| `KT. BỘ TRƯỞNG` | May appear in valid signature blocks |

Warning-only markers must not cause automatic validation failure because they
can legitimately appear in the body of law texts (e.g., at the end of an
Article where the signing authority is listed).

## 12. Long `parent_text` Policy

Phase 6 preserves whole Article context in `parent_text`. Phase 7 measures and
classifies length for downstream context packing:

| Class | Length | Action |
|-------|--------|--------|
| Short | <= 4,000 chars | No special handling |
| Medium | 4,001–10,000 chars | Standard LLM context window |
| Long | 10,001–20,000 chars | May need truncation/summarization at retrieval time |
| Very long | > 20,000 chars | Flag for manual review |

Current corpus: 0 chunks exceed 20,000 chars. Max `parent_text` is 14,481 chars.

Do not split `parent_text` arbitrarily. Context packing decisions belong to
Phase 9–10 retrieval/generation, not Phase 7.

## 13. Repealed/Empty Metadata Policy

Phase 6 flags two metadata booleans:

- `metadata.is_empty_or_repealed`: the source Article is empty, repealed, or a
  placeholder-like node.
- `metadata.is_source_unit_repealed`: the selected source unit (Article, Clause,
  or Point) itself contains a repealed placeholder.

Phase 7 must:

- Count the distribution of both flags across the corpus.
- Verify the total matches the Phase 6 count (180 empty/repealed chunks).
- Report the breakdown by `chunk_kind` (article_level_empty, clause_level, point_level).
- Preserve these flags in the validation report for Phase 8 filtering decisions.

## 14. Proposed Files

| File | Purpose |
|------|---------|
| `src/processing/processed_jsonl_validation_models.py` | Pydantic models for Phase 7 report, issue codes, and config |
| `src/processing/processed_jsonl_validator.py` | Core validator: JSONL streaming, schema validation, hash/citation/contamination checks |
| `src/services/processed_jsonl_validation_service.py` | Orchestration: run validator, reconcile with Phase 6 report, write output |
| `scripts/validate_processed_jsonl.py` | CLI entrypoint with argparse |
| `tests/unit/processing/test_processed_jsonl_validator.py` | Unit tests for validator |
| `tests/unit/services/test_processed_jsonl_validation_service.py` | Service-level tests |
| `configs/processing/processed_jsonl_validation.yml` | Config: thresholds, paths, long-text limits, contamination markers |
| `docs/processed_jsonl.md` | Phase 7 documentation (this is the reference doc) |

## 15. Implementation Slices

| Step | Slice | Description |
|------|-------|-------------|
| 1 | Models/config | Define `ProcessedJsonlValidationReport`, `ValidationIssueCode`, config schema |
| 2 | Core validator | Stream-parse JSONL, validate each row as `LegalChunk`, check required fields, uniqueness, hashes, offsets |
| 3 | Citation/contamination | Structural citation validation by level; hard-fail and warning-only contamination detection |
| 4 | Report reconciliation | Cross-check counts, level distribution, law distribution against `chunking_report.json` |
| 5 | Embedding-readiness | Verify `text`/`parent_text` contract, measure `parent_text` length distribution, flag very-long contexts |
| 6 | Service + report writer | Orchestrate all checks, write `processed_jsonl_validation_report.json` |
| 7 | CLI | argparse entrypoint with `--verbose`, `--no-color`, configurable paths |
| 8 | Full corpus run | Execute against 40,389 chunks, review report, update docs |

## 16. Execution Progress

- [ ] Step 1 - Documentation/context update
- [ ] Step 2 - Validation models/config
- [ ] Step 3 - Core JSONL validator
- [ ] Step 4 - Report reconciliation and embedding-readiness checks
- [ ] Step 5 - Service and report writer
- [ ] Step 6 - CLI
- [ ] Step 7 - Full corpus validation run
- [ ] Step 8 - Docs/context final update

## 17. Commands

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

Run Phase 7 validation (to be implemented):

```bash
uv run python scripts/validate_processed_jsonl.py \
  --input data/processed/legal_chunks.jsonl \
  --chunking-report artifacts/reports/chunking/chunking_report.json \
  --hierarchy-dir data/interim \
  --report artifacts/reports/chunking/processed_jsonl_validation_report.json \
  --verbose \
  --no-color
```

Basic quantity check:

```bash
uv run python -c "import json; from pathlib import Path; p=Path('data/processed/legal_chunks.jsonl'); print(sum(1 for _ in p.open(encoding='utf-8')))"
```

## 18. Acceptance Criteria

Phase 7 passes when all of the following are true:

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
- No Phase 7 code implements embedding, indexing, retrieval, or generation.

## 19. Reviewer Checklist

- [ ] All 40,389 JSONL rows parse and validate as `LegalChunk`.
- [ ] No duplicate `chunk_id` values.
- [ ] All `text_hash` values match SHA-256 of `text`.
- [ ] All `parent_text_hash` values match SHA-256 of `parent_text`.
- [ ] Offset containment: every chunk's offsets fit within its parent Article.
- [ ] Citation structural checks pass for all levels (article/clause/point).
- [ ] No hard-fail contamination markers in any `text` or `parent_text`.
- [ ] Warning-only contamination markers are logged but do not cause failures.
- [ ] `chunks_by_level` and `chunks_by_law` match Phase 6 `chunking_report.json`.
- [ ] `parent_text` length distribution is documented in the report.
- [ ] Repealed/empty metadata flags are preserved and counted correctly.
- [ ] Report schema is documented and versioned.
- [ ] No Phase 7 implementation code touches embedding, indexing, retrieval, or generation.

## 20. Phase 8 Handoff Notes

After Phase 7 passes, Phase 8 should:

- Embed **only** `chunk.text`.
- Store `chunk.parent_text` as the retrieval/LLM context payload in the vector index.
- Preserve `metadata.is_empty_or_repealed` and `metadata.is_source_unit_repealed`
  in the index payload for retrieval-time filtering.
- Not apply generic text splitters to `legal_chunks.jsonl`. Each row is a
  legally coherent unit; wrap as `Document` if using LangChain.
- Design context packing for long `parent_text` deliberately, using the
  `long_parent_text_summary` from the Phase 7 report rather than arbitrary
  character limits.
