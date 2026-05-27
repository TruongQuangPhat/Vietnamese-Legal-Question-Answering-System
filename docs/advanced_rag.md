# Advanced RAG: Hybrid Retrieval & Reranking

## Overview

The Advanced RAG phase upgrades the Naive RAG baseline with hybrid dense+sparse retrieval, Reciprocal Rank Fusion (RRF), cross-encoder reranking, and time-aware law filtering. This phase improves retrieval precision, especially for queries that benefit from keyword matching or require the most current legal version.

Advanced RAG builds directly on top of Naive RAG and the embedding index; it does not replace the baseline but refines the retrieval stage only.

## Quick Start

**Intended API behavior** (design phase, not yet implemented):

```bash
curl -X POST "http://localhost:8000/api/v1/qa" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Quy định về hình phạt tù cho tội phạm tham nhũng?",
    "use_advanced": true,
    "rerank_top_k": 5,
    "effective_date": "2025-01-01"
  }'
```

**Expected improvements over Naive RAG**:
- Higher precision in top-k retrieval (more relevant chunks)
- Better handling of legal terminology via sparse search
- Time filtering ensures only currently effective laws are retrieved
- Cross-encoder reranking reorders results for maximum relevance

## Architecture

```
┌──────────────────────┐
│  User Query          │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Query               │
│  Embedding           │
│  (dense + sparse)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Hybrid              │
│  Retrieval           │
│  (dense + sparse     │
│   parallel)          │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Reciprocal          │
│  Rank Fusion         │
│  (RRF)               │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Cross-Encoder       │
│  Reranker            │
│  (e.g., BGE-Reranker)│
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Time-aware          │
│  Filtering           │
│  (effective_date)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Context             │
│  Packing             │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  LLM                 │
│  Generation          │
└──────────────────────┘
```

## Components

### 1. Dense + Sparse Query Embedding

**Goal**: Generate both dense vector and sparse BM25-like representation for hybrid retrieval.

