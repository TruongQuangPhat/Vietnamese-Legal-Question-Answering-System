# Advanced Retrieval Comparison

## Headline Metrics

| System | Split | Recall@10 | MRR@10 | NDCG@10 | evidence_group_coverage@10 |
| --- | --- | ---: | ---: | ---: | ---: |
| `f1_dense` | `all` | 0.845 | 0.657 | 0.610 | 0.569 |
| `f1_dense` | `development` | 0.794 | 0.583 | 0.524 | 0.504 |
| `f1_dense` | `held_out_test` | 0.929 | 0.777 | 0.779 | 0.705 |
| `g1_sparse_bm25` | `all` | 0.864 | 0.648 | 0.602 | 0.745 |
| `g1_sparse_bm25` | `development` | 0.926 | 0.660 | 0.598 | 0.772 |
| `g1_sparse_bm25` | `held_out_test` | 0.762 | 0.629 | 0.610 | 0.689 |
| `g2_hybrid_rrf` | `all` | 0.873 | 0.687 | 0.625 | 0.622 |
| `g2_hybrid_rrf` | `development` | 0.897 | 0.699 | 0.607 | 0.614 |
| `g2_hybrid_rrf` | `held_out_test` | 0.833 | 0.666 | 0.660 | 0.639 |

## Key Questions

- `hybrid_improves_all_recall_over_dense_and_sparse`: True
- `hybrid_improves_all_group_coverage_over_dense_and_sparse`: False
- `hybrid_preserves_held_out_dense_recall_strength`: False
- `hybrid_keeps_sparse_development_group_coverage_gain`: False

## Deltas

### hybrid_vs_dense

- `all`: Recall@10 delta=+0.027; evidence_group_coverage@10 delta=+0.053.
- `development`: Recall@10 delta=+0.103; evidence_group_coverage@10 delta=+0.110.
- `held_out_test`: Recall@10 delta=-0.095; evidence_group_coverage@10 delta=-0.066.

### hybrid_vs_sparse

- `all`: Recall@10 delta=+0.009; evidence_group_coverage@10 delta=-0.122.
- `development`: Recall@10 delta=-0.029; evidence_group_coverage@10 delta=-0.157.
- `held_out_test`: Recall@10 delta=+0.071; evidence_group_coverage@10 delta=-0.049.

## Weakest Hybrid Breakdowns

### primary_domain

- `traffic_public_order_sanctions`: evidence_group_coverage_at_10=0.474, Recall@10=0.818, answer_allowed=11, queries=13
- `civil_procedure_dispute_resolution`: evidence_group_coverage_at_10=0.500, Recall@10=0.909, answer_allowed=11, queries=11
- `labor_employment_social_security`: evidence_group_coverage_at_10=0.500, Recall@10=0.818, answer_allowed=11, queries=14
- `land_real_estate_construction_environment`: evidence_group_coverage_at_10=0.524, Recall@10=0.833, answer_allowed=12, queries=14
- `civil_family_identity`: evidence_group_coverage_at_10=0.543, Recall@10=0.923, answer_allowed=13, queries=14

### question_types

- `complete_list`: evidence_group_coverage_at_10=0.341, Recall@10=0.773, answer_allowed=22, queries=23
- `sanction_or_penalty`: evidence_group_coverage_at_10=0.389, Recall@10=0.700, answer_allowed=10, queries=15
- `multi_evidence`: evidence_group_coverage_at_10=0.404, Recall@10=0.808, answer_allowed=26, queries=26
- `near_duplicate_provision`: evidence_group_coverage_at_10=0.417, Recall@10=0.750, answer_allowed=8, queries=8
- `conditions_and_exceptions`: evidence_group_coverage_at_10=0.586, Recall@10=1.000, answer_allowed=14, queries=19

## Interpretation

Hybrid RRF is useful for comparison, but at least one target condition was not met. Review split-level regressions before adopting it as the default candidate for Stage H.

## Recommendation

Proceed to Stage H reranking ablation if G2 hybrid preserves or improves retrieval coverage sufficiently for the chosen adoption criteria.
