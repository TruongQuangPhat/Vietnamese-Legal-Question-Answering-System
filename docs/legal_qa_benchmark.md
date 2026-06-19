# Legal QA Benchmark Implementation

This document describes the typed implementation layer for the broader legal
QA benchmark. The durable benchmark rules remain in
`docs/evaluation_protocol.md`.

## File Layout

Canonical benchmark data is expected to use JSONL files under a future
benchmark directory:

```text
data/eval/legal_qa_benchmark/benchmark_queries.jsonl
data/eval/legal_qa_benchmark/benchmark_targets.jsonl
data/eval/legal_qa_benchmark/benchmark_qrels.jsonl
data/eval/legal_qa_benchmark/evidence_groups.jsonl
data/eval/legal_qa_benchmark/review_records.jsonl
data/eval/legal_qa_benchmark/split_manifest.json
data/eval/legal_qa_benchmark/benchmark_manifest.json
```

Stage C implements loaders and validators for these file types, but it does
not create real benchmark records. Synthetic records are used only in tests.

Runtime or draft diagnostics may be written to:

```text
artifacts/reports/evaluation/
```

The canonical frozen split and benchmark manifests belong with the versioned
benchmark dataset under `data/eval/legal_qa_benchmark/`. Stage D/E will create
that real benchmark directory after pilot design and annotation approval.
CLI output paths are explicit and caller-controlled; Stage C does not hard-code
repository mutation.

## Schema Overview

Typed schema boundaries live under `src/evaluation/benchmark/`:

- `BenchmarkQuery`: query text, domain, question types, expected decision,
  fallback metadata, grouping keys, review status, split, and regression
  overlap declarations.
- `TemporalMetadata`: version sensitivity, `as_of_date`, and
  `applicable_law_id`.
- `LegalTarget`: reviewed legal hierarchy targets using canonical `law_id`.
- `EvidenceJudgment`: chunk-level relevance judgments.
- `EvidenceGroup`: semantic evidence requirements with
  `acceptable_chunk_ids` and `acceptable_legal_targets`.
- `ReviewRecord`: minimal primary review, independent review, and
  adjudication provenance.
- `SplitManifest`: deterministic grouped split assignments.
- `BenchmarkManifest`: frozen benchmark manifest with checksums.

All public input models reject unknown fields.

## Configuration

The default configuration is:

```text
configs/evaluation/legal_qa_benchmark.yml
```

Protocol invariants cannot be disabled through configuration:

- held-out cases require independent review;
- frozen `answer_allowed` required groups require chunk-level qrels;
- official duplicate normalization preserves Vietnamese diacritics;
- `grouping_fields` must include `case_family_id` and
  `source_provision_group_id`.

`development_ratio=0.7` and `split_seed=20260619` are provisional Stage C
defaults, not an approved final benchmark split policy.
`benchmark_version=draft` is allowed for development configuration, but freeze
refuses `draft` and other placeholder version values.

## Important Invariants

- `expected_decision=fallback_required` requires the `fallback` question type.
- The `fallback` question type requires `expected_decision=fallback_required`.
- Every fallback case requires `fallback_reason`.
- `answer_allowed` cases must not include `fallback_reason`.
- Blocking cases require `blocking_rationale`.
- Ambiguous cases require `ambiguity_category`.
- Temporal/version-sensitive cases require concrete `as_of_date`.
- Frozen queries require an assigned split.
- Regression-overlap cases must not be assigned to `held_out_test`.
- Only `required_direct` and `alternative_direct` evidence may complete
  required evidence groups.
- Supporting, near-miss, and irrelevant evidence cannot complete required
  groups.
- Frozen `answer_allowed` required groups require explicit
  `acceptable_chunk_ids`.
- `acceptable_legal_targets` support hierarchy validation but do not replace
  chunk-level qrels in a frozen benchmark.

## Sources of Truth

`SplitManifest.assignments` is the canonical split assignment. `BenchmarkQuery.split`
is a denormalized review and freeze summary. Validation requires every query to
have exactly one manifest assignment before freeze, rejects unknown assignment
IDs, and fails when `BenchmarkQuery.split` disagrees with the manifest.

`ReviewRecord` entries are the canonical review evidence.
`BenchmarkQuery.review_status` is a denormalized summary. Validation derives
the effective review evidence from records and fails when a query summary
claims `independent_reviewed`, `adjudicated`, or `frozen` without the required
records. Unresolved conflicts prevent freeze.

## Validation Layers

`BenchmarkValidator` separates validation into:

- record-level checks enforced by Pydantic models;
- referential integrity across query, target, qrel, group, and review files;
- decision and evidence sufficiency invariants;
- hierarchy and question-type consistency;
- review, conflict, adjudication, and freeze requirements;
- split leakage and regression contamination checks;
- qrel and evidence-group consistency checks;
- optional corpus-aware validation against
  `configs/laws/corpus_registry.yml` and
  `data/processed/legal_chunks.jsonl`.

Corpus-aware validation is read-only. It loads registry law IDs and minimal
chunk hierarchy metadata; it does not call Qdrant, OpenRouter, indexing,
generation, or retrieval.

## Grouped Split Behavior

`create_grouped_split` builds connected components over:

```text
case_family_id
source_provision_group_id
```

