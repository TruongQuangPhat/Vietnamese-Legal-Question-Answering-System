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
| 8D | Payload builder | Not started | Preserve legal metadata and warnings |
| 8E | Qdrant collection setup | Not started | Named dense vector, sparse optional |
| 8F | Indexing service | Not started | Batch embed/upsert/checkpoint |
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

## Verification

```bash
uv run python scripts/validate_processed_jsonl.py \
  --input data/processed/legal_chunks.jsonl \
  --config configs/processing/processed_jsonl_validation.yml \
  --output /tmp/processed_jsonl_validation_report.json \
  --pretty
uv run python -m py_compile src/indexing/indexing_models.py src/indexing/chunk_loader.py \
  src/indexing/embedding_model.py scripts/pilot_bge_m3_embeddings.py
uv run pytest tests/unit/indexing/test_indexing_models.py \
  tests/unit/indexing/test_chunk_loader.py \
  tests/unit/indexing/test_embedding_model.py -q
uv run pytest tests/unit/processing -q
uv run ruff check src/indexing/indexing_models.py src/indexing/chunk_loader.py \
  src/indexing/embedding_model.py scripts/pilot_bge_m3_embeddings.py \
  tests/unit/indexing/test_indexing_models.py tests/unit/indexing/test_chunk_loader.py \
  tests/unit/indexing/test_embedding_model.py
uv run ruff format --check src/indexing/indexing_models.py src/indexing/chunk_loader.py \
  src/indexing/embedding_model.py scripts/pilot_bge_m3_embeddings.py \
  tests/unit/indexing/test_indexing_models.py tests/unit/indexing/test_chunk_loader.py \
  tests/unit/indexing/test_embedding_model.py
git diff --check
git status --short data/raw data/interim data/reports data/processed artifacts/reports
```

## Next Slice

Slice 8D should build the traceability-preserving payload contract mapping
before Qdrant collection setup or full indexing begins.

Before full indexing in Slice 8F, rerun a larger pilot or benchmark to estimate
full-corpus CPU runtime and determine a safe batch size.
