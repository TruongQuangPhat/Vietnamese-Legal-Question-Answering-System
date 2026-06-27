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
-> sparse BM25 retrieval
-> fixed RRF fusion
-> coverage-aware quota retrieval
-> evidence selection
-> strict generation
-> citation guard
-> answerability fallback guard
-> evaluation outputs
```

Important evidence rule: the child chunk is the citable evidence unit. Parent
article context is auxiliary context only and is not directly citable.

Main source modules:

| Path | Responsibility |
| --- | --- |
| `src/ingestion/` | Corpus registry, crawling support, raw audit, cleaning, and storage utilities. |
| `src/processing/` | Legal hierarchy parsing, parent-child chunking, and processed JSONL validation. |
| `src/indexing/` | Embedding, Qdrant indexing, and index validation utilities. |
| `src/retrieval/` | Dense retrieval, evidence construction/selection, generation, citation guard, fallback behavior, and quality gates. |
| `src/evaluation/` | Frozen benchmark schemas, metrics, retrieval comparisons, strict generation evaluation, and offline diagnostics. |
| `src/services/` | Existing orchestration services where a service boundary is already used. |
| `scripts/` | Thin CLI wrappers for corpus, indexing, retrieval, and evaluation workflows. |

API deployment, GraphRAG, fine-tuning, and time-aware filtering are not part of
the adopted evaluated pipeline.

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

Protected corpus paths should not be modified unless an official corpus rerun
is explicitly scoped:

```text
data/raw/
data/interim/
data/reports/
data/processed/legal_chunks.jsonl
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

## Common Commands

Run unit and integration tests:

```bash
uv run pytest tests/unit -q
uv run pytest tests/integration -q
```

Run style checks:

```bash
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
uv lock --check
```

Validate processed chunks:

```bash
uv run python scripts/corpus/validate_processed_jsonl.py \
  --input data/processed/legal_chunks.jsonl \
  --config configs/processing/processed_jsonl_validation.yml \
  --output /tmp/processed_jsonl_validation_report.json \
  --pretty
```

Validate the frozen benchmark:

```bash
uv run python scripts/evaluation/validate_benchmark.py \
  --queries data/eval/legal_qa_benchmark/benchmark_queries.jsonl \
  --legal-targets data/eval/legal_qa_benchmark/benchmark_targets.jsonl \
  --evidence-judgments data/eval/legal_qa_benchmark/benchmark_qrels.jsonl \
  --evidence-groups data/eval/legal_qa_benchmark/evidence_groups.jsonl \
  --review-records data/eval/legal_qa_benchmark/review_records.jsonl \
  --split-manifest data/eval/legal_qa_benchmark/split_manifest.json \
  --benchmark-manifest data/eval/legal_qa_benchmark/benchmark_manifest.json \
  --processed-chunks data/processed/legal_chunks.jsonl
```

Run the final strict generation evaluation manually only when Qdrant is
available read-only, OpenRouter credentials are configured, and the existing
benchmark/retrieval artifacts are present:

```bash
uv run --extra qdrant --extra embedding python \
  scripts/evaluation/run_strict_generation_evaluation.py \
  --coverage-retrieval-dir artifacts/reports/evaluation/advanced_rag/coverage_aware_retrieval \
  --generation-baseline-dir artifacts/reports/evaluation/naive_rag_baseline/generation \
  --output-dir artifacts/reports/evaluation/advanced_rag/strict_generation_evaluation_answerability_fallback_guard \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --device cpu \
  --provider openrouter
```

Do not run the real evaluation command for documentation or code review tasks.

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
- Citation guard validates citation IDs, not complete semantic legal
  correctness.
- Held-out test excludes high-risk sanction/criminal QA.
- Provider output may be nondeterministic.
- Time-aware filtering is not adopted yet.
- Cross-encoder reranking was evaluated but not adopted.
- API deployment is not part of the current evaluated pipeline.

## License / Acknowledgments

No repository license file is currently present. Do not assume production or
legal-advice suitability without additional legal, security, and deployment
review.
