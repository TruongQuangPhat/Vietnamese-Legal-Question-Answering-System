---
name: vnlaw-advanced-rag
description: Use when maintaining or extending Advanced RAG workflows, including dense+sparse retrieval, BM25, RRF, coverage-aware quota retrieval, evidence selection, strict citation validation, fallback control, and controlled retrieval/generation evaluation.
---

# Advanced RAG Skill

Use this skill for Advanced RAG implementation, maintenance, review, and evaluation.

Current project status: Advanced RAG retrieval and strict generation evaluation are implemented. The adopted retrieval strategy is `coverage_aware_quota`. Reranking was evaluated as a controlled ablation but was not adopted. Time-aware filtering remains future or separately scoped.

## Goal

Improve retrieval coverage, answer grounding, citation reliability, and safe fallback behavior.

Final adopted workflow:

```text
query
  → dense BGE-M3 retrieval
  → sparse BM25 retrieval
  → RRF fusion
  → coverage-aware quota retrieval
  → evidence selection
  → citable child evidence preservation
  → strict legal generation
  → citation ID guard
  → answerability fallback guard
  → evaluation artifacts
```

## Adopted Techniques

* Dense semantic retrieval with BGE-M3.
* Sparse lexical retrieval with BM25.
* Reciprocal Rank Fusion.
* Coverage-aware quota retrieval.
* Evidence selection over citable child chunks.
* Auxiliary parent context for context only.
* Strict citation ID validation.
* Answerability fallback guard.
* Reproducible retrieval and generation evaluation.

## Not Adopted in Final Pipeline

* Cross-encoder reranking was evaluated but not adopted.
* Time-aware legal filtering is not part of the current adopted pipeline.
* Query decomposition and agentic planning are future or separately scoped.
* FastAPI/API deployment is not part of the evaluated Advanced RAG result unless explicitly implemented in a separate task.

## Retrieval Strategy

Use dense retrieval for semantic matching and BM25 sparse retrieval for exact legal terms, article references, and lexical queries.

Default pattern:

```text
dense candidates + sparse BM25 candidates
  → RRF
  → coverage-aware quota
  → selected citable child evidence
```

The adopted retrieval configuration is:

```text
dense_candidate_k = 50
sparse_candidate_k = 50
final_top_k = 10
rrf_k = 60
dense_weight = 1.0
sparse_weight = 1.5
quota = fused_best 5, sparse_quota 4, dense_quota 1
```

## Evidence Selection

Selected evidence should be citation-ready.

A citable child evidence packet should have:

```text
chunk_id
child text or directly citable text
law_id
source_url
citation or legal reference
legal hierarchy metadata when available
```

Parent context may be included as auxiliary context, but it must not be treated as directly citable evidence.

Fallback or needs-review behavior is required when evidence is unsafe, parent-only, missing required citation metadata, or insufficient for a grounded legal answer.

## Citation Validation

Generated answers must use only citation IDs from selected evidence.

Reject or fallback when:

* the answer cites an unknown evidence ID;
* the answer makes legal claims without citations;
* selected evidence is empty;
* evidence is parent-context-only;
* required citation/source/law metadata is missing;
* strict evaluation mode has explicit empty expected targets.

Citation ID validity is required, but it is not a full substitute for human legal semantic faithfulness review.

## Evaluation Guidance

Use Advanced RAG evaluation to compare retrieval and strict generation behavior against baselines.

Important metrics include:

```text
Recall@10
MRR@10
NDCG@10
evidence_group_coverage@10
decision_accuracy
answer_allowed_answer_rate
fallback_required_fallback_rate
citation_id_validity_rate
case_pass_rate
retrieval_error_count
generation_error_count
```

Do not tune on held-out test. Held-out results are reporting-only.

Do not overwrite official evaluation artifacts unless explicitly scoped by the user.

## Implementation Boundaries

Expected functional components may include:

```text
DenseRetriever
SparseBM25Retriever
RRF fusion
CoverageAwareQuotaRetriever
EvidenceSelector
Legal generation client
Citation guard
Fallback policy
Evaluation workflow
```

Reranker and time-aware filter components should only be used for separately scoped experiments or future work.

## Do Not

* Do not describe reranking as part of the adopted final pipeline.
* Do not claim time-aware filtering is active unless explicitly implemented and evaluated.
* Do not make parent context directly citable.
* Do not relax citation validation.
* Do not let the LLM invent laws, articles, clauses, points, dates, penalties, or citations.
* Do not use model memory as legal evidence.
* Do not tune on held-out test.
* Do not run real Qdrant, LLM, embedding, reranking, or full benchmark workflows unless explicitly scoped by the user.
