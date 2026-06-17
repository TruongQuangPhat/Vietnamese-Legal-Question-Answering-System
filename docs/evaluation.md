# Evaluation & Quality Assurance

## Overview

The Evaluation phase establishes comprehensive quality metrics for the VnLaw-QA system. It covers parser accuracy, chunk integrity, retrieval relevance, generation faithfulness, fallback behavior, and system latency. Evaluation runs continuously in CI and on golden QA datasets to catch regressions.

This phase is designed early to ensure that all downstream components have measurable quality gates.

## Quick Start

**Intended CLI** (design phase, not yet implemented):

```bash
# Run full evaluation suite
uv run python scripts/evaluate_rag.py \
  --dataset data/eval/golden_qa.jsonl \
  --qdrant-url http://localhost:6333 \
  --collection-name vnlaw_qa_chunks \
  --output-dir data/eval/reports

# Run specific test category
uv run python scripts/evaluate_rag.py --test retrieval
uv run python scripts/evaluate_rag.py --test generation
```

**Expected outputs**:
- `data/eval/reports/retrieval_metrics.json`
- `data/eval/reports/generation_metrics.json`
- `data/eval/reports/regression_report.html`

## Architecture

```
┌──────────────────────┐
│  Golden QA Dataset   │
│  (query, answer,     │
│   citation)          │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Retrieval           │
│  Evaluation          │
│  (recall, precision) │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Citation            │
│  Evaluation          │
│  (exact match)       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Generation          │
│  Faithfulness Check  │
│  (RAGAS)             │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Fallback            │
│  Evaluation          │
│  (precision/recall)  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Latency             │
│  Measurement         │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Regression          │
│  Report              │
└──────────────────────┘
```

## Components

### 1. Golden QA Dataset

**Purpose**: Ground truth for end-to-end QA evaluation.

**Format** (`data/eval/golden_qa.jsonl`):
```json
{
  "query_id": "qa_001",
  "query": "Quyền sử dụng đất của hộ gia đình?",
  "expected_answer": "Hộ gia đình có quyền sử dụng đất để xây dựng nhà ở...",
  "expected_citation": "Luật Đất đai (VBHN 2025), Điều 98, Khoản 1",
  "expected_articles": ["LDD_VBHN__article_98"],
  "difficulty": "easy|medium|hard",
  "category": "đất đai|hôn nhân|lao động"
}
```

**Construction**:
- Sample 200–500 diverse queries covering multiple laws.
- Expert-verified answers with exact citations.
- Balanced across difficulty and categories.
- Held-out; never used in training or tuning.

### 2. Retrieval Evaluation

**Goal**: Measure how well the retriever fetches relevant chunks.

**Metrics**:
- **Article recall**: % of expected `article_ids` found in top-k retrieval.
- **Clause recall**: % of expected `clause_ids` found.
- **Citation exact match**: % where retrieved citation matches expected citation exactly.
- **Precision@k**: % of retrieved top-k that are relevant (requires relevance judgments).

**Process**:
For each golden QA:
- Run retrieval (no LLM) with query.
- Compare retrieved `chunk_id` set to `expected_articles` (expanded to clause/point if available).
- Aggregate across dataset.

**Thresholds** (target):
- Article recall > 95%
- Clause recall > 90%
- Citation exact match > 85%

### 3. Generation Faithfulness

**Goal**: Verify that generated answer is grounded in retrieved context and does not hallucinate.

**Method**: RAGAS or custom LLM judge.

**Metrics**:
- **Faithfulness**: Answer claims supported by context (score 0–1).
- **Answer relevance**: Answer addresses the question (score 0–1).
- **Unsupported claim rate**: % of answer sentences with no supporting citation in context.

**Process**:
- For each QA pair: generate answer using full pipeline (retrieval + LLM).
- Feed `(query, context, answer)` to faithfulness evaluator.
- Compute averages.

**Thresholds**:
- Faithfulness > 0.9
- Unsupported claim rate < 0.05

### 4. Fallback Evaluation

**Goal**: Measure fallback policy correctness.

**Metrics**:
- **Fallback precision**: % of fallback cases where fallback was correct (system should have declined).
- **Fallback recall**: % of cases that should have fallen back that actually did.

**Process**:
- Label golden QA as "answerable" or "unanswerable" based on whether expected answer exists in corpus.
- Run full pipeline; record whether fallback triggered.
- Compute precision/recall for fallback decisions.

**Thresholds**:
- Fallback precision > 0.95 (few false declines)
- Fallback recall > 0.90 (few false answers on unanswerable)

### 5. Latency Measurement

**Goal**: Ensure system meets SLA.

**Metrics**:
- End-to-end latency (p50, p95, p99) for QA request.
- Retrieval time (p50, p95)
- Generation time (p50, p95)

**Target**: p95 < 2 seconds for simple queries; p95 < 5 seconds for complex multi-hop.

### 6. Regression Evaluation

**Goal**: Detect quality drops when making changes.

**Process**:
- Store baseline metrics from previous version (in `data/eval/baseline/`).
- After code change, re-run evaluation.
- Compare metrics; flag if any drop > 5% (configurable threshold).
- Generate HTML report with before/after charts.

**Automation**: CI pipeline runs regression check on PRs affecting retrieval/generation code.

## Pipeline Execution Flow

1. Prepare golden QA dataset (static).
2. For each evaluation run:
   - Load dataset.
   - For each query: run full pipeline or specific component (retrieval-only, generation-only).
   - Collect metrics: retrieval scores, faithfulness scores, fallback decisions, latencies.
   - Aggregate statistics.
   - Compare to baseline if provided.
   - Write JSON reports and HTML summary.
