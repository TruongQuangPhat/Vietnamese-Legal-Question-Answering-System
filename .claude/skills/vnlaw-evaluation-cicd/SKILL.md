---
name: vnlaw-evaluation-cicd
description: Use for RAGAS evaluation, golden QA datasets, parser/retrieval/generation tests, legal citation metrics, CI/CD quality gates, Docker build checks, and release readiness.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# Evaluation and CI/CD Skill

Use this skill to evaluate system quality and enforce merge/release gates (Phase 12+).

## Goal

Ensure the system is not only functional, but legally grounded, testable, reproducible, and safe to release.

## Test Categories

```text
unit tests       → parser, chunker, normalizer, services
integration     → ingestion pipeline, API flow
evaluation      → RAGAS, golden QA, citation checks, hallucination checks
security        → secret scan, unsafe logs, injection risks
release         → Docker build, config validation, deployment readiness
```

## RAGAS Metrics

Target gates:

```text
context_precision >= 0.85
faithfulness >= 0.80
answer_relevancy    tracked
context_recall      tracked
```

RAGAS is useful but not sufficient for legal QA. Track legal-specific metrics separately.

## Legal QA Metrics

Track:

```text
citation_exact_match
article_recall
clause_recall
point_recall
effective_date_correctness
unsupported_claim_rate
fallback_precision
fallback_recall
```

Citation validation failures should block release candidates.

## Golden Dataset Format

```json
{
  "question": "Vietnamese legal question",
  "ground_truth": "Grounded answer with citation",
  "contexts": ["Relevant law text"],
  "reference_articles": ["LDD_VBHN/Dieu17"],
  "query_date": "2025-01-01",
  "domain": "land"
}
```

Golden datasets must include:

- exact article lookup questions;
- semantic questions;
- date-sensitive questions;
- insufficient-evidence questions;
- cross-reference questions (when GraphRAG is enabled).

## CI Gates

Block merge when:

- unit tests fail;
- ruff fails;
- mypy fails;
- parser schema validation fails;
- RAGAS context precision is below threshold;
- RAGAS faithfulness is below threshold;
- citation validation fails;
- Docker build fails;
- secret scan finds real secrets.

## Commands

```bash
# Full test suite
uv run pytest tests/unit -v

# Linting
uv run ruff check src tests
uv run ruff format src tests

# Type checking
uv run mypy src

# Integration tests
uv run pytest tests/integration -v

# Evaluation
uv run python tests/evaluation/run_ragas.py \
  --dataset data/eval/golden_qa_v1.jsonl \
  --api-url http://localhost:8000
```

## OOP and Docstring Rules

Expected components:

```text
EvaluationRunner        # orchestrates evaluation runs
RagasEvaluator          # RAGAS metric computation
CitationEvaluator       # legal citation accuracy metrics
GoldenDatasetLoader     # loads golden QA datasets
RegressionReport        # test result aggregation
```

Rules:

- Keep metric computation separate from API calls.
- Evaluation scripts must be reproducible.
- Public evaluation utilities must have Google-style docstrings.
- Evaluation reports must clearly state dataset version and metric thresholds.

## Evaluation Checklist

- [ ] Parser tests cover multiple law structures.
- [ ] Chunk schema validation passes.
- [ ] Retrieval returns correct metadata.
- [ ] Low-confidence fallback works.
- [ ] Legal answers include citations.
- [ ] Citation validator passes.
- [ ] RAGAS gates pass.
- [ ] API endpoint returns request_id.
- [ ] No secret appears in logs or reports.

## Do Not

- Do not rely only on manual QA.
- Do not treat RAGAS as the only legal correctness metric.
- Do not update golden answers casually without review.
- Do not bypass CI gates to merge.
- Do not report aggregate scores without dataset version.
