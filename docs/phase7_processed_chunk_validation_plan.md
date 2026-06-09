# Phase 7 — Processed Chunk Validation & Embedding Readiness Plan

## Objective

Validate `data/processed/legal_chunks.jsonl` as a deterministic,
hierarchy-preserving, citation-traceable input before Phase 8 embedding and
indexing. Phase 7 is a validation gate only: it must report unsafe chunks and
corpus inconsistencies without modifying, reparsing, or rechunking legal data.

## Current Status

- Slice 1: Complete
- Slice 2: Complete
- Slice 3A: Complete
- Slice 3B: Complete
- Slice 3C: Complete
- Slice 3D: Complete
- Slice 3E: Complete
- Slice 3F: Complete
- Slice 3G: Complete
- Slice 3H and later: Not started

## Completed Slices

### Slice 1 — Models, Config, And Report

- Pydantic V2 models define configuration, structured issues, and the report.
- Stable issue codes include `CITATION_STRUCTURE_MISMATCH` and
  `COUNT_RECONCILIATION_FAILED`.
- `errors_total` and `warnings_total` are authoritative.
- `sample_failures` and `sample_warnings` are capped diagnostic samples.
- Report status is derived as `pass`, `pass_with_warnings`, or `fail`.

### Slice 2 — Core JSONL Validation

- Streams JSONL line by line instead of loading the corpus into memory.
- Validates JSON parseability and object roots.
- Runs `LegalChunk.model_validate`.
- Checks required field presence before schema validation and required values
  after validation.
- Enforces global `chunk_id` uniqueness.
- Counts valid and invalid chunks once per line.
- Builds `chunks_by_level` and `chunks_by_law` distributions.

### Slice 3A — Hash Integrity

- Recomputes `text_hash` and `parent_text_hash` with the canonical hash helper.
- A chunk with one or both bad hashes increments `hash_mismatches` once.
- A hash-invalid line increments `invalid_chunks` and `errors_total` once.

### Slice 3B — Count Reconciliation

- Compares Phase 6 `total_chunks` with JSONL `total_lines`.
- Compares report-provided `chunks_by_level` entries as hard failures.
- Compares only the number of laws in `chunks_by_law`; mismatch is warning-only.
- Missing, unreadable, invalid, incomplete, or malformed report data is
  warning-only.
- Corpus-level reconciliation does not change per-line valid/invalid counts.
- No separate count-reconciliation source or test module was created.

### Slice 3C — Citation Structural Validation

- Validates citation hierarchy elements from typed chunk metadata.
- `article_level` and `article_level_empty` require
  `Điều <article_number>`.
- `clause_level` requires `Khoản <clause_number>` and
  `Điều <article_number>`.
- `point_level` requires `Điểm <point_label>`, `Khoản <clause_number>`, and
  `Điều <article_number>`.
- Matching is case-insensitive, accepts flexible whitespace and punctuation,
  and does not require a fixed element order.
- Exact identifier boundaries prevent prefix matches such as `Điều 1` matching
  `Điều 10`, `Khoản 2` matching `Khoản 20`, or `Điểm a` matching `Điểm aa`.
- One chunk with one or several missing citation elements increments
  `citation_failures`, `errors_total`, and the line-level invalid count once.
- Unknown chunk kinds and absent metadata values are not newly failed by this
  slice; required-field validation remains responsible for missing metadata.
- Citation validation does not inspect law titles, years, legal semantics,
  source text, or hierarchy files.

### Slice 3D — Hierarchy Traceability Validation

- Uses configured `hierarchy_dir/{law_id}/hierarchy.json` files read-only.
- Caches one hierarchy node index per law to avoid per-chunk file reads.
- Indexes dictionaries with non-empty `node_id` values; production files use a
  flat top-level `nodes` list, while recursive traversal supports simple nested
  fixtures.
- Requires `source_node_id` and `parent_article_node_id` to exist.
- Verifies the parent node is an Article and compares its `number` with
  `chunk.article_number` when present.
- Article chunks verify Article source level/number and require source and
  parent Article IDs to match.
- Clause chunks verify Clause source level/number and direct Article parent ID
  when those fields exist.
- Point chunks verify Point source level/label, resolve the direct Clause
  parent when available, compare Clause number, and verify its Article parent.
- Missing, unreadable, invalid, or node-empty hierarchy files are hard
  per-chunk failures. Load-failure samples are emitted at most once per law.
