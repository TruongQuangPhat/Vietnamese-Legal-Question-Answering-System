# Embedding & Indexing Pipeline

## Overview

The Embedding & Indexing phase transforms validated legal chunks into vector embeddings and builds a hybrid search index. This phase starts only after processed JSONL validation is stable and all 52 laws have passed quality gates.

The index enables retrieval of relevant legal provisions based on semantic similarity and keyword matching. Metadata filtering supports time-aware queries and corpus subsetting.

## Quick Start

**Intended CLI** (design phase, not yet implemented):

```bash
uv run python scripts/build_embedding_index.py \
  --input data/processed/legal_chunks.jsonl \
  --qdrant-url http://localhost:6333 \
  --collection-name vnlaw_qa_chunks \
  --batch-size 32
```

**Expected workflow**:
1. Input: `data/processed/legal_chunks.jsonl`
2. Model: Load embedding model (e.g., BGE-M3)
3. Process: Generate dense + sparse vectors in batches
4. Output: Qdrant collection `vnlaw_qa_chunks` with full payload
5. Validation: Collection size matches chunk count; hybrid search works.

## Architecture

```
┌──────────────────────┐
│  Processed JSONL     │
│  legal_chunks.jsonl  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Chunk               │
│  Loader              │
│  (streaming)         │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Embedding           │
│  Model               │
│  (BGE-M3)            │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Vector              │
│  Payload             │
│  Builder             │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Vector Store        │
│  Writer              │
│  (Qdrant)            │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Index               │
│  Validator           │
└──────────────────────┘
```

## Components

### 1. Chunk Loader

**Goal**: Stream chunks from JSONL files without loading everything into memory.

**Process**:
- Iterate over all `data/processed/*.jsonl` files.
- For each file, read line by line → `json.loads(line)`.
- Yield `ProcessedChunk` objects (Pydantic validated).
- Track total count and file statistics.

**Output**: Async generator of chunk dicts.

### 2. Embedding Model

**Goal**: Generate dense and sparse vector representations for each chunk.

**Model selection criteria**:
- Vietnamese language support (trained on Vietnamese corpus or multilingual).
- Native sparse + dense output (e.g., BGE-M3) or separate sparse encoder (BM25).
- Dimension: dense vector ~1024 for BGE-M3.
- Throughput: can process thousands of chunks in reasonable time.

**Candidate models** (evaluation needed):
- `BAAI/bge-m3` — multilingual, dense+sparse, 1024 dims.
- `intfloat/multilingual-e5-large` — dense only, may need separate BM25.
- Vietnamese-specific embeddings (if available).

**Batch inference**:
- Use async batching (e.g., `asyncio.gather` on batches of 32–64 texts).
- Model loading with `sentence-transformers` or custom wrapper.
- Cache embeddings if re-indexing (avoid recompute unchanged chunks).

**Output per chunk**:
- `dense_vector`: list[float] of length 1024 (or model dim)
- `sparse_vector`: dict{token_id: weight} or BM25 scores on tokenized text

### 3. Vector Payload Builder

**Goal**: Construct Qdrant point payload with all metadata needed for retrieval and filtering.

**Payload structure**:
```python
{
    "vector": dense_vector,
    "sparse_vector": sparse_vector,  # optional, for hybrid
    "law_id": "LDD_VBHN",
    "law_name": "Luật Đất đai (VBHN 2025)",
    "law_type": "law",
    "legal_status": "active",
    "article_number": "123",
    "article_title": "Điều 123. ...",
    "clause_number": "2",  # nullable
    "point_label": "c",   # nullable
    "hierarchy_path": {...},  # as in chunk
    "citation": "Luật Đất đai (VBHN 2025), Điều 123, Khoản 2, Điểm c",
    "source_url": "https://...",
    "source_domain": "thuvienphapluat.vn",
    "source_type": "html",
    "effective_date": "2025-01-01",
    "expiry_date": null,
    "text_hash": "sha256:...",
    "text": "Nội dung..."  # optional: store original text for debugging
}
```

**Important**: Do not store `parent_text` in vector payload (too large). Store only `text` and metadata.

### 4. Vector Store Writer

**Goal**: Upsert vectors and payloads into Qdrant collection.

**Qdrant configuration**:
- Collection name: `vnlaw_qa_chunks`
- Distance metric: `Cosine` (or `Dot` for normalized embeddings)
- Vector params:
  - `dense`: size = model dim, distance = Cosine
  - `sparse`: indexed if using hybrid
- HNSW parameters for approximate nearest neighbor search.

