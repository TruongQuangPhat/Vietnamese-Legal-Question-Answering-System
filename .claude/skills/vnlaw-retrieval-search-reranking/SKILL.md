---
name: vnlaw-retrieval-search-reranking
description: Use for retrieval/search internals: Qdrant hybrid search, dense/sparse retrieval, metadata filters, RRF, reranker, confidence thresholds, and retrieval metrics.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# Retrieval, Search, and Reranking Skill

Use this skill for retrieval implementation details.

This skill focuses on search internals. For full Advanced RAG orchestration, also use `vnlaw-advanced-rag`.

## Goal

Retrieve legally relevant, citation-ready evidence with metadata and confidence signals.

```text
query preprocessing
  → optional intent/date extraction
  → dense search
  → sparse search
  → metadata filtering
  → RRF fusion
  → reranking
  → confidence scoring
  → evidence selection
```

## Expected Files

```text
src/retrieval/vector_store.py
src/retrieval/reranker.py
src/retrieval/filters.py
src/retrieval/confidence.py
configs/retrieval.yml
tests/unit/retrieval/
```

## Dense Search

Use dense search for semantic meaning:

```text
"What benefits does an employee receive when leaving a job?"
```

Dense retrieval should use child `content`, not only parent article text.

## Sparse Search

Use sparse/BM25-style search for exact legal references:

```text
"Điều 46 Bộ luật Lao động"
"Khoản 1 Điều 17 Luật Đất đai"
```

Sparse search must preserve exact legal terms, article numbers, clause numbers, and law names.

## RRF Fusion

Use Reciprocal Rank Fusion to combine dense and sparse rankings without early weight tuning.

Default candidate flow:

```text
dense top 40 + sparse top 40 → RRF top 20 → reranker top 5
```

## Filters

Support metadata filters for:

```text
law_id
domain_tags
status
effective_date
expiry_date
law tier
document type
```

Time-aware filtering must use query date when available.

## Reranker

Use a cross-encoder reranker to score query-document pairs.

Attach to each candidate:

```text
retrieval_score
rerank_score
above_threshold
source_rank
retrieval_method
```

## Confidence Handling

If top evidence is below threshold:

```text
do not generate unsupported answer
return fallback
optionally suggest checking official source
```

## OOP and Docstring Rules

Expected components:

```text
DenseRetriever
SparseRetriever
HybridRetriever
RRFFusion
LegalReranker
MetadataFilterBuilder
ConfidenceScorer
```

Rules:

- Keep vector store access separate from retrieval orchestration.
- Use typed retrieval candidate models.
- Preserve hierarchy and source URL in every candidate.
- Public classes/functions must have Google-style docstrings.
- Docstrings must explain score semantics and filtering assumptions.

## Retrieval Tests

Add tests for:

- exact Article queries;
- semantic queries;
- no-result queries;
- expired law filtering;
- duplicate fusion;
- reranking order;
- metadata preservation;
- confidence fallback trigger.

## Do Not

- Do not remove exact-match capability.
- Do not return candidates without legal hierarchy.
- Do not ignore effective-date filters.
- Do not pass raw Qdrant payloads directly into generation.
- Do not treat rerank score as legal truth without citation validation.