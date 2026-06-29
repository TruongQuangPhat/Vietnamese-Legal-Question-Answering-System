# VnLaw-QA Project Context

This file is the canonical current-state summary for repository contributors
and coding assistants.

## 1. Project Goal

VnLaw-QA is a Vietnamese legal question-answering and retrieval-augmented
generation system designed around:

- trusted legal sources;
- preserved legal hierarchy;
- source traceability;
- citation integrity;
- safe fallback when evidence is insufficient;
- reproducible evaluation.

It is a legal research assistant. It is not a generic chatbot and is not a
replacement for professional legal advice.

## 2. Current Architecture

```text
Corpus registry
-> trusted-source crawling
-> raw corpus audit
-> cleaning / normalization
-> legal hierarchy parsing
-> parent-child chunking
-> processed chunk validation
-> BGE-M3 dense indexing in Qdrant
-> Qdrant dense retrieval
-> local BM25 sparse retrieval
-> fixed RRF fusion
-> coverage-aware quota retrieval
-> evidence construction and selection
-> strict generation
-> citation ID guard
-> answerability fallback guard
-> benchmark evaluation and offline diagnostics
```

Repository layout:

```text
scripts/
  corpus/       # corpus pipeline CLI entrypoints
  indexing/     # embedding/Qdrant CLI entrypoints
  retrieval/    # retrieval, Naive RAG, review, and quality-gate entrypoints
  evaluation/   # benchmark, retrieval comparison, strict generation, diagnostics

apps/
  frontend/     # Next.js Legal QA product UI

src/
  ingestion/    # registry, crawl, audit, cleaning, storage
  processing/   # hierarchy parsing, chunking, JSONL validation
  indexing/     # embedding and Qdrant indexing/validation
  retrieval/    # retrieval, fusion, evidence construction/selection, RAG pipeline behavior, citation/fallback integration where currently implemented
  generation/   # generation-specific helpers where implemented
  services/     # existing orchestration services
  evaluation/   # benchmark schemas, metrics, workflows, diagnostics, artifact contracts
  api/          # FastAPI Legal QA product API
  monitoring/   # separately scoped
  security/     # separately scoped

docker/
  backend/Dockerfile
  frontend/Dockerfile

docker-compose.yml  # backend + frontend fake-mode local stack
```

Scripts are thin wrappers. Reusable logic belongs under `src/`.

BM25 sparse retrieval is local/manual in the current final pipeline. It is not a Qdrant sparse named-vector index.

There is intentionally no `apps/backend`. The backend remains under `src/api`
and service orchestration remains under `src/services`.

## 3. Configuration Convention

`configs/` stores committed, non-secret YAML configuration. These files are
safe to commit, reviewable in Git, and define reproducible pipeline/runtime
settings such as retrieval thresholds, indexing settings, evaluation benchmark
configuration, processing validation rules, corpus registry metadata, and
provider/model defaults without secrets.

`.env` stores local runtime overrides, machine-specific values, and secrets. It
is not committed. `.env.example` documents variable names only. Use `.env` for
provider keys and tokens, local endpoints, service mode, and config selectors
such as `LEGAL_QA_RETRIEVAL_CONFIG`, `LEGAL_QA_LLM_CONFIG`, and
`LEGAL_QA_QDRANT_URL`.

Do not put provider API keys or tokens in `configs/*.yml`. Do not put large
reviewable config blocks in `.env`; `.env` should select or override runtime
values, not replace committed config files.

Current committed config inventory:

| Path | Purpose |
| --- | --- |
| `configs/evaluation/legal_qa_benchmark.yml` | Benchmark case configuration. |
| `configs/indexing/embedding_indexing.yml` | Embedding and Qdrant indexing settings. |
| `configs/laws/corpus_registry.yml` | Trusted legal corpus registry metadata. |
| `configs/llm/openrouter.yml` | Non-secret LLM provider/model defaults. |
| `configs/processing/processed_jsonl_validation.yml` | Processed JSONL validation rules. |
| `configs/retrieval/quality_gate.yml` | Retrieval quality gate settings. |
| `configs/retrieval/retrieval.yml` | Retrieval runtime defaults. |

Empty placeholder config directories are currently intentional:
`configs/generation/`, `configs/ingestion/`, and `configs/sources/`.


## 4. Legal QA Safety Invariants