**Upsert strategy**:
- Batch upserts (e.g., 100–500 points per batch).
- Use `client.upsert(collection_name, points=batch)`.
- Point ID = `chunk_id` (deterministic, allows idempotent re-runs).
- Payload includes all metadata fields listed above.

**Idempotency**: Re-running indexing with same chunks should not create duplicates; `chunk_id` as point ID ensures upsert replaces existing.

### 5. Index Validator

**Goal**: Verify index correctness after write.

**Checks**:
- Collection info: `points_count` equals total number of processed chunks (across 52 laws).
- Sample search: run a simple query vector (e.g., embedding of "đất đai") → returns top-k results with valid `chunk_id`.
- Metadata filters work: filter by `law_id`, `effective_date` range.
- Hybrid search: if sparse vectors stored, verify dense-only, sparse-only, and hybrid (RRF) queries succeed.

**Failure handling**:
- Count mismatch → log error; may indicate missed chunks or duplicate IDs.
- Filter failure → check payload schema; missing fields cause filter errors.
- Search failure → investigate vector format or collection config.

**Success**: Index is ready for retrieval.

## Pipeline Execution Flow

1. Load validated `data/processed/legal_chunks.jsonl` rows.
2. Initialize embedding model (download if needed).
3. For each chunk in streaming batches:
   - Compute dense vector via model.
   - Compute sparse vector (BM25 on tokenized text or model output).
   - Build payload dict with all metadata.
   - Create Qdrant `PointStruct` with `id=chunk_id`, `vector=dense`, `sparse_vector=sparse`, `payload=payload`.
   - Append to batch.
4. Upsert batch to Qdrant collection (create collection if not exists).
5. Repeat until all chunks indexed.
6. Run Index Validator:
   - Get collection info → count check.
   - Execute test queries (with/without filters).
   - Verify sample results have expected payload fields.
7. Write index report: `artifacts/reports/indexing/indexing_validation.json`.

## Data Models / Output Schema

### Qdrant Collection Configuration

```python
from qdrant_client.models import Distance, VectorParams, SparseVectorParams

client.create_collection(
    collection_name="vnlaw_qa_chunks",
    vectors_config={
        "dense": VectorParams(size=1024, distance=Distance.COSINE)
    },
    sparse_vectors_config={
        "sparse": SparseVectorParams()
    },
    hnsw_config=HnswConfigDiff(m=16, ef_construct=100)
)
```

### Point Payload Schema

Same as `ProcessedChunk` but without `parent_text` and optionally without `text` (can be omitted if storage cost high). Keep:
- `law_id`, `law_name`, `law_type`, `legal_status`
- `article_number`, `article_title`, `clause_number`, `point_label`
- `hierarchy_path`
- `citation`, `source_url`, `source_domain`, `source_type`
- `effective_date`, `expiry_date`, `issued_date`
- `text_hash`, `metadata`

### Index Validation Report

```json
{
  "collection_name": "vnlaw_qa_chunks",
  "timestamp": "2025-01-01T12:00:00Z",
  "total_chunks_processed": 15000,
  "collection_points_count": 15000,
  "count_match": true,
  "test_queries": [
    {
      "query": "đất đai",
      "top_k": 5,
      "retrieved_chunk_ids": ["LDD_VBHN__article_1__clause_1", ...],
      "all_have_required_payload": true
    }
  ],
  "metadata_filter_tests": [
    {
      "filter": {"law_id": "LDD_VBHN"},
      "expected_min_results": 100,
      "actual": 120,
      "pass": true
    }
  ],
  "errors": [],
  "warnings": []
}
```

## CLI Reference

### Main Command

```bash
# Full indexing for all laws
uv run python scripts/build_embedding_index.py \
  --input-dir data/processed \
  --qdrant-url http://localhost:6333 \
  --collection-name vnlaw_qa_chunks \
  --model-name BAAI/bge-m3 \
  --batch-size 32

# Specific laws only
uv run python scripts/build_embedding_index.py \
  --law-ids LDD_VBHN BLDS_2015 \
  --input-dir data/processed \
  --output-dir artifacts/reports/indexing

# Validate existing index without re-indexing
uv run python scripts/build_embedding_index.py \
  --validate-only \
  --qdrant-url http://localhost:6333 \
  --collection-name vnlaw_qa_chunks

# Delete and recreate collection (fresh start)
uv run python scripts/build_embedding_index.py \
  --recreate-collection \
  --collection-name vnlaw_qa_chunks
```

