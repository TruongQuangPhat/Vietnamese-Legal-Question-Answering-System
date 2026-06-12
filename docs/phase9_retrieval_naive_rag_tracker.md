# Phase 9 Retrieval / Naive RAG Tracker

## Status

```text
Phase 9A — Dense Retrieval Baseline: implemented
Phase 9B — Naive RAG Answer Generation: not implemented
```

Phase 9 starts from the validated Phase 8 Qdrant collection:

```text
Collection: vnlaw_chunks_bgem3_v1_full
Vector: dense
Dimension: 1024
Distance: Cosine
Model: BAAI/bge-m3
Sparse indexing: disabled
```

## Phase 9A Implemented

- Typed retrieval contracts in `src/retrieval/models.py`.
- Safe exact-match filters in `src/retrieval/filters.py`.
- Read-only dense Qdrant retriever in `src/retrieval/dense_retriever.py`.
- Thin service orchestration in `src/services/retrieval_service.py`.
- Runtime defaults in `configs/retrieval/retrieval.yml`.
- Manual single-query CLI in `scripts/run_dense_retrieval.py`.
- Unit tests under `tests/unit/retrieval/`.

The retriever embeds the user query with the existing BGE-M3 wrapper, validates
the 1024-dimensional query vector, searches Qdrant with named vector `dense`,
requests `with_payload=True` and `with_vectors=False`, and returns typed
payload-backed legal evidence.

## Phase 9A Guardrails

- No LLM call.
- No answer generation.
- No prompt templates.
- No generated-citation validation.
- No sparse retrieval, BM25, hybrid search, RRF, or reranking.
- No FastAPI endpoint.
- No corpus mutation.
- No Qdrant mutation.
- No effective-date filtering claim.

## Manual Command

```bash
uv run --extra qdrant --extra embedding python scripts/run_dense_retrieval.py \
  --query "Quyền sử dụng đất của hộ gia đình là gì?" \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 10 \
  --device cpu \
  --output artifacts/reports/retrieval/manual_query_result.json
```

## Next Work

1. Run manual retrieval checks against local Qdrant and review result quality.
2. Add a small retrieval evaluation set before tuning thresholds.
3. Design evidence/context packing for Naive RAG generation.
4. Implement answer generation only after retrieval quality is understood.
5. Keep hybrid retrieval, RRF, and reranking for Phase 10.