- No trusted source means no confident answer.
- No traceable citation means the answer is invalid.
- Do not fabricate laws, articles, clauses, points, procedures, penalties,
  effective dates, or citations.
- Preserve hierarchy where available:
  `Phần -> Chương -> Mục -> Điều -> Khoản -> Điểm`.
- Prefer consolidated legal documents (`VBHN`) when available.
- Auxiliary parent context is not directly citable evidence.
- Generated answers may cite only selected citable child evidence IDs.
- Citation-ID validity is required, but it does not prove full semantic legal
  faithfulness.
- If evidence is insufficient, unsafe, indirect, parent-only, or missing
  required targets in strict evaluation mode, fallback is required.
- The system supports legal research, not professional legal advice.

Default trusted source:

```text
https://thuvienphapluat.vn
```

## 5. Corpus and Index State

- Legal documents: 52.
- Processed chunk file: `data/processed/legal_chunks.jsonl`.
- Processed chunks: 40,389.
- Chunking: parent-child legal chunking.
- One legal child chunk maps to one Qdrant point.
- Parent context is auxiliary context only and not directly citable.
- Legal hierarchy is preserved where available.

Dense index:

```text
embedding model: BAAI/bge-m3
vector name: dense
vector dimension: 1024
distance: cosine
Qdrant collection: vnlaw_chunks_bgem3_v1_full
point count: 40,389
```

Query embedding embeds only the query. The 40,389 corpus chunks are already
indexed; do not re-embed or re-index unless a task explicitly scopes an
official indexing rerun.

## 6. Benchmark State

Frozen benchmark:

```text
benchmark version: v0.1.0
query count: 128
development split: 85
held-out test split: 43
expected answer_allowed: 110
expected fallback_required: 18
```

The held-out test split is reporting-only and must not drive tuning. It
excludes high-risk sanction/criminal QA, and no qualified human legal review
has been completed for final generated claims.

## 7. Final Adopted Retrieval

Adopted strategy:

```text
coverage_aware_quota
```

Configuration:

```text
dense_candidate_k = 50
sparse_candidate_k = 50
final_top_k = 10
rrf_k = 60
dense_weight = 1.0
sparse_weight = 1.5
quota = fused_best 5, sparse_quota 4, dense_quota 1
```

All-split retrieval result:

| Metric | Value |
| --- | ---: |
| Recall@10 | 0.9545454545 |
| MRR@10 | 0.6883910534 |
| NDCG@10 | 0.6465347419 |
| evidence_group_coverage@10 | 0.7712765957 |

Dense BGE-M3 top-k=10 baseline:

| Metric | Value |
| --- | ---: |
| Recall@10 | 0.8454545455 |
| MRR@10 | 0.65717 |
| NDCG@10 | 0.60974 |
| evidence_group_coverage@10 | 0.56915 |

Reranking ablation:

```text
reranker_model = BAAI/bge-reranker-v2-m3
decision = no_adoption_no_eligible_reranker
adopted = false
selected_config = None
```

Reranking was evaluated but is not part of the final adopted pipeline.

## 8. Final Adopted Strict Generation Workflow

Workflow:

```text
workflow_name = strict_generation_evaluation
retrieval_strategy = coverage_aware_quota
provider/model = openrouter / google/gemini-2.5-flash
reranking_used = false
held_out_used_for_tuning = false
```

Final adopted run:

```text
strict_generation_evaluation_answerability_fallback_guard
```

All split:

| Metric | Value |
| --- | ---: |
| query_count | 128 |
| decision_accuracy | 0.875 |
| answer_allowed_answer_rate | 0.8545454545 |
| fallback_required_fallback_rate | 1.0 |
| selected_evidence_group_coverage | 0.7861616162 |
| case_pass_rate | 0.7578125 |
| case_partial_rate | 0.1171875 |
| case_fail_rate | 0.125 |
| citation_id_validity_rate | 1.0 |
| retrieval_error_count | 0 |
| generation_error_count | 0 |

Development split:

| Metric | Value |
| --- | ---: |
| query_count | 85 |
| decision_accuracy | 0.8941176471 |
| answer_allowed_answer_rate | 0.8676470588 |
| fallback_required_fallback_rate | 1.0 |
| selected_evidence_group_coverage | 0.7897058824 |
| case_pass_rate | 0.7647058824 |
| retrieval_error_count | 0 |
| generation_error_count | 0 |