3. (CI) Fail if any metric below threshold or regression > 5%.

## Data Models / Output Schema

### Evaluation Report (JSON)

```json
{
  "timestamp": "2025-01-01T12:00:00Z",
  "dataset": "golden_qa_v1",
  "num_queries": 300,
  "retrieval": {
    "article_recall": 0.96,
    "clause_recall": 0.92,
    "citation_exact_match": 0.88,
    "precision_at_10": 0.75
  },
  "generation": {
    "faithfulness": 0.94,
    "answer_relevance": 0.91,
    "unsupported_claim_rate": 0.03
  },
  "fallback": {
    "precision": 0.96,
    "recall": 0.92
  },
  "latency_ms": {
    "end_to_end_p50": 1250,
    "end_to_end_p95": 2100,
    "retrieval_p50": 80,
    "retrieval_p95": 120,
    "generation_p50": 1100,
    "generation_p95": 1800
  },
  "thresholds_met": true,
  "regression_check": {
    "compared_to": "v1.2.3",
    "article_recall_delta": -0.01,
    "faithfulness_delta": -0.02,
    "regression_detected": false
  }
}
```

### Golden QA Dataset Schema

See Components section above.

## CLI Reference

### Main Evaluation Command

```bash
# Full evaluation
uv run python scripts/evaluate_rag.py \
  --dataset data/eval/golden_qa.jsonl \
  --qdrant-url http://localhost:6333 \
  --collection-name vnlaw_qa_chunks \
  --output-dir data/eval/reports \
  --compare-baseline data/eval/baseline/latest.json

# Component-specific
uv run python scripts/evaluate_rag.py --test retrieval --k 5 10 20
uv run python scripts/evaluate_rag.py --test generation --judge-model provider/model-name
uv run python scripts/evaluate_rag.py --test latency --num-queries 100

# Generate regression report (CI)
uv run python scripts/evaluate_rag.py --ci-check --threshold 0.05
```

**Arguments**:
- `--dataset`: Path to golden QA JSONL.
- `--qdrant-url`, `--collection-name`: Vector store for retrieval.
- `--output-dir`: Where to write reports.
- `--compare-baseline`: Baseline JSON to compare against.
- `--test`: Run only specific test category.
- `--ci-check`: Exit non-zero if regression detected.
- `--threshold`: Regression threshold (default 0.05 = 5%).

## Testing

**Unit tests**:
- `test_retrieval_metrics()`: compute recall/precision correctly given retrieved and expected sets.
- `test_faithfulness_judge()`: sample answer/context pairs scored accurately.
- `test_latency_percentiles()`: p50/p95 computed correctly from sample.
- `test_regression_detection()`: delta > threshold flagged.

**Golden QA evaluation**:
- Run full suite nightly or on PRs to main.
- Store historical metrics to track trends.
- Alert on threshold misses or regressions.

## Error Handling

- **Missing golden QA file**: `FileNotFoundError`; abort.
- **Qdrant connection failure**: Log error, skip retrieval tests, exit with partial results.
- **LLM judge API failure**: Retry with backoff; if persistent, mark generation tests as skipped (not failed).
- **Timeout on query**: Skip that query, log warning; continue with others.
- **Malformed golden QA entry**: Skip, log error with line number.

Partial results are still written; CI should consider overall pass/fail based on completed metrics.

## Troubleshooting

| Issue | Possible Cause | How to Check | Recommended Fix |
|-------|----------------|--------------|-----------------|
| Retrieval recall much lower than baseline | Index incomplete or embedding model changed | Compare collection point count to expected chunk count | Re-index if missing; verify embedding model matches training |
| Faithfulness score low | LLM prompt weak OR context packing includes irrelevant text | Inspect low-scoring answer/context pairs | Strengthen prompt; improve context relevance (reranking) |
| Evaluation very slow | Running full LLM judge on every QA item | Check time per query | Reduce dataset size for CI; use smaller judge model; batch API calls |
| Regression false positive | Baseline from different dataset or conditions | Verify baseline run conditions match current | Ensure same golden QA, same model versions, same index |
| Fallback precision low | Threshold too low OR retrieval returning irrelevant chunks | Analyze false positives (fallback triggered but answer was possible) | Adjust confidence threshold; improve retrieval quality |
| Latency p95 high | Outliers in generation (slow LLM responses) | Inspect slowest queries | Implement timeout; consider faster model; cache frequent queries |

## Best Practices

- **Hold out golden QA** — never use for tuning or training; keep secret.
- **Run evaluation on every PR** — at least retrieval and basic generation; full suite nightly.
- **Version evaluation code** — changes to metrics require justification and baseline reset.
- **Track trends** — store historical reports; visualize metrics over time.
- **Automate CI gates** — fail if any metric below threshold or regression > 5%.
- **Keep evaluation deterministic** — fixed random seeds, same model versions, same index snapshot for fair comparison.

## Changelog

### Version 0.1 (2026-05-21)

- Created initial evaluation & QA documentation.
- Defined metrics: retrieval (article/clause recall, citation match), generation (faithfulness, unsupported claims), fallback (precision/recall), latency.
- Specified golden QA dataset format and construction guidelines.
- Outlined regression evaluation and CI integration.
- Provided evaluation report JSON schema.
- Documented testing strategy and troubleshooting.

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
| `docs/api_deployment.md` | Future extension | FastAPI endpoints, Docker deployment, security |
| `docs/mlops_maintenance.md` | Future extension | Corpus updates, index refresh, monitoring, runbooks |
