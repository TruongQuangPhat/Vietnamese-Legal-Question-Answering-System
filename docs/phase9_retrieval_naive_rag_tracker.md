# Phase 9 Retrieval / Naive RAG Tracker

## Status

```text
Phase 9A — Dense Retrieval Baseline: implemented
Phase 9A.1 — Retrieval Sanity Evaluation & Evidence Risk Audit: implemented
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

## Phase 9A.1 Implemented

Live smoke tests against the real Qdrant collection passed technically:

```text
query_vector_dimension = 1024
result_count = requested top_k
issues = []
metadata/citation/source fields are preserved
```

The same smoke tests exposed dense-only quality limitations:

- annual leave queries can retrieve the correct Article 113 parent context while
  ranking sibling child provisions ahead of the expected Clause 1 evidence;
- marriage-condition queries can retrieve related marriage provisions before
  Article 8;
- parent Article context can contain answer-like text while the retrieved child
  chunk citation points to a different Clause/Point.

Phase 9A.1 adds a small read-only evaluation/audit layer:

```text
data/eval/manual_retrieval_queries.jsonl
src/retrieval/evaluation.py
scripts/evaluate_dense_retrieval.py
tests/unit/retrieval/test_evaluation.py
```

The evaluator reports expected-target hits separately from Article-level hits,
computes recall/MRR metrics, summarizes retrieved evidence, and flags
structural citation risks. Expected targets now declare an explicit
`match_level`:

```text
article -> law_id + article_number
clause  -> law_id + article_number + clause_number
point   -> law_id + article_number + clause_number + point_label
```

Null fields below the declared `match_level` are not exact-null constraints.
For example, an Article-level expected target can be satisfied by a Clause or
Point chunk under that Article. Clause-level targets can be satisfied by child
Point chunks under the same Clause. This avoids undercounting valid child chunks
while preserving separate Article-hit and exact-depth metrics.

The JSON report exposes `article_match_rank`, `clause_match_rank`,
`point_match_rank`, `best_rank_by_match_level`, `best_exact_rank`, and
`exact_match_depth` for each query. Risk flags include the expected target,
declared match level, best ranks, top result, and lower matching result when
available. It does not modify retrieval ranking or call an LLM.

## Evaluation Command

```bash
uv run --extra qdrant --extra embedding python scripts/evaluate_dense_retrieval.py \
  --queries data/eval/manual_retrieval_queries.jsonl \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --output artifacts/reports/retrieval/dense_retrieval_eval.json
```

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

1. Run and review the Phase 9A.1 evaluation report against local Qdrant.
2. Use the risk audit to decide minimum evidence-pack safety rules.
3. Design citation-preserving evidence/context packing for Naive RAG.
4. Delay answer generation until retrieval quality and citation risk are better
   understood.
5. Keep hybrid retrieval, RRF, and reranking for Phase 10.
