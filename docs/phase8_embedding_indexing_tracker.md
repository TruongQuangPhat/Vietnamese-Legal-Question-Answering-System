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
| 8C | Embedding model pilot | Not started | BGE-M3 pilot only; measure dense dimension |
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

## Verification

```bash
uv run python scripts/validate_processed_jsonl.py \
  --input data/processed/legal_chunks.jsonl \
  --config configs/processing/processed_jsonl_validation.yml \
  --output /tmp/processed_jsonl_validation_report.json \
  --pretty
uv run python -m py_compile src/indexing/indexing_models.py src/indexing/chunk_loader.py
uv run pytest tests/unit/indexing/test_indexing_models.py \
  tests/unit/indexing/test_chunk_loader.py -q
uv run pytest tests/unit/processing -q
uv run ruff check src/indexing/indexing_models.py src/indexing/chunk_loader.py \
  tests/unit/indexing/test_indexing_models.py tests/unit/indexing/test_chunk_loader.py
uv run ruff format --check src/indexing/indexing_models.py src/indexing/chunk_loader.py \
  tests/unit/indexing/test_indexing_models.py tests/unit/indexing/test_chunk_loader.py
git diff --check
git status --short data/raw data/interim data/reports data/processed artifacts/reports
```

## Next Slice

Slice 8C remains the planned next slice: a constrained BGE-M3 embedding model
pilot that measures dense output dimension from the actual model. Slice 8D
remains responsible for building Qdrant payloads.
