# Phase 9 Retrieval / Naive RAG Tracker

## Status

```text
Phase 9A — Dense Retrieval Baseline: implemented
Phase 9A.1 — Retrieval Sanity Evaluation & Evidence Risk Audit: implemented
Phase 9A.2 — Evidence Safety and Context Assembly Rules: implemented
Phase 9A.3 — Evidence Selection and Fallback Rules: implemented
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

## Phase 9A.2 Implemented

Phase 9A.2 adds a retrieval-side evidence safety layer:

```text
src/retrieval/evidence.py
tests/unit/retrieval/test_evidence.py
```

The evidence layer converts a typed `RetrievalResult` into an `EvidenceBundle`
of ordered `EvidencePacket` objects. It preserves citation metadata,
hierarchy, source URL/domain, child text, parent Article context, metadata,
warnings, and safety issues.

Evidence packets classify citation scope:

```text
child_exact           -> child text is citable with the retrieved child citation
article_context       -> article-level chunk can cite article context
unsafe_parent_context -> parent_text is broader than the child citation
missing_citation      -> citation metadata is missing
```

Parent Article context is conservative by default. Child `text` remains the
primary citable evidence. For Clause/Point chunks, broader `parent_text` is
included only as auxiliary context and is explicitly rendered as not directly
citable under the child citation. This prevents a future generator from using
Article-level `parent_text` content while citing a sibling child chunk.

Safety levels are structural:

```text
safe    -> complete citation/source metadata and directly citable child/article text
caution -> child text is citable, but broader parent context or truncation needs care
unsafe  -> missing citation/law/source/child text or empty/repealed flags
```

`ContextAssemblyConfig` controls `max_packets`, parent inclusion,
child/parent truncation limits, parent-text deduplication, score display, and
minimum safety level. Rendered context keeps citable text adjacent to its
citation and separates auxiliary parent context under an explicit warning.

This slice still does not generate answers, create prompts, validate generated
citations, rerank, perform hybrid retrieval, or mutate Qdrant/corpus data.

## Phase 9A.3 Implemented

Phase 9A.3 adds a retrieval-side evidence gate:

```text
src/retrieval/selection.py
tests/unit/retrieval/test_selection.py
```

The selection layer consumes an `EvidenceBundle` and returns an
`EvidenceSelectionResult` with:

```text
decision: answer_allowed | fallback_required | needs_review
selected_evidence
rejected_evidence
fallback_reasons
selection warnings
rendered selected context
```

Rules are conservative:

- unsafe evidence is never selected;
- safe evidence is preferred before caution evidence;
- caution evidence can be selected only when it still has citation, law ID,
  source URL, and citable child text;
- parent Article context for child chunks remains auxiliary only and is never
  treated as directly citable under the child citation;
- selected context excludes unsafe evidence and keeps citation adjacent to
  citable child text;
- all-caution parent-context evidence defaults to fallback unless configured for
  review;
- optional evaluation-assisted mode can require selected packets to match
  expected targets from Phase 9A.1.

This means the `annual_leave_days` failure mode remains blocked in
evaluation-assisted mode: sibling Article 113 chunks do not satisfy expected
Clause 1 / Point a-b-c targets, so the result is fallback/review rather than a
clean generation-allowed decision.

This slice still does not generate legal answers, create final prompts, validate
generated citations, perform hybrid retrieval, rerank, or mutate Qdrant/corpus
data.

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

1. Review Phase 9A.1 evaluation output together with Phase 9A.2/9A.3 evidence
   safety and answerability decisions.
2. Decide operational thresholds for when `needs_review` should become fallback
   in automated settings.
3. Design future Phase 9B generation around `EvidenceSelectionResult`
   selected context only after the evidence gate behavior is accepted.
4. Delay answer generation until retrieval quality and citation risk are better
   understood.
5. Keep hybrid retrieval, RRF, and reranking for Phase 10.
