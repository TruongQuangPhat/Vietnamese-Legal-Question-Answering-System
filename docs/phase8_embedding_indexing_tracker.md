# Phase 8 Embedding and Indexing Tracker

## Goal

Phase 8 builds a verified vector-index foundation from validated
`LegalChunk` records. It is not full RAG and does not perform legal answer
generation.

The dense baseline comes first. Sparse vectors remain optional and
configurable so sparse integration cannot block dense indexing.

## Corpus Readiness

- Input: `data/processed/legal_chunks.jsonl`
- Valid chunks: 40,389 across 52 laws
- Validation errors and invalid chunks: 0
- Accepted non-blocking warnings: 8,206
- Payload ready rate: 1.0
- Readiness: `embedding_ready=true`, `ready_with_warnings`

Warnings remain visible and non-blocking. Short chunks, authority markers,
distinct chunk IDs, citations, hashes, hierarchy fields, and parent Article
context must be preserved.

## Protected Paths

Phase 8 work must not mutate:

- `data/raw`
- `data/interim`
- `data/reports`
- `data/processed`
- `artifacts/reports` except during a separately scoped official report run

Validation checks for development must write reports under `/tmp`.

## Non-Goals

Phase 8 does not implement retrieval, reranking, RAG answer generation,
GraphRAG, model fine-tuning, or legal advice. It must not invent
`effective_date`, `expiry_date`, `status`, or `domain_tags`; unknown values
remain null or empty until deterministic enrichment exists.

## Slicing Plan

| Slice | Name | Status | Notes |
|---|---|---|---|
| 8A | Configuration and typed data contracts | Done | No embedding or Qdrant connection |
| 8B | Chunk loader and metadata enrichment | Done | Read-only streaming and deterministic mapping |
| 8C | Embedding model pilot | Done | BGE-M3 loaded; 10- and 100-chunk CPU pilots passed; dense dimension 1024 |
| 8D | Payload builder | Done | Typed payload mapping and deterministic UUIDv5 point IDs |
| 8E | Qdrant collection setup | Done | Safe schema setup; no corpus points indexed |
| 8F | Indexing service | Done | Bounded dense embed/upsert, dry-run, report, checkpoint |
| 8G | Official CLI | Not started | `build_embedding_index.py` |
| 8H | Index validation | Not started | Count/vector/payload/filter/idempotency |

## Slice 8A Summary

Slice 8A adds:

- explicit embedding, sparse, Qdrant, payload, and runtime configuration;
- nullable dense dimension with `measure_from_model_output` policy;
- typed embedding input and dense/sparse output contracts;
- a traceability-preserving vector payload contract;
- typed indexing issue and planned-report contracts;
- unit tests for configuration and model invariants.

It does not load BGE-M3, connect to Qdrant, embed text, create collections,
index points, retrieve data, mutate chunks, or write an official report.

## Slice 8B Summary

Slice 8B adds:

- a read-only, line-by-line `LegalChunk` JSONL loader;
- fail-fast errors with input path and line number where available;
- deterministic `text_only`, `citation_plus_text`, and
  `law_citation_plus_text` mapping;
- optional exact `law_id` filtering and result limiting;
- preservation of short text, hashes, citations, hierarchy, typed metadata,
  warnings, and distinct chunk IDs;
- unit tests using temporary JSONL files only.

It does not load BGE-M3, generate dense or sparse vectors, connect to Qdrant,
index points, implement checkpointing or retrieval, mutate the corpus, or
write an official report. Protected corpus and report paths remain unchanged.

## Slice 8C Summary

Slice 8C adds:

- a lazy, testable `BGEM3FlagModel` dense embedding wrapper;
- robust extraction of `dense_vecs` and measured output dimensions;
- a constrained pilot CLI with safe sample limits and `/tmp` output default;
- vector finiteness, dimension, norm, runtime, throughput, device, and
  batch-size stability diagnostics;
- failure reports for missing dependencies, model loading, device, and
  embedding errors;
- fake-model unit tests that do not require a GPU, model download, Qdrant, or
  internet access.

Dense dimension is measured from model output and is not hard-coded or written
back to configuration. The pilot does not connect to Qdrant, perform full
indexing, build payloads, mutate the corpus, or write official reports under
`artifacts/reports`.

### BGE-M3 Download and Load

Install the optional embedding dependency with:

```bash
uv sync --extra embedding
```

