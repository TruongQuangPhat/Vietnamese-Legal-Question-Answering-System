---
name: vnlaw-project-charter
description: Use when Codex needs the overall VnLaw-QA mission, product scope, trusted legal corpus, current architecture, implementation priorities, safety boundaries, or project direction.
---

# VnLaw-QA Project Charter Skill

Use this skill to orient major work in the repository.

This skill defines the mission, architecture direction, trusted corpus policy, current system state, and implementation priorities.

## Current Project Status

VnLaw-QA has progressed from corpus ingestion through evaluated legal RAG workflows.

Current implemented state:

```text id="js85dz"
corpus documents = 52
processed chunks = 40,389
embedding model = BAAI/bge-m3
Qdrant collection = vnlaw_chunks_bgem3_v1_full
dense vector name = dense
dense dimension = 1024
benchmark = v0.1.0
benchmark queries = 128
development split = 85
held-out test split = 43
```

Implemented workflows include:

```text id="bp0wk8"
registry-driven corpus ingestion
raw corpus audit
cleaning and normalization
legal hierarchy parsing
parent-child chunking
processed JSONL validation
BGE-M3 dense indexing
Naive RAG baseline
Advanced RAG retrieval evaluation
strict generation evaluation
workflow-level integration tests for corpus/retrieval/evaluation
```

Current adopted retrieval:

```text id="wdd35c"
coverage_aware_quota
dense_candidate_k = 50
sparse_candidate_k = 50
final_top_k = 10
rrf_k = 60
dense_weight = 1.0
sparse_weight = 1.5
quota = fused_best 5, sparse_quota 4, dense_quota 1
```

Current adopted strict generation workflow:

```text id="qpbe0g"
coverage-aware hybrid retrieval
  → evidence selection
  → strict legal generation
  → citation ID guard
  → answerability fallback guard
```

Reranking was evaluated but not adopted. GraphRAG, API/backend, time-aware filtering, production MLOps, and fine-tuning are future or separately scoped unless explicitly requested.

## Mission

VnLaw-QA is a Vietnamese legal question-answering and legal research support system.

The system must answer legal questions in Vietnamese with:

* strict grounding in selected legal evidence;
* traceable citations;
* preserved Article, Clause, Point, Law Name, and legal hierarchy metadata;
* fallback when evidence is insufficient, unsafe, indirect, parent-only, or missing citation metadata;
* explicit limitation that the system supports legal research and does not replace qualified legal advice.

## Target Users

```text id="n6wk2u"
citizens
small businesses
law students
paralegals
researchers
```

The system provides legal research support, not professional legal representation.

## Current Architecture

The current architecture follows this flow:

```text id="agf232"
trusted legal source
  → registry-driven crawling
  → raw artifact storage
  → raw corpus audit
  → cleaning and normalization
  → legal hierarchy parsing
  → parent-child chunking
  → processed JSONL
  → BGE-M3 dense indexing in Qdrant
  → BM25 sparse retrieval
  → RRF fusion
  → coverage-aware quota retrieval
  → evidence selection
  → strict legal generation
  → citation ID validation
  → answerability fallback
  → evaluation artifacts
```

Parent-child chunking is a core architecture decision:

```text id="qsbzhm"
child chunk = citable Article/Clause/Point evidence
parent context = auxiliary Article-level context
```

Parent context is not directly citable.

## Current Evaluation Summary

Final adopted retrieval on all benchmark queries:

```text id="4xy5w2"
Recall@10 = 0.9545454545
MRR@10 = 0.6883910534
NDCG@10 = 0.6465347419
evidence_group_coverage@10 = 0.7712765957
```

Final strict generation on all 128 benchmark queries:

```text id="jsm4wz"
decision_accuracy = 0.875
answer_allowed_answer_rate = 0.8545454545
fallback_required_fallback_rate = 1.0
selected_evidence_group_coverage = 0.7861616162
case_pass_rate = 0.7578125
citation_id_validity_rate = 1.0
retrieval_error_count = 0
generation_error_count = 0
```

Held-out test is reporting-only and must not be used for tuning.

No qualified human legal review has occurred, so results should not be presented as verified legal correctness.

## Trusted Corpus Rule

Default trusted source:

```text id="l9j26h"
https://thuvienphapluat.vn
```

Do not add other sources without explicit approval and documentation.

Prefer consolidated VBHN documents when available. If no VBHN exists, preserve original law and amendment chronology with metadata when available.