The grouping is transitive. If one query shares `case_family_id` with a second
query, and that second query shares `source_provision_group_id` with a third
query, all three are assigned to the same split.

Regression-overlap cases are forced to `development`. The splitter records an
input fingerprint, uses a configurable seed, keeps output ordering stable, and
reports stratification summaries. The input fingerprint is the canonical
semantic fingerprint of query records sorted by stable query ID, so harmless
JSONL line reordering does not change it. Multi-label stratification for
`question_types` is diagnostic; it is not a hard quota.

## Qrel and Evidence-Group Consistency

Every `acceptable_chunk_ids` entry in an `EvidenceGroup` must have a matching
`EvidenceJudgment` for the same `query_id` and `chunk_id`. That judgment must
use `required_direct` or `alternative_direct` and must reference the same
`evidence_group_id`.

Every direct judgment that references a group must point to an existing group
for the same query, and its chunk must be listed in that group's
`acceptable_chunk_ids`. Supporting, near-miss, and irrelevant judgments cannot
complete required groups. For frozen chunk-level groups, `minimum_hits` must
not exceed the number of distinct acceptable direct chunks.

## Fingerprints and Freeze

Fingerprint helpers distinguish two checksum categories:

```text
raw_file_sha256
canonical_content_sha256
```

`raw_file_sha256` hashes exact stored bytes. It changes when whitespace,
serialization, or JSONL line order changes.

`canonical_content_sha256` parses records through typed schemas, serializes
canonical JSON with sorted object keys, sorts record collections by documented
stable IDs, preserves Vietnamese Unicode content, and ignores JSON key order
and JSONL line order where dataset semantics are order-insensitive.

Split manifests record both raw file integrity and canonical split assignment
identity. Assignment dictionary ordering is not semantically significant.

Freeze support:

1. loads all benchmark files;
2. validates the dataset;
3. refuses freeze when validation errors exist;
4. refuses freeze when `benchmark_version` is `draft` or another placeholder;
5. refuses to overwrite an existing output manifest;
6. refuses freeze when queries are not frozen;
7. computes raw file checksums and canonical content fingerprints;
8. writes `BenchmarkManifest` atomically to a caller-provided path;
9. reloads and verifies the written manifest.

Manifests reject secret-like keys and values. They must not contain local
environment dumps, API keys, tokens, Authorization headers, or access tokens.

## CLI Usage

Validate benchmark files:

```bash
uv run python scripts/evaluation/validate_benchmark.py \
  --queries data/eval/legal_qa_benchmark/benchmark_queries.jsonl \
  --legal-targets data/eval/legal_qa_benchmark/benchmark_targets.jsonl \
  --evidence-judgments data/eval/legal_qa_benchmark/benchmark_qrels.jsonl \
  --evidence-groups data/eval/legal_qa_benchmark/evidence_groups.jsonl \
  --review-records data/eval/legal_qa_benchmark/review_records.jsonl \
  --config configs/evaluation/legal_qa_benchmark.yml
```

Create a grouped split manifest:

```bash
uv run python scripts/evaluation/create_benchmark_split.py \
  --queries data/eval/legal_qa_benchmark/benchmark_queries.jsonl \
  --config configs/evaluation/legal_qa_benchmark.yml \
  --output data/eval/legal_qa_benchmark/split_manifest.json
```

For draft diagnostics, a caller may write a temporary split report under
`artifacts/reports/evaluation/`.

Freeze a benchmark manifest:

```bash
uv run python scripts/evaluation/freeze_benchmark.py \
  --queries data/eval/legal_qa_benchmark/benchmark_queries.jsonl \
  --legal-targets data/eval/legal_qa_benchmark/benchmark_targets.jsonl \
  --evidence-judgments data/eval/legal_qa_benchmark/benchmark_qrels.jsonl \
  --evidence-groups data/eval/legal_qa_benchmark/evidence_groups.jsonl \
  --review-records data/eval/legal_qa_benchmark/review_records.jsonl \
  --split-manifest data/eval/legal_qa_benchmark/split_manifest.json \
  --change-log "Initial reviewed benchmark freeze." \
  --output data/eval/legal_qa_benchmark/benchmark_manifest.json
```

For draft validation reports, use `artifacts/reports/evaluation/`. Do not treat
runtime report paths as canonical frozen benchmark assets.

## Exit Codes

- `0`: command completed and validation passed where applicable.
- `1`: validation completed but found benchmark errors.
- `2`: command could not run because inputs, config, or file I/O failed.

## Current Limitations

- No real benchmark cases are included yet.
- No pilot annotation has started.
- Metric computation is not implemented in this layer.
- Sparse retrieval, BM25, RRF, fusion, reranking, GraphRAG, API, UI, and
  fine-tuning are out of scope.
- Semantic regression overlap detection is not fully automatic; declared
  overlap and exact normalized query matches are enforced, while deeper
  semantic overlap still requires review.
- Domain quotas, numeric relevance gains, and reranker choices remain open
  design questions.
- There is no overwrite mode for frozen benchmark manifests. Corrections
  should normally use a new benchmark version and output path.

## Data Status Distinctions

- Synthetic tests: temporary non-authoritative fixtures under `tests/`.
- Pilot data: future reviewed draft annotation records.
- Frozen benchmark data: future adjudicated files with deterministic splits,
  chunk-level qrels, checksums, and manifests.
