---
name: vnlaw-advanced-rag
description: Use when implementing Advanced RAG features such as hybrid dense+sparse retrieval, RRF, reranking, time-aware filtering, query decomposition, context packing, confidence scoring, and citation validation.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# Advanced RAG Skill

Use this skill only after a working Naive RAG baseline exists.

## Goal

Improve retrieval quality, answer faithfulness, and legal citation reliability.

```text
query
  → query analysis
  → intent/date/legal-reference extraction
  → dense retrieval + sparse retrieval
  → RRF fusion
  → time-aware filtering
  → reranking
  → context packing
  → answer generation
  → citation validation
  → confidence/fallback decision
```

## Required Techniques

- Dense semantic retrieval.
- Sparse lexical/BM25 retrieval.
- Reciprocal Rank Fusion.
- Cross-encoder reranking.
- Time-aware legal filtering.
- Legal context packing.
- Confidence scoring.
- Strict citation validation.
- Fallback when evidence is insufficient.

## Retrieval Strategy

Use dense retrieval for semantic questions:

```text
"What are maternity rights?"
```

Use sparse retrieval for exact legal references:

```text
"Điều 141 Bộ luật Hình sự"
```

Use hybrid retrieval for most production queries.

Default pattern:

```text
dense top 40 + sparse top 40 → RRF top 20 → reranker → top 5 evidence packets
```

## Time-Aware Filtering

If the query includes a date, retrieve the law version effective at that date.

If no query date exists, use the current configured system date.

Never mix expired and active versions without explaining legal validity.

## Context Packing

Each evidence packet must include:

```text
law_id
law_name
version/VBHN
effective_date
expiry_date
hierarchy
relevant child excerpt
parent article content
source_url
retrieval_score
rerank_score
```

Prefer concise, citation-ready packets over large unstructured context.

## Citation Validation

After generation, validate that every legal claim cites evidence that actually appears in the retrieved context.

Reject or regenerate answers when:

- citation references a missing article;
- citation references a missing clause/point;
- answer contains unsupported legal claims;
- top evidence is below confidence threshold.

## Quality Gates

Target metrics:

- RAGAS context precision ≥ 85%.
- Faithfulness ≥ 80%.
- Citation exact match should be tracked separately.
- Hybrid search latency ≤ 500ms p95 under dev assumptions.
- QA API response ≤ 10s under dev assumptions.

## OOP and Docstring Rules

Expected components:

```text
HybridRetriever
DenseRetriever
SparseRetriever
RRFFusion
LegalReranker
TimeAwareFilter
ContextPacker
CitationValidator
ConfidenceScorer
```

Rules:

- Use typed interfaces or protocols for retrievers and rerankers.
- Do not pass raw untyped dictionaries across module boundaries.
- Public classes/functions must use Google-style docstrings.
- Keep retrieval, reranking, generation, and validation separate.

## Do Not

- Do not increase context size blindly.
- Do not remove exact-match capability.
- Do not return documents without legal hierarchy.
- Do not ignore effective dates.
- Do not answer when reranked evidence is below threshold.
- Do not let the LLM invent citations.