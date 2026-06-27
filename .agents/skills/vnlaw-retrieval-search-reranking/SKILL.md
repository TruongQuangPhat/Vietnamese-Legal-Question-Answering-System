---
name: vnlaw-retrieval-search-reranking
description: "Use for retrieval/search internals: Qdrant dense retrieval, local BM25 sparse retrieval, metadata preservation, RRF fusion, coverage-aware quota retrieval, controlled reranking ablations, retrieval metrics, and evidence selection readiness."
---

# Retrieval, Search, and Reranking Skill

Use this skill for retrieval implementation details.

This skill focuses on search internals. For full Advanced RAG orchestration, also use `vnlaw-advanced-rag`.

## Current Status

Dense retrieval, local BM25 sparse retrieval, fixed RRF fusion, and `coverage_aware_quota` retrieval are implemented.

The final adopted retrieval workflow is:

```text
query
  → dense BGE-M3 retrieval from Qdrant
  → local BM25 sparse retrieval
  → RRF fusion
  → coverage-aware quota retrieval
  → citation-ready evidence candidates
  → evidence selection
```

Reranking was evaluated as a controlled ablation and was not adopted.

Time-aware filtering is not part of the current adopted retrieval pipeline unless separately scoped and evaluated.

## Goal

Retrieve legally relevant, citation-ready evidence with metadata required for downstream evidence selection, citation validation, and safe fallback.

```text
query
  → dense search
  → sparse BM25 search
  → RRF fusion
  → coverage-aware quota retrieval
  → metadata-preserving candidates
  → evidence selection readiness
```

## Current Adopted Retrieval Configuration

```text
retrieval_strategy = coverage_aware_quota
dense_candidate_k = 50
sparse_candidate_k = 50
final_top_k = 10
rrf_k = 60
dense_weight = 1.0
sparse_weight = 1.5
quota = fused_best 5, sparse_quota 4, dense_quota 1
```

Current dense index contract:

```text
embedding model = BAAI/bge-m3
Qdrant collection = vnlaw_chunks_bgem3_v1_full
vector name = dense
dimension = 1024
distance = cosine
```

## Relevant Components and Files

Use the repository’s current structure. Relevant files may include:

```text
src/retrieval/
configs/retrieval.yml
tests/unit/retrieval/
tests/integration/retrieval/
artifacts/reports/evaluation/advanced_rag/
```

Do not create new retrieval abstractions unless the task explicitly requires them.

## Dense Search

Use dense search for semantic matching:

```text
"Người lao động được hưởng quyền lợi gì khi nghỉ việc?"
```

Dense retrieval should embed and search citable child chunk text, not only parent article text.

Dense results must preserve payload fields needed by downstream selection and citation:

```text
chunk_id
law_id
law_name when available
citation or legal reference
source_url
text or child_text
parent_text or auxiliary parent context
legal hierarchy metadata
retrieval score/rank
```

## Sparse BM25 Search

Use local BM25-style sparse retrieval for exact legal references and lexical legal terms:

```text
"Điều 46 Bộ luật Lao động"
"Khoản 1 Điều 17 Luật Đất đai"
```

Sparse search must preserve exact legal terms, article numbers, clause numbers, point markers, and law names.

Do not describe BM25 sparse retrieval as a Qdrant sparse named vector unless a separate sparse-vector indexing task is explicitly implemented.

## RRF Fusion

Use Reciprocal Rank Fusion to combine dense and sparse rankings.

Default candidate flow:

```text
dense candidates + sparse BM25 candidates
  → RRF
  → coverage-aware quota top-k
```

Fusion must:

* deduplicate by stable chunk ID;
* preserve source ranks;
* preserve dense/sparse source metadata;
* keep legal metadata required for citation and evidence selection;
* produce deterministic ordering for equal inputs.

## Coverage-Aware Quota Retrieval

Coverage-aware quota retrieval is the adopted strategy.

It should preserve a mix of:

```text
best fused candidates
sparse candidates for exact legal reference coverage
dense candidates for semantic coverage
```

The selected candidates must remain citation-ready and must not lose hierarchy, source URL, citation, or child text metadata.

## Filters

Basic metadata filters may include:

```text
law_id
status
domain_tags if available
article_id
clause_id
point_id
```

Time-aware filters using `effective_date` / `expiry_date` are future or separately scoped. If implemented later, they must be evaluated separately and must not silently mix expired and active versions.

## Reranker

Use cross-encoder reranking only for explicitly scoped ablations.

The final adopted pipeline does not use reranking.

For controlled reranking ablations, preserve separate metadata such as:

```text
rerank_score
rerank_rank
reranker_model
reranking_used
```

Do not add rerank score requirements to the final adopted retrieval candidate contract.

## Confidence and Fallback Readiness

Retrieval should support safe downstream fallback by preserving evidence quality signals and metadata.

Fallback should be triggered downstream when:

```text
retrieval returns no useful evidence
selected evidence is empty
evidence is parent-context-only
citation/source metadata is missing
evidence is insufficient or unsafe
```

Do not generate an unsupported legal answer just because retrieval returned candidates.

## OOP and Docstring Rules

Expected components may include:

```text
DenseRetriever
SparseBM25Retriever
HybridRetriever
RRFFusion
CoverageAwareQuotaRetriever
MetadataFilterBuilder
EvidenceCandidate
```

Optional or separately scoped components:

```text
LegalReranker
TimeAwareFilter
ConfidenceScorer
```

Rules:

* Keep vector store access separate from retrieval orchestration.
* Use typed retrieval candidate models.
* Preserve hierarchy and source URL in every candidate.
* Public classes/functions must have Google-style docstrings where project style requires it.
* Docstrings must explain score semantics, source rank metadata, filtering assumptions, and citation-readiness assumptions.

## Retrieval Tests

Add or update tests for:

* exact Article/Clause/Point queries;
* semantic queries;
* no-result queries;
* duplicate fusion and deterministic ordering;
* metadata preservation;
* source-rank metadata;
* coverage-aware quota selection;
* fallback readiness when selected evidence is empty or non-citable.

Separately scoped tests may cover:

```text
reranking ablation order
time-aware filtering
expired law filtering
real Qdrant integration
```

Routine tests should use fake retrievers, fake Qdrant clients, tiny fixtures, and `tmp_path`.

Workflow-level integration tests currently exist under:

```text
tests/integration/retrieval/
```

## Do Not

* Do not remove exact-match capability.
* Do not return candidates without legal hierarchy/source metadata when that metadata is available.
* Do not pass raw Qdrant payloads directly into generation.
* Do not make parent context directly citable.
* Do not treat rerank score as legal truth.
* Do not describe reranking as part of the adopted final pipeline.
* Do not claim time-aware filtering is active unless separately implemented and evaluated.
* Do not run real Qdrant, embedding, reranking, LLM, or full benchmark workflows unless explicitly scoped by the user.