- Multiple traceability problems on one chunk increment
  `traceability_failures`, `errors_total`, and the line-level invalid count
  once.
- Checks are marked skipped only when `hierarchy_dir` is explicitly `None`.
- Unknown chunk kinds receive common node-existence and parent Article checks
  but no kind-specific source checks.

### Slice 3E — Contamination Audit

- Scans both embedding `text` and parent Article `parent_text`.
- Uses the configured hard and warning marker lists without modifying chunks.
- Matching is Unicode-aware, case-insensitive, and whitespace-normalized.
- Hard markers increment `contamination_failures` and `errors_total`, and mark
  the affected line invalid.
- Warning markers increment `contamination_warnings` and `warnings_total`
  without invalidating the line.
- Multiple hard or warning marker matches on one chunk count once for that
  severity; issue context retains all matched fields and configured markers.
- A chunk containing both categories records one hard failure and one warning.
- The colon remains required for `Nơi nhận:` and `Lưu:`, so text such as
  `Lưu ý` does not trigger the `Lưu:` hard marker.

### Slice 3F — Repealed / Empty Metadata Audit

- Counts both `is_empty_or_repealed` and `is_source_unit_repealed` flags.
- Scans `text` and `parent_text` for the configured conservative repealed
  placeholder phrases using case-insensitive, whitespace-normalized matching.
- Hard-fails direct `text` patterns without either metadata flag.
- Hard-fails parent-only patterns without metadata for Article chunks, where
  the parent and selected source represent the same legal unit.
- Does not fail Clause or Point chunks solely because shared `parent_text`
  contains a repealed sibling; those matches remain visible in the summary.
- Warns when metadata is marked but neither field contains a configured
  repealed pattern.
- Counts one mismatch per affected chunk and retains matched field/pattern
  details in capped issue samples.

### Slice 3G — Text Length / Parent Text Length Readiness

- Collects character lengths for schema-valid `text` and `parent_text`.
- Populates deterministic min/max/mean/median and p90/p95/p99 summaries.
- Uses 20 characters as the very-short reporting threshold, 50 characters for
  short-text warnings, and 4,000 characters for long-text warnings.
- Uses configured parent thresholds: 15,000 characters for long warnings and
  20,000 for extreme warnings.
- Whitespace-only non-repealed `text` is a hard failure; repealed/empty
  metadata suppresses that new length hard failure.
- Short/long text and empty/long/extreme parent context are warning-only.
- Counts each condition authoritatively while emitting at most one length
  warning issue per affected chunk.
- Preserves up to five longest parent-context examples and reports configured
  parent length bucket counts without modifying or truncating chunks.

## Current Review Before Slice 3C

Review date: June 9, 2026.

Baseline results:

- Python compilation: passed.
- Phase 7 model and validator tests: 83 passed.
- Ruff lint: passed.
- Ruff format check: passed.
- `git diff --check`: passed.
- Protected paths: clean.
- Working tree before this documentation update contained only the intentional
  deletion of the obsolete root-level tracking file.

Current corpus/report observations:

- Phase 6 report: 40,389 chunks across 52 laws.
- Levels: 1,322 article, 20,643 clause, and 18,424 point chunks.
- Chunk kinds include 1,233 `article_level`, 89 `article_level_empty`,
  20,643 `clause_level`, and 18,424 `point_level` chunks.
- A read-only profile found no missing exact `Điều`/`Khoản`/`Điểm` tokens under
  the proposed simple structural rules.
- Law names vary, including consolidated/VBHN naming, while hierarchy tokens
  remain stable.

Files and surfaces reviewed:

- Project context: `README.md`, `CLAUDE.md`, `AGENTS.md`,
  `PROJECT_CONTEXT.md`, and `pyproject.toml`.
- Repository layout: `configs/`, `docs/`, `src/`, `src/processing/`, `tests/`,
  `tests/unit/`, and `tests/unit/processing/`.
- Phase 7 code: `processed_jsonl_validation_models.py`,
  `processed_jsonl_validator.py`, and `legal_chunk_models.py`.
- Phase 7 tests: model and validator unit test modules.
- Configuration: `configs/processing/processed_jsonl_validation.yml`.
- Phase 6 evidence: `chunking_report.json` and a read-only inspection of
  `legal_chunks.jsonl`.