BGE-M3 was downloaded and loaded successfully through
`FlagEmbedding.BGEM3FlagModel` using:

```bash
uv run --extra embedding python /tmp/download_bge_m3.py
```

The temporary load test used:

```python
from FlagEmbedding import BGEM3FlagModel

model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)
```

Observed result:

```text
Model loaded successfully.
Dense shape: (2, 1024)
First vector length: 1024
```

Under WSL/Linux, the default Hugging Face model cache is:

```text
~/.cache/huggingface/hub/models--BAAI--bge-m3
```

When `HF_HOME` is set manually, the cache is:

```text
$HF_HOME/hub/models--BAAI--bge-m3
```

The model is not stored in `/tmp`; `/tmp` contains only temporary scripts and
pilot reports.

### Real CPU Pilots

The 10-chunk baseline pilot succeeded:

```bash
uv run --extra embedding python scripts/pilot_bge_m3_embeddings.py \
  --input data/processed/legal_chunks.jsonl \
  --config configs/indexing/embedding_indexing.yml \
  --output /tmp/bge_m3_embedding_pilot_report.json \
  --limit 10 \
  --batch-size 2 \
  --template text_only \
  --device cpu
```

Summary:

```text
Samples: 10
Dense dimension: 1024
Device: cpu
Runtime seconds: 64.157554
Throughput: 0.156 chunks/s
Report: /tmp/bge_m3_embedding_pilot_report.json
```

Diagnostics: 10 vectors, no empty/NaN/Inf vectors, no dimension mismatches,
mean norm approximately 1.0, and batch-size stability passed. The maximum
absolute difference was `1.063515910407209e-07`.

The 100-chunk CPU pilot also succeeded:

```bash
uv run --extra embedding python scripts/pilot_bge_m3_embeddings.py \
  --input data/processed/legal_chunks.jsonl \
  --config configs/indexing/embedding_indexing.yml \
  --output /tmp/bge_m3_embedding_pilot_report_100.json \
  --limit 100 \
  --batch-size 4 \
  --template text_only \
  --device cpu
```

Summary:

```text
Samples: 100
Dense dimension: 1024
Device: cpu
Runtime seconds: 83.946154
Throughput: 1.191 chunks/s
Report: /tmp/bge_m3_embedding_pilot_report_100.json
```

The report recorded:

```text
status: success
actual_sample_count: 100
vector_count: 100
dense_dimension: 1024
dimensions_observed: [1024]
empty_vector_count: 0
nan_vector_count: 0
inf_vector_count: 0
dimension_mismatch_count: 0
zero_or_near_zero_norm_count: 0
norm_min: 0.9999999999999991
norm_max: 1.000000000000002
norm_mean: 1.0000000000000007
norm_p50: 1.0000000000000004
norm_p95: 1.0000000000000018
failed_chunk_ids: []
issues: []
batch_size_stable: true
primary_batch_size: 4
comparison_batch_size: 1
comparison_sample_count: 4
max_absolute_difference: 9.562628434933718e-08
```

### Interpretation

- BGE-M3 dense embedding is operational on CPU.
- The measured dense dimension is 1024.
- Dense vectors are normalized to approximately unit norm.
- No invalid vectors were observed in the 100-chunk pilot.
- Batch-size stability passed with negligible floating-point differences.
- CPU throughput was approximately 1.19 chunks/s at batch size 4.
- Full-corpus CPU indexing may still be slow and requires another benchmark
  before Slice 8F to estimate runtime and select a safe batch size.
- CUDA/GPU is not validated. A prior environment check produced an NVIDIA
  driver warning, so CPU remains the validated execution path.

## Slice 8D Summary

Slice 8D adds:

- deterministic `LegalChunk` to `VectorPayload` mapping;
- preservation of citation, hierarchy, Article/Clause/Point fields, exact
  `text` and `parent_text`, hashes, source fields, metadata, and warnings;
- embedding model, optional revision, payload schema, and indexing run
  provenance;
- explicit null/empty storage for unknown temporal, status, and domain fields
  without inference;
- deterministic UUIDv5 point IDs derived from namespace and original
  `chunk_id`;
- JSON-compatible payload serialization that retains null enrichment fields.

It does not generate or persist vectors, load BGE-M3, connect to Qdrant,
create collections, upsert points, index the corpus, or implement retrieval.

## Slice 8E Summary

Slice 8E adds:

- an async Qdrant collection setup layer with lazy optional dependency loading;
- a named `dense` vector schema using the measured BGE-M3 dimension of 1024;
- optional named sparse-vector configuration, disabled by default;
- deterministic payload indexes for `law_id`, chunk hierarchy fields, repeal
  metadata, source domain, and Article number;
- safe existing-collection validation with explicit recreation only;
- a collection-only CLI with a no-connection `--dry-run` mode;
- fake-client unit tests that do not require Qdrant, Docker, BGE-M3, or
  internet access.

The default setup is non-destructive: `recreate=false`. A matching collection
is retained, while a mismatched collection fails unless recreation is
explicitly requested. Python payloads continue to retain null temporal and
status fields; Qdrant server payload behavior must be checked before full
indexing, and this slice does not change the null policy.

It does not load BGE-M3, generate vectors, read the processed corpus, upsert
points, perform full indexing, implement retrieval, or write official reports.

Slice 8E server-backed Qdrant smoke test:
- Local Qdrant URL: http://localhost:6333
- Dev collection: vnlaw_chunks_bgem3_v1_dev
- Collection status: green
- Dense vector: dense, size 1024, distance Cosine
- Payload indexes: law_id, chunk_kind, level, metadata.is_empty_or_repealed, metadata.is_source_unit_repealed, source_domain, article_number
- points_count: 0, expected because 8E does not index corpus points
- Idempotency check: pass, existing matching collection returns already_exists
- Mismatch protection: pass, requesting dense dimension 768 fails without recreate

## Slice 8F Summary

Slice 8F adds:

- an async indexing service connecting the validated chunk loader, embedding
  input mapper, BGE-M3 dense wrapper, payload builder, deterministic UUIDv5
  point IDs, and Qdrant upsert;
- bounded batch processing with input-order preservation and explicit
  per-batch failure accounting;
- dense vector count, name, order, and measured 1024-dimension validation;
- a non-mutating dry-run path that builds embedding inputs, payloads, and
  point IDs without loading BGE-M3 or calling Qdrant;
- typed success, partial-success, failed, and dry-run reports;
- optional atomic JSON checkpoints;
- a safe CLI that requires `--limit` for real indexing unless
  `--allow-full-corpus` is explicitly supplied;
- protected-path rejection for experimental reports and checkpoints.

The three-chunk real-corpus dry-run succeeded without loading BGE-M3 or
contacting Qdrant:

```text
collection: vnlaw_chunks_bgem3_v1_dev
limit: 3
batch size: 2
status: dry_run
planned: 3
embedded/upserted/failed: 0/0/0
report: /tmp/vnlaw_phase8_8f_dry_run_report_3.json
```

A bounded real CPU smoke also succeeded using the cached BGE-M3 model:

```text
collection: vnlaw_chunks_bgem3_v1_dev
limit: 3
batch size: 2
dense dimension: 1024
status: success
embedded/upserted/failed: 3/3/0
runtime seconds: 157.312994
throughput: 0.0191 chunks/s
Qdrant points_count after smoke: 3
report: /tmp/vnlaw_phase8_8f_indexing_report_3.json
checkpoint: /tmp/vnlaw_phase8_8f_checkpoint_3.json
```

### Post-Index Validation

The local Qdrant collection remained healthy after the tiny smoke:

```text
collection: vnlaw_chunks_bgem3_v1_dev
status: green
optimizer_status: ok
points_count: 3
vectors.dense.size: 1024
vectors.dense.distance: Cosine
```

Payload indexes were populated for all three points:

```text
law_id
chunk_kind
level
article_number
source_domain
metadata.is_empty_or_repealed
metadata.is_source_unit_repealed
```

Point scrolling confirmed that persisted payloads retain the original
`chunk_id`, legal citation and hierarchy, exact `text` and `parent_text`,
source fields, hashes, metadata, warnings, embedding provenance, indexing run
ID, and nullable temporal/status/domain fields. Vector scrolling confirmed
that each point contains the named `vector.dense` data.

A payload filter for `law_id = BLDS_2015` returned matching points. This
confirms that legal traceability fields survived indexing and that the
configured payload filtering works.

`points_count = 3` is expected for this tiny smoke. Qdrant may report
`indexed_vectors_count = 0` for very small collections because it may not
build a full vector index below its optimization/indexing threshold. For this
smoke, `points_count`, persisted named vectors, and payload/filter validation
are the relevant checks.