Held-out test split:

| Metric | Value |
| --- | ---: |
| query_count | 43 |
| decision_accuracy | 0.8372093023 |
| answer_allowed_answer_rate | 0.8333333333 |
| fallback_required_fallback_rate | 1.0 |
| selected_evidence_group_coverage | 0.7804232804 |
| case_pass_rate | 0.7441860465 |
| retrieval_error_count | 0 |
| generation_error_count | 0 |

Rejected trial:

```text
strict_generation_evaluation_residual_answer_allowed_improvement
```

It was tried but not adopted because development improved while held-out
regressed and `generation_error_count` became `1`.

## 9. Testing State

The repository now has workflow-level integration coverage under:

```text
tests/integration/corpus/
tests/integration/retrieval/
tests/integration/evaluation/
```

These tests use tiny fixtures, fake dependencies, and `tmp_path`. They do not
call real Qdrant, real LLMs, real embedding models, real rerankers, or full
benchmark workflows.

Unit tests cover service, processing, retrieval, and evaluation modules.

## 10. Product MVP State

The Legal QA product MVP is complete for fake-mode local demo usage:

- FastAPI backend API under `src/api`;
- `GET /health`, `GET /version`, and `POST /api/v1/legal-qa/ask`;
- fake/real Legal QA service mode boundary;
- runtime settings, CORS, request safety, and safe logging;
- Next.js frontend under `apps/frontend`;
- Vietnamese ask UI with answer, citation, evidence, and metadata rendering;
- Makefile local development commands;
- backend and frontend Dockerfiles;
- `docker-compose.yml` fake-mode backend + frontend stack.

Routine local/demo workflow uses fake mode:

```text
make backend-dev
make frontend-dev
make stack-up
make stack-down
```

Backend fake-mode development must use:

```bash
LEGAL_QA_SERVICE_MODE=fake uv run python -m uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
```

Do not replace it with `uv run uvicorn`.

Frontend browser-facing API URL remains:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Do not change it to a Docker service hostname for browser-facing local fake
mode.

Fake mode does not require Qdrant, OpenRouter, embedding models, rerankers, or
legal corpus data. Real mode is manual-only and should not be used in routine
validation.

## 11. Protected Paths and Runtime Safety

Do not mutate these paths unless the user explicitly scopes an official rerun:

```text
data/raw/
data/interim/
data/reports/
data/processed/legal_chunks.jsonl
data/eval/
artifacts/reports/evaluation/
```

Unless explicitly requested:

* do not call OpenRouter/Gemini/API;
* do not run real Qdrant-backed retrieval or evaluation;
* do not write to Qdrant;
* do not recreate/delete Qdrant collections;
* do not re-embed or re-index the corpus;
* do not run real embedding inference;
* do not run reranking inference;
* do not run full benchmark or strict generation evaluation.

When real retrieval/evaluation is explicitly scoped, keep Qdrant read-only unless the task explicitly scopes indexing, payload mutation, collection recreation, or upsert behavior.

## 12. Durable Documentation

- `README.md` — professional project overview, setup, commands, and final
  results.
- `docs/advanced_rag.md` — adopted coverage-aware retrieval and strict
  generation evaluation details.
- `docs/evaluation.md` — benchmark and metrics protocol.
- `docs/embedding_indexing.md` — BGE-M3/Qdrant index contract.
- `docs/naive_rag.md` — baseline dense RAG reference.
- `docs/parent_child_chunking.md` and `docs/processed_jsonl.md` — chunk and
  processed JSONL contracts.

Historical roadmap/journal docs are not authoritative when they conflict with
this file.

## 13. Future or Separately Scoped Work

The following are not part of the current adopted evaluated pipeline unless a future task explicitly scopes, implements, and evaluates them:

* GraphRAG / Neo4j graph traversal;
* multi-agent retrieval or orchestration;
* production API/backend deployment;
* production frontend deployment;
* time-aware legal filtering;
* cross-encoder reranking as an adopted pipeline component;
* fine-tuning;
* production monitoring or MLOps infrastructure;
* new trusted legal-source architecture.

Reranking was evaluated as an ablation and was not adopted. Held-out results are reporting-only and must not be used for tuning.
