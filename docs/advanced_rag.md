# Advanced RAG: Coverage-Aware Hybrid Retrieval and Strict Generation

## Overview

Advanced RAG upgrades the Naive RAG baseline with dense BGE-M3 retrieval, BM25
sparse retrieval, fixed Reciprocal Rank Fusion (RRF), coverage-aware quota
selection, strict evidence selection, citation validation, and an answerability
fallback guard.

The adopted system is still a legal research assistant. It is not legal advice,
and it must fall back when retrieved evidence is insufficient, unsafe, indirect,
or not traceable.

Important scope decisions:

- Cross-encoder reranking was evaluated but not adopted.
- Time-aware law filtering is not part of the adopted pipeline yet.
- API deployment is not part of this evaluation.

## Final Adopted Pipeline

The final evaluated pipeline is:

1. Query.
2. Dense BGE-M3 query embedding.
3. Dense Qdrant retrieval from `vnlaw_chunks_bgem3_v1_full`.
4. Sparse BM25 retrieval over the processed legal chunks.
5. Fixed RRF fusion.
6. Coverage-aware quota retrieval.
7. Evidence selection.
8. Citable child evidence preservation when auxiliary parent context is present.
9. Strict legal generation.
10. Citation ID guard.
11. Answerability fallback guard.
12. Evaluation outputs under `artifacts/reports/evaluation/advanced_rag/`.

The adopted retrieval strategy is `coverage_aware_quota`:

- benchmark version: `v0.1.0`
- query count: `128`
- dense candidate k: `50`
- sparse candidate k: `50`
- final top k: `10`
- RRF k: `60`
- dense weight: `1.0`
- sparse weight: `1.5`
- quota: fused best `5`, sparse quota `4`, dense quota `1`

## Retrieval Evaluation

Retrieval was evaluated on the frozen `v0.1.0` benchmark.

| System | Recall@10 | MRR@10 | NDCG@10 | evidence_group_coverage@10 |
| --- | ---: | ---: | ---: | ---: |
| Dense BGE-M3 baseline | 0.845 | 0.657 | 0.610 | 0.569 |
| Sparse BM25 baseline | 0.864 | 0.648 | 0.602 | 0.745 |
| Fixed RRF hybrid | 0.873 | 0.687 | 0.625 | 0.622 |
| Coverage-aware quota hybrid | 0.955 | 0.688 | 0.647 | 0.771 |

Coverage-aware quota retrieval was selected because it improved all-split
Recall@10 and evidence-group coverage while preserving a fixed, reproducible
retrieval configuration.

Split-level coverage-aware quota results:

| Split | Recall@10 | MRR@10 | NDCG@10 | evidence_group_coverage@10 |
| --- | ---: | ---: | ---: | ---: |
| all | 0.955 | 0.688 | 0.647 | 0.771 |
| development | 0.956 | 0.692 | 0.617 | 0.748 |
| held_out_test | 0.952 | 0.683 | 0.704 | 0.820 |

Held-out test metrics are reporting-only and must not be used for tuning.

## Reranking Ablation

Reranking was tested as a controlled ablation after coverage-aware retrieval.

- reranker model: `BAAI/bge-reranker-v2-m3`
- implementation note: a native Transformers wrapper was used after
  FlagEmbedding incompatibility
- selection split: `development`
- held-out test used for selection: `false`
- final decision: `no_adoption_no_eligible_reranker`
- selected config: `None`
- adopted: `false`

No reranked configuration passed the adoption thresholds. The final pipeline
does not use reranking.

## Strict Generation Evaluation

Strict generation was evaluated with:

- workflow name: `strict_generation_evaluation`
- retrieval strategy: `coverage_aware_quota`
- provider/model: `openrouter` / `google/gemini-2.5-flash`
- query count: `128`
- expected answer allowed: `110`
- expected fallback required: `18`

The final adopted generation run is
`strict_generation_evaluation_answerability_fallback_guard`.

| System | Decision accuracy | Answer rate | Safe fallback rate | Group coverage | Pass rate | Citation validity | Retrieval errors | Generation errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| generation_baseline | 0.430 | 0.391 | 0.667 | 0.357 | 0.375 | 1.000 | 0 | 0 |
| strict_generation_evaluation with answerability fallback guard | 0.875 | 0.855 | 1.000 | 0.786 | 0.758 | 1.000 | 0 | 0 |

Split-level final strict generation metrics:

| Split | Decision accuracy | Answer rate | Safe fallback rate | Group coverage | Pass rate | Retrieval errors | Generation errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 0.875 | 0.855 | 1.000 | 0.786 | 0.758 | 0 | 0 |
| development | 0.894 | 0.868 | 1.000 | 0.790 | 0.765 | 0 | 0 |
| held_out_test | 0.837 | 0.833 | 1.000 | 0.780 | 0.744 | 0 | 0 |

The residual answer evidence selection trial
`strict_generation_evaluation_residual_answer_allowed_improvement` was tried
but not adopted because development improved while held-out regressed and
`generation_error_count` became `1`.

## Safety and Legal QA Invariants

The adopted Advanced RAG pipeline preserves the project’s core legal QA
invariants:

- No trusted source means no confident legal answer.
- No traceable citation means the answer is invalid.
- Auxiliary parent context may support understanding, but it is not directly
  citable.
- Citation ID validity is required but does not prove full semantic
  faithfulness.
- Fallback is required when evidence is insufficient or when strict evaluation
  explicitly has no answerable target evidence.
- Held-out test is reporting-only.
- Qualified human legal review has not yet been completed for high-risk
  held-out expansion.

The citation guard checks that generated `[E#]` IDs map to selected evidence.
It does not by itself prove that every generated legal claim is semantically
faithful.

## Final Adopted Result

Final adopted retrieval strategy:

```text
coverage_aware_quota
```

Final adopted generation workflow:

```text
strict_generation_evaluation_answerability_fallback_guard
```

Final all-split metrics:

- decision_accuracy: `0.875`
- answer_allowed_answer_rate: `0.855`
- fallback_required_fallback_rate: `1.000`
- selected_evidence_group_coverage: `0.786`
- case_pass_rate: `0.758`
- citation_id_validity_rate: `1.000`
- retrieval_error_count: `0`
- generation_error_count: `0`

## Known Limitations

- The frozen benchmark has 128 queries only.
- There is no claim-level human semantic faithfulness review for the final
  generation output.
- Citation guard checks citation IDs, not full legal correctness.
- Held-out test excludes high-risk sanction/criminal QA that lacks qualified
  human legal review.
- Provider output may be nondeterministic.
- Time-aware filtering is not adopted yet.
- API deployment is not part of this evaluation.

## Reproduction Commands

The final strict generation evaluation requires:

- Qdrant collection `vnlaw_chunks_bgem3_v1_full` available read-only;
- OpenRouter credentials configured;
- existing benchmark, retrieval, and frozen generation baseline artifacts.

Run:

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

Do not use this command for code review or documentation-only validation. It
runs the real evaluation workflow.

## Changelog

### 2026-06-27

- Adopted coverage-aware hybrid retrieval.
- Recorded reranking as a negative ablation.
- Added strict generation evaluation with citation guard and answerability
  fallback guard.
- Final benchmark result reached `0.875` decision accuracy, `1.000` safe
  fallback rate, and `0` generation errors.