**Arguments**:
- `--input-dir`: Directory containing `{law_id}.jsonl` files (default: `data/processed`)
- `--qdrant-url`: Qdrant server URL (default: `http://localhost:6333`)
- `--qdrant-api-key`: API key if authentication enabled.
- `--collection-name`: Target collection (default: `vnlaw_qa_chunks`)
- `--model-name`: Embedding model HuggingFace ID or local path.
- `--batch-size`: Number of chunks per embedding batch (default: 32)
- `--law-ids`: Specific laws to index; if omitted, all found.
- `--validate-only`: Only run validator, do not index.
- `--recreate-collection`: Drop and recreate collection (warning: data loss).

## Testing

**Unit tests**:
- `test_payload_builder()`: given a `ProcessedChunk`, produces payload with required fields.
- `test_sparse_vector_generation()`: BM25 produces non-zero weights for tokenized text.
- `test_chunk_id_as_point_id()`: deterministic ID used as Qdrant point ID.
- `test_metadata_filter_payload()`: filter by `law_id` and `effective_date` works.

**Integration tests**:
- Index small corpus (10 laws) → collection count matches chunk count.
- Search test: query for "đất đai" returns at least one LDD law chunk.
- Filter test: filter `{"law_id": "BLDS_2015"}` returns only BLDS chunks.
- Re-run indexing on same data → no duplicates, count unchanged.

## Error Handling

- **Qdrant connection failure**: `ConnectionError`; log and retry with backoff; abort after N attempts.
- **Model load failure**: `OSError` (missing weights); download or fix path.
- **Upsert failure**: Partial failure → retry batch; if persistent, log failed chunk IDs and continue.
- **Validation failure**: Count mismatch → log error; investigate missing chunks.
- **Disk full**: `OSError`; abort immediately.

All errors include collection name and batch range for debugging.

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| Collection count < expected | Some chunks failed to upsert | Compare `data/processed/*.jsonl` line counts vs collection count | Check logs for upsert errors; retry failed batches |
| Search returns no results | Embedding model not loaded correctly OR vectors all zero | Run test query with known similar term; inspect vector norms | Verify model outputs non-zero vectors; check collection has vectors |
| Filter by `effective_date` fails | Payload missing field or wrong type | Query with filter and check error message | Ensure `effective_date` present in all payloads and in `YYYY-MM-DD` format |
| Out of memory during embedding | Batch size too large | Monitor RAM usage; OOM killer | Reduce `--batch-size`; use smaller model |
| Sparse vectors not indexed | Qdrant collection created without sparse config | Check collection info via Qdrant console | Recreate collection with `sparse_vectors_config` |
| Slow indexing throughput | Model too large or CPU-bound | Measure time per batch | Use GPU if available; optimize batch size; consider smaller model |
| Duplicate points in collection | `chunk_id` changed between runs | Search for same `chunk_id` appears multiple times | Ensure `chunk_id` is deterministic; delete and re-index if needed |

## Best Practices

- **Idempotent indexing** — same input should produce identical index state; use deterministic `chunk_id` as point ID.
- **Batch size tuning** — balance throughput vs memory; start with 32, adjust based on model size.
- **Monitor count** — always validate `collection_points_count == total_chunks` before proceeding to retrieval.
- **Keep raw JSONL** — do not delete `data/processed/` after indexing; serves as backup for re-index.
- **Version model** — record model name and revision in `metadata` of each point for reproducibility.
- **Test filters early** — verify `law_id` and `effective_date` filters work before large-scale indexing.

## Changelog

### Version 0.1 (2026-05-21)

- Created initial embedding & indexing documentation.
- Defined components: chunk loader, embedding model (BGE-M3 example), payload builder, Qdrant writer, validator.
- Specified vector schema (dense + sparse) and metadata payload fields.
- Provided index validation report schema with count and filter tests.
- Documented CLI arguments and testing strategy.
- Added troubleshooting for common indexing failures.

## Related Documentation

| Document | Status | Description |
|----------|--------|-------------|
| `docs/project_phase_journal.md` | Existing | Project phase journal and pipeline notes |
| `docs/project_setup.md` | Implemented | Environment setup and coding standards |
| `docs/corpus_registry.md` | Implemented | Corpus registry schema and design |
| `docs/raw_corpus_audit.md` | Designed | Raw artifact audit procedure |
| `docs/cleaning_normalization.md` | Existing | HTML-to-text and Unicode normalization |
| `docs/legal_parsing.md` | Existing | Legal hierarchy parsing algorithm |
| `docs/parent_child_chunking.md` | Existing | Parent-child chunking design |
| `docs/processed_jsonl.md` | Existing | JSONL export schema and validation |
| `docs/naive_rag.md` | Future extension | Baseline RAG implementation |
| `docs/advanced_rag.md` | Future extension | Hybrid retrieval, reranking, time-aware filtering |