- Related documentation: processed JSONL, parent-child chunking, and
  end-to-end pipeline documents.

## Design Principles

- Preserve the streaming validator and single typed report object.
- Keep authoritative counters separate from capped issue samples.
- Count a failed check according to its documented unit: per line/chunk for
  citation integrity, corpus-level for reconciliation.
- Set `line_has_error` for hard per-chunk failures so `invalid_chunks` remains a
  count of affected lines, not a count of individual missing citation elements.
- Use existing local helper/closure style inside `validate()` when the logic is
  local to one validation pass.
- Reuse `ProcessedJsonlIssue`, stable issue codes, `_make_issue`, and sample-cap
  helpers.
- Keep hard failures distinct from warning-only diagnostics.
- Do not mutate generated data or Phase 6 reports.
- Do not combine citation structure with hierarchy-file traceability.
- Do not begin embedding, indexing, retrieval, generation, or RAG work.

## Slice 3C Implementation — Citation Structural Validation

Purpose: verify that each validated chunk citation contains the hierarchy
identifiers required by its chunk kind, without enforcing document-title,
year, punctuation, or element-order conventions.

Implemented rules:

| Chunk kind | Required structural elements |
| --- | --- |
| `article_level` | `Điều <article_number>` |
| `article_level_empty` | `Điều <article_number>` |
| `clause_level` | `Khoản <clause_number>` and `Điều <article_number>` |
| `point_level` | `Điểm <point_label>`, `Khoản <clause_number>`, and `Điều <article_number>` |

Implemented behavior:

1. Run citation validation only after schema and required-field validation.
2. Build expected elements from typed chunk metadata; do not parse identifiers
   from `text`, `parent_text`, `hierarchy_path`, or external sources.
3. Match Vietnamese labels with flexible whitespace and exact escaped
   identifiers so `Điều 1` does not incorrectly satisfy `Điều 10`.
4. Do not require a fixed law name, year, VBHN label, punctuation, or ordering.
5. On any missing or mismatched required element:
   - increment `citation_failures` once for the chunk;
   - increment `errors_total` once;
   - mark the line invalid once;
   - add a capped `CITATION_STRUCTURE_MISMATCH` sample with chunk identity,
     citation, chunk kind/level, and missing expected elements.
6. If several required elements are wrong on one chunk, report one citation
   failure with all missing elements in context.
7. Preserve all Slice 1–3B counters, status behavior, and reconciliation logic.

Tests added in the existing validator test module:

- valid article, empty-article, clause, and point citations;
- missing or wrong Article, Clause, and Point identifiers;
- law-title/year/VBHN variation remains accepted;
- punctuation and element order are not over-constrained;
- exact identifier boundaries prevent prefix false positives;
- multiple missing elements count as one citation failure and one invalid chunk;
- existing sample-cap behavior remains covered;
- prior Slice 1–3B behavior remains passing.

Implementation files:

- `src/processing/processed_jsonl_validator.py`
- `tests/unit/processing/test_processed_jsonl_validator.py`
- `docs/phase7_processed_chunk_validation_plan.md`

No new source module was created. The validation model file was not modified
because `CITATION_STRUCTURE_MISMATCH` already existed.

Verification result:

- Phase 7 model and validator tests: 98 passed.
- Read-only full-corpus validation: 40,389 valid chunks, 0 invalid chunks,
  0 citation failures, 0 hash mismatches, and 0 reconciliation failures.
- Python compilation: passed.
- Ruff lint: passed.
- Ruff format check: passed.
- `git diff --check`: passed.
- Protected data and artifact paths: clean.

## Slice 3D Implementation — Hierarchy Traceability Validation

Observed hierarchy schema:

- top-level object fields include `law_id`, `root_node_id`, metadata, warnings,
  and a flat `nodes` list;
- nodes expose `node_id`, `level`, `number`, `parent_id`, and `children`;
- `children` contains node ID strings rather than nested node objects.

Objective: prove that each processed chunk references real hierarchy nodes and
that clearly available Article/Clause/Point metadata agrees with the chunk.
This slice does not compare source text, offsets, citations, or legal meaning.

Implementation files:

- `src/processing/processed_jsonl_validator.py`
- `tests/unit/processing/test_processed_jsonl_validator.py`
- `docs/phase7_processed_chunk_validation_plan.md`