**Process**:
- Dense: Same embedding model as indexing (BGE-M3) → `dense_vector`.
- Sparse: Tokenize query with same tokenizer used during BM25 indexing (or use model's native sparse output if available).
- Normalize sparse vector to unit sum (optional).

**Output**:
- `dense_vector`: list[float] (1024 dims for BGE-M3)
- `sparse_vector`: dict{token_id: weight} or list of (token, score) pairs

### 2. Hybrid Retrieval (Parallel Dense & Sparse)

**Goal**: Fetch candidates using both similarity modalities.

**Two independent searches**:
1. **Dense-only**: cosine similarity on `dense_vector` → top-k_dense (e.g., 50)
2. **Sparse-only**: BM25 or dot product on `sparse_vector` → top-k_sparse (e.g., 50)

**Qdrant query**:
```python
dense_results = client.search(
    collection_name=collection,
    query_vector=("dense", dense_vector),
    limit=k_dense,
    with_payload=True
)

sparse_results = client.search(
    collection_name=collection,
    query_vector=("sparse", sparse_vector),
    limit=k_sparse,
    with_payload=True
)
```

**Note**: If using a single model that outputs both, Qdrant supports hybrid search with `fusion_type` (e.g., `rrf`), but for maximum control we run two separate queries and fuse manually.

### 3. Reciprocal Rank Fusion (RRF)

**Goal**: Merge dense and sparse result lists into a single ranked set.

**RRF algorithm**:
- For each unique chunk ID appearing in either list, compute:
  ```
  rrf_score = 0
  if chunk in dense_results:
      rank_dense = position in dense_results (starting at 1)
      rrf_score += 1 / (k + rank_dense)  # k=60 common default
  if chunk in sparse_results:
      rank_sparse = position in sparse_results
      rrf_score += 1 / (k + rank_sparse)
  ```
- Sort all chunks by `rrf_score` descending.
- Take top-k_final (e.g., 20) for reranking.

**Advantages**:
- Does not require score normalization (dense vs sparse scores not comparable).
- Simple, robust, and widely used in hybrid search.

**Implementation notes**:
- Use `k=60` (standard RRF parameter).
- Ties broken by secondary sort (e.g., dense score then sparse score).

### 4. Cross-Encoder Reranking

**Goal**: Re-score the top-k_final candidates with a more powerful (but slower) cross-encoder model for maximum precision.

**Model selection**:
- Cross-encoder models take `(query, document)` pairs and output relevance score (0–1 or logit).
- Examples: `BAAI/bge-reranker-large`, `cross-encoder/ms-marco-MiniLM-L-6-v2` (English), or Vietnamese-capable reranker if available.

**Process**:
- Take top-k_final from RRF (e.g., 20).
- For each chunk, form text pair: `query` + `chunk.text`.
- Run batch inference through cross-encoder → `rerank_score` per chunk.
- Sort by `rerank_score` descending.
- Keep top-k_reranked (e.g., 5–10) for context packing.

**Cost/Latency trade-off**:
- Cross-encoder is slower than bi-encoder (dense retrieval) but only runs on 20–50 candidates, not entire corpus.
- Expected added latency: 100–300ms for 20 candidates on CPU; faster on GPU.

**Output**: Final ranked list of chunks with `rerank_score` (overwrites or supplements retrieval score).

### 5. Time-Aware Law Filtering

**Goal**: Ensure retrieved provisions are legally effective at the query's relevant date.

**Use case**: User asks "What is the penalty for X?" without specifying a date. System should return current law, not repealed version.

**Mechanism**:
- Each chunk has `effective_date` and `expiry_date` (nullable).
- Determine query context date:
  - If query explicitly mentions a date (e.g., "in 2020"), parse and use that.
  - Else default to today's date (or configuration `default_effective_date`).
- Filter final retrieved chunks: keep only those where `effective_date <= query_date` and (`expiry_date` is null or `query_date < expiry_date`).
- If filtering removes all chunks, fall back to unfiltered results or trigger fallback (configurable).

**Implementation**:
- Apply filter after reranking (before context packing) to avoid losing relevant results due to date mismatch.
- Record in `metadata` whether date filtering was applied and how many chunks were dropped.

**Example**:
```python
query_date = parse_query_date(query) or date.today()
filtered_chunks = [
    c for c in reranked_chunks
    if c.effective_date <= query_date and (c.expiry_date is None or query_date < c.expiry_date)
]
if not filtered_chunks:
    # Option 1: use unfiltered with warning
    # Option 2: fallback with message "No current regulation found"
    pass
```

### 6. Query Decomposition (Optional)

**Goal**: Handle complex multi-part questions by breaking into sub-queries.

**When needed**: If query contains multiple distinct legal issues (e.g., "What are the requirements for marriage and divorce?").
**Approach**:
- Use LLM to decompose query into simpler sub-queries.
- Run retrieval for each sub-query independently.
- Merge results (deduplicate, re-rank by max score across sub-queries).
- Pack merged context; generate answer.

**Status**: Optional enhancement; may be part of Advanced RAG or deferred to GraphRAG.

## Pipeline Execution Flow

1. Receive query via API with optional `effective_date` and `use_advanced` flag.
2. Generate dense + sparse query embeddings.
3. Run parallel searches: dense top-50 and sparse top-50 from Qdrant.
4. Apply RRF to merge dense + sparse results → top-20 unique chunks.
5. Load cross-encoder reranker model.
6. Rerank top-20 with cross-encoder → top-5–10 chunks.
7. Apply time-aware filtering using query date (today by default).
8. Pack filtered chunks into context with citations.
9. Construct strict legal prompt (from Naive RAG) and call Claude API.
10. Run citation validator on generated answer.
11. Compute confidence (base = average rerank scores).
12. Return answer if confidence ≥ threshold and citations valid; else fallback.

## Data Models / Output Schema

### Advanced RAG Request (extends Naive RAG)

```json
{
  "query": "Quy định về hình phạt tù cho tội phạm tham nhũng?",
  "max_chunks": 10,
  "confidence_threshold": 0.75,
  "use_advanced": true,
  "effective_date": "2025-01-01",
  "rerank_top_k": 5,
  "retrieval_k_dense": 50,
  "retrieval_k_sparse": 50,
  "rrf_k": 60
}
```

### Advanced RAG Response (same as Naive RAG but with extra metadata)

```json
{
  "answer": "...",
  "citations": [...],
  "confidence": 0.89,
  "retrieved_chunks": [
    {
      "chunk_id": "...",
      "score": 0.92,
      "rerank_score": 0.95,
      "dense_rank": 3,
      "sparse_rank": 5,
      "payload": {...}
    }
  ],
  "fallback": false,
  "processing_time_ms": 1450,
  "advanced_retrieval": {
    "num_dense_results": 50,
    "num_sparse_results": 50,
    "num_rrf_fused": 20,
    "num_after_rerank": 8,
    "num_after_date_filter": 8,
    "date_filter_applied": true,
    "query_date": "2025-01-01"
  }
}
```

### Internal Metrics (for logging/evaluation)

```json
{
  "retrieval": {
    "dense_latency_ms": 45,
    "sparse_latency_ms": 38,
    "rrf_latency_ms": 2,
    "rerank_latency_ms": 180,
    "date_filter_latency_ms": 1
  }
}
```

## CLI Reference

### Testing Advanced Retrieval Standalone

```bash
# Run hybrid retrieval without generation
uv run python -m src.retrieval.advanced \
  --query "Quy định về hình phạt tù?" \
  --qdrant-url http://localhost:6333 \
  --collection-name vnlaw_qa_chunks \
  --output-format json \
  --k-dense 50 \
  --k-sparse 50 \
  --rerank-top-k 5 \
  --effective-date 2025-01-01
```

### Compare Naive vs Advanced

```bash
# Naive retrieval
uv run python -m src.retrieval.naive --query "..." --output naive_results.json

# Advanced retrieval
uv run python -m src.retrieval.advanced --query "..." --output advanced_results.json

# Compare metrics (precision, recall against golden set)
uv run python -m src.evaluation.compare --naive naive_results.json --advanced advanced_results.json --golden data/eval/golden_qa.jsonl
```

## Testing

**Unit tests**:
- `test_rrf_fusion()`: given two ranked lists, RRF produces correct fused ranking.
- `test_cross_encoder_rerank()`: reranker runs on batch, scores in [0,1], reorders correctly.
- `test_time_filter()`: chunks outside date range excluded; boundary dates handled correctly.
- `test_hybrid_retrieval_parallel()`: dense and sparse queries execute concurrently.

**Integration tests**:
- End-to-end retrieval: query → hybrid → RRF → rerank → filtered chunks.
- Measure precision@k compared to naive retrieval; expect improvement (target +10–20%).
- Latency budget: advanced retrieval < 500ms added over naive retrieval.

**A/B testing**:
- Route some production traffic to advanced retrieval; compare evaluation metrics (recall, citation match, answer quality).
- Roll back if regression detected.

## Error Handling

- **Cross-encoder model load failure**: Fall back to RRF scores only (skip rerank); log warning.
- **Sparse vector missing**: If chunk collection lacks sparse vectors, skip sparse search; use dense-only.
- **Date parsing failure**: Invalid `effective_date` format → return 400; use today's date if parameter omitted.
- **All chunks filtered by date**: Log warning; either use unfiltered (configurable) or trigger fallback.
- **RRF ties**: Deterministic secondary sort ensures consistent results.

All errors include `query_id` for tracing; partial results still returned if possible.

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| Rerank latency too high | Cross-encoder model too large OR batch size too small | Profile rerank stage time | Use smaller reranker model; increase batch size; consider GPU |
| No improvement over naive | Sparse search not configured OR RRF k too high | Compare dense vs sparse result overlap | Enable sparse vectors in Qdrant; tune RRF k (try 20–100) |
| Date filter removes all results | Query date too old OR `effective_date` fields missing | Check chunk `effective_date` values | Ensure all chunks have valid dates; adjust default query date |
| Hybrid search returns same as dense-only | Sparse vectors identical to dense OR BM25 not working | Inspect sparse result diversity | Verify sparse indexing was done; check BM25 tokenization |
| Cross-encoder produces NaN scores | Input contains non-tokenized tokens OR model mismatch | Run single pair through reranker manually | Ensure tokenizer matches model; check input text encoding |
| Memory OOM during rerank | Batch size too large for model | Monitor RAM during rerank | Reduce batch size; use CPU offloading; use smaller model |
| RRF fusion order seems wrong | Rank calculation error (0-based vs 1-based) | Compute RRF manually for small example | Use 1-based ranks; verify `1/(k+rank)` formula |

## Best Practices

- **Baseline first** — ensure Naive RAG meets quality thresholds before implementing Advanced RAG.
- **Tune RRF k** — experiment with 20, 60, 100; validate on golden QA.
- **Cache rerank results** — for repeated queries, cache reranked chunk IDs to avoid recomputation.
- **Monitor latency** — track added ms for each stage; alert if rerank exceeds budget.
- **Log fusion decisions** — record how many chunks from dense vs sparse survived to rerank; helps diagnose issues.
- **Version reranker model** — record model name and revision in `metadata` for reproducibility.
- **Time filter by default** — always apply date filter unless query explicitly requests historical view.

## Changelog

### Version 0.1 (2026-05-21)

- Created initial Advanced RAG documentation.
- Defined hybrid retrieval (dense + sparse), RRF fusion, cross-encoder reranking, and time-aware filtering.
- Specified pipeline architecture with 8 stages from query embedding to LLM generation.
- Provided request/response schemas with advanced retrieval metadata.
- Documented testing strategy (unit, integration, A/B) and troubleshooting.
- Marked as Future extension; not yet implemented.

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
| `docs/embedding_indexing.md` | Future extension | Embedding model and Qdrant indexing |
| `docs/naive_rag.md` | Future extension | Baseline RAG implementation |
| `docs/advanced_rag.md` | Future extension | Hybrid retrieval, reranking, time-aware filtering |
| `docs/graphrag_agents.md` | Future extension | Legal graph schema, traversal, agent orchestration |
| `docs/evaluation.md` | Future extension | Evaluation metrics, golden QA dataset, CI gates |
| `docs/api_deployment.md` | Future extension | FastAPI endpoints, Docker deployment, security |
| `docs/mlops_maintenance.md` | Future extension | Corpus updates, index refresh, monitoring, runbooks |
