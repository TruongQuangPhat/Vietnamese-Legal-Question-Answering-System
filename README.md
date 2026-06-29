# VnLaw-QA

VnLaw-QA is a Vietnamese legal question-answering system using
Retrieval-Augmented Generation with legal hierarchy-aware corpus processing,
hybrid retrieval, strict citation validation, and conservative fallback
control. The system supports legal research; it is not a replacement for
professional legal advice.

## Highlights

- 52 trusted Vietnamese legal documents.
- 40,389 validated parent-child legal chunks.
- Dense retrieval with `BAAI/bge-m3` in Qdrant.
- Sparse BM25 retrieval and fixed RRF fusion.
- Adopted coverage-aware hybrid retrieval strategy:
  `coverage_aware_quota`.
- Strict evidence selection with citable child evidence only.
- Citation ID guard and answerability fallback guard.
- Reproducible frozen benchmark `v0.1.0` with 128 queries.
- Workflow-level integration tests for corpus, retrieval, and evaluation
  workflows using tiny fixtures and fake dependencies.

## Architecture

```text
Corpus registry
-> trusted-source crawling
-> raw corpus audit
-> cleaning and normalization
-> legal hierarchy parsing
-> parent-child chunking
-> processed JSONL validation
-> dense Qdrant indexing
-> Qdrant dense retrieval
-> local BM25 sparse retrieval
-> fixed RRF fusion
-> coverage-aware quota retrieval
-> evidence selection
-> strict generation
-> citation ID guard
-> answerability fallback guard
-> evaluation outputs
```

Important evidence rule: the child chunk is the citable evidence unit. Parent article context is auxiliary context only and is not directly citable.

BM25 sparse retrieval is local/manual in the current final pipeline. It is not a Qdrant sparse named-vector index.

Main source modules:

| Path              | Responsibility                                                                                                                                                                                                            |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/ingestion/`  | Corpus registry, crawling support, raw audit, cleaning, and storage utilities.                                                                                                                                            |
| `src/processing/` | Legal hierarchy parsing, parent-child chunking, and processed JSONL validation.                                                                                                                                           |
| `src/indexing/`   | Embedding, Qdrant indexing, and index validation utilities.                                                                                                                                                               |
| `src/retrieval/`  | Dense retrieval, local BM25 retrieval, RRF fusion, coverage-aware quota retrieval, evidence construction/selection, citation ID guard integration, fallback behavior, and RAG pipeline behavior where currently implemented. |
| `src/generation/` | Generation-specific helpers where implemented.                                                                                                                                                                            |
| `src/evaluation/` | Frozen benchmark schemas, metrics, retrieval comparisons, strict generation evaluation, evidence diagnostics, and offline diagnostics.                                                                                    |
| `src/services/`   | Existing orchestration services where a service boundary is already used.                                                                                                                                                 |
| `scripts/`        | Thin CLI wrappers for corpus, indexing, retrieval, and evaluation workflows.                                                                                                                                              |

API deployment, GraphRAG, fine-tuning, production MLOps, and time-aware filtering are not part of the adopted evaluated pipeline.


## Current Results

### Retrieval

Frozen benchmark: `v0.1.0`, 128 queries.

| System | Recall@10 | MRR@10 | NDCG@10 | evidence_group_coverage@10 |
| --- | ---: | ---: | ---: | ---: |
| Dense BGE-M3 baseline | 0.845 | 0.657 | 0.610 | 0.569 |
| Coverage-aware quota hybrid | 0.955 | 0.688 | 0.647 | 0.771 |

Adopted retrieval configuration:

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

Reranking was evaluated with `BAAI/bge-reranker-v2-m3` and was not adopted
because no eligible configuration passed the adoption thresholds.

### Strict generation

Final adopted workflow:
`strict_generation_evaluation_answerability_fallback_guard`.

Provider/model used for the final evaluation:
`openrouter` / `google/gemini-2.5-flash`.

| System | Decision accuracy | Answer-allowed answer rate | Fallback-required fallback rate | Selected evidence group coverage | Case pass rate | Citation ID validity | Retrieval errors | Generation errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `generation_baseline` | 0.430 | 0.391 | 0.667 | 0.357 | 0.375 | 1.000 | 0 | 0 |
| Final strict generation | 0.875 | 0.855 | 1.000 | 0.786 | 0.758 | 1.000 | 0 | 0 |

Split-level final metrics:

| Split | Queries | Decision accuracy | Answer rate | Safe fallback rate | Group coverage | Pass rate | Retrieval errors | Generation errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 128 | 0.875 | 0.855 | 1.000 | 0.786 | 0.758 | 0 | 0 |
| development | 85 | 0.894 | 0.868 | 1.000 | 0.790 | 0.765 | 0 | 0 |
| held_out_test | 43 | 0.837 | 0.833 | 1.000 | 0.780 | 0.744 | 0 | 0 |

The held-out split is reporting-only and was not used for tuning.

## Safety and Scope

- No trusted source means no confident legal answer.
- No traceable citation means the answer is invalid.
- Do not fabricate laws, articles, clauses, points, procedures, penalties,
  effective dates, or citations.
- Preserve hierarchy when available:
  `Phần -> Chương -> Mục -> Điều -> Khoản -> Điểm`.
- Prefer consolidated legal documents (`VBHN`) when available.
- Parent context is auxiliary only and not directly citable.
- Citation ID validity is required, but it is not full semantic legal
  faithfulness.
- If evidence is insufficient, unsafe, indirect, parent-only, or missing
  required targets in strict evaluation mode, the system must fallback.
- No qualified human legal review has been completed for final generated
  claims.

## Repository Structure

```text
VnLaw-QA/
├── configs/      # YAML configuration and benchmark config
├── data/         # raw, interim, processed, and evaluation data
├── docs/         # durable technical documentation
├── scripts/      # CLI wrappers
├── src/          # reusable implementation modules
├── tests/        # unit and integration tests
└── artifacts/    # generated reports and evaluation outputs when present
```

Protected corpus, benchmark, and official evaluation paths should not be modified unless an official rerun is explicitly scoped:

```text
data/raw/
data/interim/
data/reports/
data/processed/legal_chunks.jsonl
data/eval/
artifacts/reports/evaluation/
```

## Setup

Requirements:

- Python 3.11+
- `uv`
- Qdrant only for real retrieval/evaluation workflows
- OpenRouter credentials only for real LLM generation evaluation

Install dependencies:

```bash
uv sync
```

Optional provider secrets belong in environment variables or an uncommitted
`.env`. Do not store API keys in configs, docs, reports, or source code.

For backend runtime configuration and local smoke checks, see
`docs/backend-runtime.md`.

For frontend local development, see `apps/frontend/README.md`.

## Local Product Development

Run the fake-mode MVP with two terminals.

Backend:

```bash
make backend-dev
```

Frontend:

```bash
make frontend-dev
```

Then open:

```text
http://localhost:3000
```

Fake mode returns stub Legal QA responses for local UI and API contract checks.
It does not require Qdrant, OpenRouter, embedding models, rerankers, or
benchmark/evaluation workflows. Real mode requires separate manual setup and
should not be used in routine validation.

## Common Commands

Run focused product checks:

```bash
make test-api
make frontend-lint
make frontend-build
```

Build and run the backend container in fake mode:

```bash
make backend-image
make backend-container
```

Equivalent direct commands:

```bash
docker build -f docker/backend/Dockerfile -t vnlaw-qa-backend:local .
docker run --rm -p 8000:8000 -e LEGAL_QA_SERVICE_MODE=fake vnlaw-qa-backend:local
```

Smoke check the running container:

```bash
curl -s http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