The validation model file was not modified because
`HIERARCHY_TRACEABILITY_FAILED` already existed. No new source module was
created.

Verification result:

- Phase 7 model and validator tests: 110 passed.
- Read-only full-corpus validation: 40,389 valid chunks, 0 invalid chunks,
  traceability checks not skipped, 0 traceability failures, 0 citation
  failures, 0 hash mismatches, and 0 reconciliation failures.
- Python compilation: passed.
- Ruff lint: passed.
- Ruff format check: passed.
- `git diff --check`: passed.
- Protected data and artifact paths: clean.

## Slice 3E Implementation — Contamination Audit

Objective: detect fixed non-content boilerplate and signature/authority
markers in processed child and parent text without cleaning or mutating the
generated corpus.

Hard-failure markers:

- `XÁC THỰC VĂN BẢN HỢP NHẤT`
- `Nơi nhận:`
- `Lưu:`
- `Văn bản này được hợp nhất`

Warning-only markers:

- `BỘ TRƯỞNG`
- `CHỦ NHIỆM`
- `CHỦ TỊCH QUỐC HỘI`
- `TM. QUỐC HỘI`
- `KT. BỘ TRƯỞNG`

Implementation files:

- `src/processing/processed_jsonl_validator.py`
- `tests/unit/processing/test_processed_jsonl_validator.py`
- `docs/phase7_processed_chunk_validation_plan.md`

The validation model file was not modified because
`HARD_CONTAMINATION_FOUND` and `WARNING_CONTAMINATION_FOUND` already existed.
No new source module was created.

Verification result:

- Phase 7 model and validator tests: 122 passed.
- Read-only full-corpus validation: 40,389 valid chunks, 0 invalid chunks,
  0 hard contamination failures, and 3,561 warning-only contamination chunks.
- Full-corpus status: `pass_with_warnings`; the broad authority markers can
  appear in substantive provisions, so their warning-only classification is
  preserved.
- Python compilation: passed.
- Ruff lint: passed.
- Ruff format check: passed.
- `git diff --check`: passed.
- Protected data and artifact paths: clean.

## Slice 3F Implementation — Repealed / Empty Metadata Audit

Objective: audit whether empty/repealed metadata agrees with conservative
placeholder phrases in selected chunk text and parent Article context, without
modifying generated chunks.

Configured patterns:

- `(được bãi bỏ)`
- `Điều này được bãi bỏ`
- `Khoản này được bãi bỏ`
- `Điểm này được bãi bỏ`

Populated summary fields:

- `metadata_empty_or_repealed_count`
- `metadata_source_unit_repealed_count`
- `text_repealed_pattern_count`
- `parent_text_repealed_pattern_count`
- `text_or_parent_repealed_pattern_count`
- `text_repealed_but_metadata_not_marked_count`
- `article_parent_repealed_but_metadata_not_marked_count`
- `metadata_marked_but_no_text_pattern_count`
- `metadata_mismatch_failure_count`
- `metadata_mismatch_warning_count`

Implementation files:

- `src/processing/processed_jsonl_validation_models.py`
- `src/processing/processed_jsonl_validator.py`
- `tests/unit/processing/test_processed_jsonl_validation_models.py`
- `tests/unit/processing/test_processed_jsonl_validator.py`
- `docs/phase7_processed_chunk_validation_plan.md`

The validation model received the minimal stable issue code
`REPEALED_METADATA_MISMATCH`. No new source module was created.

Verification result:

- Phase 7 model and validator tests: 132 passed.
- Read-only full-corpus validation: 40,389 valid chunks, 0 invalid chunks,
  0 Slice 3F failures, and 0 Slice 3F warnings.
- Full-corpus repealed summary: 180 `is_empty_or_repealed`, 180
  `is_source_unit_repealed`, 180 direct `text` matches, 756 `parent_text`
  matches, and 0 metadata inconsistencies.
- The additional 576 parent-only matches belong to Clause/Point chunks whose
  shared parent Article contains a repealed sibling; they are summarized but
  not treated as source-unit mismatches.
- Overall status remains `pass_with_warnings` because Slice 3E still reports
  3,561 warning-only contamination chunks.
- Python compilation: passed.
- Ruff lint: passed.
- Ruff format check: passed.
- `git diff --check`: passed.
- Protected data and artifact paths: clean.

## Slice 3G Implementation — Text Length / Parent Text Length Readiness