No full-corpus indexing was performed. Protected corpus and official report
paths were unchanged. The low three-chunk throughput includes model startup
and is not a reliable full-corpus estimate; rerun a larger benchmark before
an operational indexing run.

### Slice 8F Verification

Final verification passed:

```text
Phase 7 gate: pass_with_warnings
Phase 7 errors/invalid chunks: 0/0
Phase 7 payload readiness: 1.0
Indexing tests: 107 passed
Processing tests: 351 passed
Python compilation: passed
Ruff lint and format check: passed
uv lock --check: passed
git diff --check: passed
Protected paths: unchanged
```

Intermediate environment and formatting failures were corrected before the
final checks. They included a missing `python` command, restricted uv cache
access, initial pytest import failures for `src` and `scripts`, sandboxed curl
access to local Qdrant, and one Ruff formatting correction.

### Known Limitations

- No retrieval service or query embedding CLI exists.
- Sparse indexing remains unimplemented and disabled.
- Failed batches are reported, but automatic retries are not implemented.
- Checkpoints record progress but cannot resume a run yet.
- The indexing service does not create or recreate collections.
- No official production indexing report was generated.
- The CLI does not ingest the Phase 7 report directly, so run reports
  conservatively record the gate status as `not_run`.
- No full-corpus indexing was performed.

## Verification

```bash
uv run python scripts/validate_processed_jsonl.py \
  --input data/processed/legal_chunks.jsonl \
  --config configs/processing/processed_jsonl_validation.yml \
  --output /tmp/processed_jsonl_validation_report.json \
  --pretty
uv run python -m py_compile src/indexing/indexing_models.py src/indexing/chunk_loader.py \
  src/indexing/embedding_model.py src/indexing/payload_builder.py \
  src/indexing/qdrant_collection.py src/indexing/indexing_service.py \
  scripts/setup_qdrant_collection.py scripts/index_qdrant_chunks.py
uv run pytest tests/unit/indexing/test_indexing_models.py \
  tests/unit/indexing/test_chunk_loader.py \
  tests/unit/indexing/test_embedding_model.py \
  tests/unit/indexing/test_payload_builder.py \
  tests/unit/indexing/test_qdrant_collection.py \
  tests/unit/indexing/test_indexing_service.py -q
uv run pytest tests/unit/processing -q
uv run ruff check src/indexing/indexing_models.py src/indexing/chunk_loader.py \
  src/indexing/embedding_model.py src/indexing/payload_builder.py \
  src/indexing/qdrant_collection.py src/indexing/indexing_service.py \
  scripts/setup_qdrant_collection.py scripts/index_qdrant_chunks.py \
  tests/unit/indexing/test_indexing_models.py tests/unit/indexing/test_chunk_loader.py \
  tests/unit/indexing/test_embedding_model.py tests/unit/indexing/test_payload_builder.py \
  tests/unit/indexing/test_qdrant_collection.py \
  tests/unit/indexing/test_indexing_service.py
uv run ruff format --check src/indexing/indexing_models.py src/indexing/chunk_loader.py \
  src/indexing/embedding_model.py src/indexing/payload_builder.py \
  src/indexing/qdrant_collection.py src/indexing/indexing_service.py \
  scripts/setup_qdrant_collection.py scripts/index_qdrant_chunks.py \
  tests/unit/indexing/test_indexing_models.py tests/unit/indexing/test_chunk_loader.py \
  tests/unit/indexing/test_embedding_model.py tests/unit/indexing/test_payload_builder.py \
  tests/unit/indexing/test_qdrant_collection.py \
  tests/unit/indexing/test_indexing_service.py
uv lock --check
git diff --check
git status --short data/raw data/interim data/reports data/processed artifacts/reports
```

## Next Slice

Slice 8G should implement operational CLI hardening, retries, resumability,
and Phase 7 gate integration:

- resume from a validated checkpoint;
- apply a bounded retry policy to failed batches;
- ingest and enforce a fresh Phase 7 gate report;
- record stronger run and environment metadata;
- document a safe operational runbook;
- verify idempotent reruns using deterministic point IDs;
- run controlled limits of 10, 100, then 1,000 before considering full corpus;
- reconcile report counts with Qdrant point counts.

Before any full indexing run, rerun a larger pilot or benchmark to estimate
full-corpus CPU runtime and determine a safe batch size.