The backend image is for fake-mode local packaging checks. It does not require
Qdrant, OpenRouter, embedding models, rerankers, or legal corpus data. Real
mode requires additional runtime setup and is not part of routine validation.

Build and run the frontend container:

```bash
make frontend-image
make frontend-container
```

Equivalent direct commands:

```bash
docker build -f docker/frontend/Dockerfile \
  -t vnlaw-qa-frontend:local \
  --build-arg NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
  .

docker run --rm -p 3000:3000 vnlaw-qa-frontend:local
```

Local container smoke:

1. Run the backend on `http://localhost:8000` with `make backend-dev` or
   `make backend-container`.
2. Run the frontend container on `http://localhost:3000`.
3. Open `http://localhost:3000`.
4. Submit a Vietnamese legal question.
5. Confirm the fake backend response renders.

`NEXT_PUBLIC_API_BASE_URL` is browser-facing and must not contain secret values.
For this local packaging flow it remains `http://localhost:8000`; Docker Compose
service-network wiring is intentionally not configured yet.

Run safe validation:

```bash
env UV_CACHE_DIR=/tmp/vnlaw-uv-cache find src scripts tests -name '*.py' -exec uv run python -m py_compile {} +

uv run pytest tests/unit -q --durations=30
uv run pytest tests/integration -q --durations=30

uv run ruff check src scripts tests
uv run ruff format --check src scripts tests

uv lock --check
git diff --check
```

Check protected paths before committing:

```bash
git diff --name-only -- \
  data/raw \
  data/interim \
  data/reports \
  data/processed/legal_chunks.jsonl \
  data/eval

git diff --name-only -- artifacts/reports/evaluation
```

Expected output is usually empty unless the task explicitly scoped corpus, benchmark, or official evaluation artifact changes.

## Evaluation

Benchmark `v0.1.0` contains:

- total queries: 128;
- development split: 85;
- held-out test split: 43;
- expected `answer_allowed`: 110;
- expected `fallback_required`: 18.

The held-out split is reporting-only, excludes high-risk sanction/criminal QA,
and has not received qualified human legal review. Results should be interpreted
as engineering evidence, not a legal-quality certification.

## Limitations

- The benchmark has only 128 queries.
- No claim-level qualified human legal review has been completed for final
  generation outputs.
- Citation ID guard validates citation IDs, not complete semantic legal
  correctness.
- Held-out test excludes high-risk sanction/criminal QA.
- Provider output may be nondeterministic.
- Time-aware filtering is not adopted yet.
- Cross-encoder reranking was evaluated but not adopted.
- API deployment is not part of the current evaluated pipeline.

## License / Acknowledgments

This project is licensed under the MIT License. See `LICENSE` for details.

This system is intended for legal research and engineering evaluation only. Do
not assume production or legal-advice suitability without additional legal,
security, and deployment review.