## Legal Accuracy Rules

Non-negotiable safety rules:

* no trusted source -> no confident legal answer;
* no traceable citation -> invalid legal answer or fallback;
* never fabricate laws, articles, clauses, points, penalties, procedures, dates, or citations;
* every legal claim must be grounded in selected evidence;
* parent context is auxiliary only and not directly citable;
* citation ID validity is required but is not full semantic legal faithfulness review;
* fallback when evidence is insufficient or unsafe;
* do not provide professional legal advice.

## Implementation Priorities

Use this priority order for future work:

### 1. Preserve current validated corpus and evaluated RAG behavior

```text id="k6ucmw"
protect corpus artifacts
protect benchmark/qrels/evidence groups
protect official evaluation artifacts
maintain retrieval/generation safety guards
keep integration tests passing
```

### 2. Improve documentation and developer context

```text id="9xzaum"
README
PROJECT_CONTEXT.md
AGENTS.md
docs/
skills/
```

Documentation should reflect the current implemented system without becoming a project diary or phase tracker.

### 3. Maintain and extend evaluation safely

```text id="4x0bdn"
unit tests
workflow-level integration tests
retrieval metrics
strict generation metrics
citation/fallback metrics
artifact contracts
```

Do not tune on held-out test.

### 4. Future or separately scoped work

```text id="t1jrdu"
API/backend
GraphRAG / Neo4j
time-aware legal filtering
production MLOps
fine-tuning
RAGAS supplemental evaluation
```

These should not be treated as current adopted behavior unless explicitly implemented and evaluated.

## Core Architecture Decisions

Current decisions:

* Use Qdrant collection `vnlaw_chunks_bgem3_v1_full` for dense retrieval.
* Use BGE-M3 dense vectors with named vector `dense`, dimension 1024, cosine distance.
* Use BM25 sparse retrieval outside Qdrant for lexical/legal-reference matching.
* Use RRF and coverage-aware quota retrieval as the adopted hybrid retrieval strategy.
* Use parent-child chunking with citable child evidence and auxiliary parent context.
* Use strict citation ID validation before accepting generated answers.
* Use answerability fallback guard for unsupported or fallback-required cases.
* Use Pydantic V2 for schemas and data boundaries where applicable.
* Use lightweight unit/integration tests with fakes/mocks for routine validation.

Not current adopted decisions:

* Cross-encoder reranking is not part of the final adopted pipeline.
* Time-aware filtering is not part of the current evaluated pipeline.
* Neo4j/GraphRAG is not implemented as the current retrieval workflow.
* FastAPI/API deployment is not part of the current evaluated system unless separately scoped.
* Fine-tuning is not justified before retrieval, citation, and fallback behavior remain stable across stronger evaluations.

## Protected Paths

Do not modify these unless the user explicitly scopes the operation:

```text id="2sai0m"
data/raw/**
data/interim/**
data/reports/**
data/processed/legal_chunks.jsonl
data/eval/**
artifacts/reports/evaluation/**
```

Do not run real Qdrant writes, re-embedding, re-indexing, full benchmark evaluation, real LLM/API calls, reranking inference, or production pipeline runs unless explicitly requested.

## Operational Artifact Rules

* Qdrant storage and model caches are runtime state and must not be committed.
* Checkpoints are runtime/resume artifacts, not user-facing reports by default.
* Official user-facing reports should use functional names such as `retrieval_strategy`, `run_type`, `report_type`, `collection_name`, and `evaluation_workflow`.
* Do not expose internal roadmap labels or historical phase labels in active artifact schemas.

## Planning Output

When this skill is used for planning, return:

```text id="u31nqz"
Project understanding:
Relevant workflow:
Relevant modules:
Recommended implementation path:
Risks:
Tests/evaluation required:
Files likely to change:
Protected paths to avoid:
Validation commands:
```

## Do Not

* Do not add unapproved legal sources.
* Do not ignore legal evidence sufficiency.
* Do not make parent context directly citable.
* Do not describe reranking, GraphRAG, API/backend, time-aware filtering, or fine-tuning as adopted unless explicitly implemented and evaluated.
* Do not start fine-tuning before retrieval, citation, fallback, and evaluation behavior are stable.
* Do not optimize architecture by bypassing legal accuracy and citation safety.
* Do not run real services or mutate protected artifacts unless the user explicitly scopes that work.