Objective: measure embedding-unit and parent-context character lengths and
surface readiness risks without splitting, truncating, or rewriting chunks.

Thresholds:

- very short `text`: fewer than 20 characters, summary-only counter;
- short `text`: fewer than 50 characters, warning-only;
- long `text`: more than 4,000 characters, warning-only;
- long `parent_text`: more than configured 15,000 characters, warning-only;
- extreme `parent_text`: more than configured 20,000 characters, warning-only.

Populated report summaries:

- `text_length_summary`: count, min/max/mean/median, p90/p95/p99, empty,
  very-short, short-warning and long-warning counts, plus thresholds.
- `parent_text_length_summary`: count, min/max/mean/median, p90/p95/p99,
  empty, long-warning and extreme-warning counts, plus thresholds.
- `long_parent_text_summary`: thresholds, long/extreme counts, maximum,
  configured bucket counts, and up to five longest examples.

Implementation files:

- `src/processing/processed_jsonl_validation_models.py`
- `src/processing/processed_jsonl_validator.py`
- `tests/unit/processing/test_processed_jsonl_validation_models.py`
- `tests/unit/processing/test_processed_jsonl_validator.py`
- `docs/phase7_processed_chunk_validation_plan.md`

The validation model received `TEXT_LENGTH_WARNING` and `EMPTY_TEXT_FOUND`.
The existing `VERY_LONG_PARENT_TEXT` code is reused. The existing
`long_parent_text_summary` value type was widened to support structured capped
examples. No new source module was created.

Verification result:

- Phase 7 model and validator tests: 144 passed.
- Read-only full-corpus validation: 40,389 valid chunks, 0 invalid chunks, and
  0 hard length failures.
- `text`: min 9, max 3,430, p95 466, p99 728; 475 very-short chunks,
  4,645 short-text warnings, 0 empty text, and 0 long-text warnings.
- `parent_text`: min 26, max 14,481, p95 4,884, p99 8,704; 0 empty,
  0 long warnings, and 0 extreme warnings.
- Parent buckets: 36,887 at or below 4,000; 3,284 from 4,001–10,000;
  218 from 10,001–15,000; none above 15,000.
- Overall status remains `pass_with_warnings`; authoritative warnings total
  8,206, including the existing 3,561 contamination warnings and 4,645 new
  short-text readiness warnings.
- Python compilation: passed.
- Ruff lint: passed.
- Ruff format check: passed.
- `git diff --check`: passed.
- Protected data and artifact paths: clean.

## Non-goals

Phase 7 validation slices must not:

- validate whether a citation is legally or semantically correct;
- compare citations with hierarchy JSON files;
- validate effective dates, law versions, amendments, or repeal status;
- enforce law title, year, consolidated-version wording, punctuation, or order;
- modify citations or chunks;
- parse or rechunk legal text;
- add external legal sources or network calls;
- implement payload or embedding-readiness checks before their approved slice;
- implement services, CLI commands, reports on disk, embedding, indexing,
  retrieval, reranking, generation, Naive RAG, Advanced RAG, or GraphRAG.

## Remaining Risks / Open Questions

- Vietnamese citation labels may contain capitalization or spacing variation;
  matching should be tolerant without accepting wrong identifiers.
- Naive substring checks can confuse identifier prefixes such as `Điều 1` and
  `Điều 10`; exact boundaries are required.
- `article_level_empty` must follow article citation rules even though the
  current required-field rule map does not list it alongside `article_level`.
- Repealed/empty chunks still need structurally valid citations; their legal
  status metadata is a separate concern.
- Unknown future `chunk_kind` values are intentionally skipped in Slice 3C;
  a later chunk-kind consistency check must decide how to classify them before
  citation requirements are expanded.
- Citation failures are hard failures because incorrect hierarchy anchors make
  a chunk unsafe for legal retrieval; this severity is explicit in tests.
- Citation structure must remain separate from later hierarchy traceability to
  avoid duplicate failure counts for the same underlying inconsistency.

## Tracking File Migration

The root-level `phase7_processed_chunk_validation_plan.md` was obsolete and is
removed. Its useful Slice 1–3B status and verification history are incorporated
here. This file is the only official Phase 7 tracking plan going forward.

## Next Action

Slice 3G is complete. Slice 3H and later are not started; wait for explicit
approval before implementing the next validation slice.
