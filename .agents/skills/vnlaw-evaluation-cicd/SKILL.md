---
name: vnlaw-evaluation-cicd
description: Use for benchmark evaluation, retrieval/generation metrics, citation/fallback checks, unit and integration test gates, CI/CD quality checks, artifact contracts, and release readiness for VnLaw-QA.
---

# Evaluation and CI/CD Skill

Use this skill to evaluate system quality and enforce safe merge/release gates.

## Current Status

Evaluation and testing are implemented across corpus processing, retrieval, and generation workflows.

Current evaluation state:

```text
benchmark = v0.1.0
total queries = 128
development split = 85
held-out test split = 43
answer_allowed = 110
fallback_required = 18
held-out test = reporting-only
```

Current workflow-level integration tests exist under:

```text
tests/integration/corpus/
tests/integration/retrieval/
tests/integration/evaluation/
```

The current final evaluated workflow uses:

```text
coverage-aware hybrid retrieval
  → evidence selection
  → strict legal generation
  → citation ID guard
  → answerability fallback guard
```

Reranking was evaluated but not adopted. RAGAS, API evaluation, Docker release gates, and production deployment checks are optional or separately scoped unless explicitly requested.

## Goal

Ensure the system is functional, legally grounded, testable, reproducible, and safe to evolve.

Evaluation should verify:

* corpus and processed chunk contracts;
* retrieval quality;
* selected evidence coverage;
* citation validity;
* fallback behavior;
* generation decision accuracy;
* artifact schema stability;
* test and lint health.

## Test Categories

```text
unit tests       → parser, chunker, normalizer, embedder, retrieval, generation, evaluation
integration     → corpus workflows, retrieval workflows, evaluation workflows
evaluation      → benchmark metrics, citation checks, fallback checks, evidence coverage
artifact checks  → report/manifest/schema contract validation
security        → secret scan, unsafe logs, sensitive output review
release         → config validation, reproducibility, optional Docker/API checks
```

Do not require real Qdrant, real LLMs, real embedding models, or full benchmark runs in routine unit/integration tests.

## Relevant Files

```text
tests/unit/
tests/integration/
tests/unit/evaluation/
tests/integration/evaluation/

src/evaluation/
scripts/evaluation/

data/eval/
artifacts/reports/evaluation/
```

Optional or future-scoped files may include:

```text
.github/workflows/ci.yml
.github/workflows/eval.yml
.github/workflows/build.yml
scripts/run_ragas_evaluation.py
data/eval/golden_qa_v1.jsonl
tests/integration/api/
```

Do not create CI, API, Docker, or RAGAS workflows unless explicitly scoped.

## Core Retrieval Metrics

Track retrieval quality with:

```text
Recall@10
MRR@10
NDCG@10
evidence_group_coverage@10
retrieval_error_count
```

Current final adopted retrieval is `coverage_aware_quota`.

Do not describe reranking as part of the final pipeline. Reranking is only for controlled ablations unless a new task explicitly scopes it.

## Core Strict Generation Metrics

Track generation and safety behavior with:

```text
decision_accuracy
answer_allowed_answer_rate
fallback_required_fallback_rate
selected_evidence_group_coverage
case_pass_rate
case_partial_rate
case_fail_rate
citation_id_validity_rate
retrieval_error_count
generation_error_count
```

Citation ID validity is required, but it is not a substitute for qualified human legal review.

## Current Final Result Snapshot

Current final strict generation result on all 128 benchmark queries:

```text
decision_accuracy = 0.875
answer_allowed_answer_rate = 0.8545454545
fallback_required_fallback_rate = 1.0
selected_evidence_group_coverage = 0.7861616162
case_pass_rate = 0.7578125
citation_id_validity_rate = 1.0
retrieval_error_count = 0
generation_error_count = 0
```

Use detailed reports in `docs/advanced_rag.md`, `docs/evaluation.md`, and official evaluation artifacts for full context.

## Legal QA Metrics

Track legal-specific behavior:

```text
citation_id_validity_rate
article_or_evidence_recall
selected_evidence_group_coverage
unsupported_claim_rate if available
answer_allowed_answer_rate
fallback_required_fallback_rate
case_pass_rate
case_partial_rate
case_fail_rate
```

Fallback-required failures and citation validation failures are safety-critical.

## Benchmark and Dataset Rules

Benchmark inputs, qrels, evidence groups, and official artifacts are protected.

Do not casually update:

```text
data/eval/**
artifacts/reports/evaluation/**
```

unless the user explicitly scopes that work.

Rules:

* do not tune on held-out test;
* held-out test is reporting-only;
* preserve benchmark version and query split metadata;
* report dataset version with metrics;
* do not report aggregate scores without dataset/split context;
* do not overwrite official artifacts without explicit approval.

## Optional RAGAS Usage

RAGAS may be useful for supplemental evaluation, but it is not the primary current legal QA gate.

If used, track separately:

```text
context_precision
faithfulness
answer_relevancy
context_recall
```

Do not treat RAGAS as sufficient for legal correctness. Legal citation, evidence coverage, and fallback behavior must be evaluated separately.

## CI Gates

Routine safe gates should include:

```bash
env UV_CACHE_DIR=/tmp/vnlaw-uv-cache find src scripts tests -name '*.py' -exec uv run python -m py_compile {} +

uv run pytest tests/unit -q --durations=30
uv run pytest tests/integration -q --durations=30

uv run ruff check src scripts tests
uv run ruff format --check src scripts tests

uv lock --check
git diff --check
```

Also check protected paths when relevant:

```bash
git diff --name-only -- \
  data/raw \
  data/interim \
  data/reports \
  data/processed/legal_chunks.jsonl

git diff --name-only -- artifacts/reports/evaluation
```

Expected output for protected path checks is usually empty unless the user explicitly scoped artifact/data changes.

## Real Evaluation Runs

Full retrieval or strict generation evaluation may require real Qdrant, real model inference, OpenRouter/Gemini, or existing indexed artifacts.

Do not run real evaluation pipelines unless explicitly scoped by the user.

Never expose secrets or API keys in logs, reports, prompts, or artifacts.

## OOP and Docstring Rules

Expected components may include:

```text
BenchmarkLoader
EvaluationRunner
RetrievalEvaluator
StrictGenerationEvaluator
CitationEvaluator
FallbackEvaluator
EvidenceSelectionDiagnostics
RegressionReport
ArtifactContractChecker
```

Rules:

* Keep metric computation separate from retrieval, LLM calls, and artifact writing.
* Evaluation scripts must be reproducible.
* Public evaluation utilities must have Google-style docstrings where project style requires it.
* Evaluation reports must clearly state dataset version, split, configuration, and limitations.

## Evaluation Checklist

* [ ] Unit tests pass.
* [ ] Integration tests pass.
* [ ] Ruff check passes.
* [ ] Format check passes.
* [ ] uv lock check passes.
* [ ] Processed chunk validation remains stable when scoped.
* [ ] Retrieval metrics are reported with dataset/split/config.
* [ ] Strict generation metrics are reported with dataset/split/config.
* [ ] Citation ID validation is enforced.
* [ ] Fallback-required cases are handled safely.
* [ ] Held-out test is not used for tuning.
* [ ] No secret appears in logs or reports.
* [ ] Protected paths are not modified unless explicitly scoped.

## Do Not

* Do not rely only on manual QA.
* Do not treat RAGAS as the only legal correctness metric.
* Do not tune on held-out test.
* Do not update benchmark answers, qrels, or evidence groups casually.
* Do not overwrite official evaluation artifacts without explicit scope.
* Do not report aggregate scores without dataset version and split.
* Do not run real LLM, Qdrant, embedding, reranking, or full benchmark workflows unless explicitly requested.
* Do not bypass citation validation or fallback checks.
* Do not describe API, Docker, RAGAS, GraphRAG, reranking, or time-aware filtering as adopted unless separately implemented and evaluated.
