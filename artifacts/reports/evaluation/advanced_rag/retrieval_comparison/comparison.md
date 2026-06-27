# Advanced Retrieval Comparison

| System | Split | Recall@10 | MRR@10 | NDCG@10 | evidence_group_coverage@10 |
| --- | --- | ---: | ---: | ---: | ---: |
| `dense_bge_m3_baseline` | `all` | 0.845 | 0.657 | 0.610 | 0.569 |
| `dense_bge_m3_baseline` | `development` | 0.794 | 0.583 | 0.524 | 0.504 |
| `dense_bge_m3_baseline` | `held_out_test` | 0.929 | 0.777 | 0.779 | 0.705 |
| `sparse_bm25_baseline` | `all` | 0.864 | 0.648 | 0.602 | 0.745 |
| `sparse_bm25_baseline` | `development` | 0.926 | 0.660 | 0.598 | 0.772 |
| `sparse_bm25_baseline` | `held_out_test` | 0.762 | 0.629 | 0.610 | 0.689 |
| `fixed_rrf_hybrid` | `all` | 0.873 | 0.687 | 0.625 | 0.622 |
| `fixed_rrf_hybrid` | `development` | 0.897 | 0.699 | 0.607 | 0.614 |
| `fixed_rrf_hybrid` | `held_out_test` | 0.833 | 0.666 | 0.660 | 0.639 |
| `coverage_aware_quota` | `all` | 0.955 | 0.688 | 0.647 | 0.771 |
| `coverage_aware_quota` | `development` | 0.956 | 0.692 | 0.617 | 0.748 |
| `coverage_aware_quota` | `held_out_test` | 0.952 | 0.683 | 0.704 | 0.820 |

## Key Questions

- `coverage_aware_improves_development_group_coverage_over_fixed_rrf`: True
- `coverage_aware_recovers_sparse_development_group_coverage`: False
- `coverage_aware_preserves_fixed_rrf_all_recall`: True
- `coverage_aware_preserves_dense_held_out_recall`: True

## Deltas

### coverage_aware_vs_dense
- `all`: Recall@10 delta=+0.109; group coverage delta=+0.202.
- `development`: Recall@10 delta=+0.162; group coverage delta=+0.244.
- `held_out_test`: Recall@10 delta=+0.024; group coverage delta=+0.115.

### coverage_aware_vs_sparse
- `all`: Recall@10 delta=+0.091; group coverage delta=+0.027.
- `development`: Recall@10 delta=+0.029; group coverage delta=-0.024.
- `held_out_test`: Recall@10 delta=+0.190; group coverage delta=+0.131.

### coverage_aware_vs_fixed_rrf
- `all`: Recall@10 delta=+0.082; group coverage delta=+0.149.
- `development`: Recall@10 delta=+0.059; group coverage delta=+0.134.
- `held_out_test`: Recall@10 delta=+0.119; group coverage delta=+0.180.

## Interpretation

Coverage-aware quota retrieval is selected on development evidence-group coverage only; held_out_test is reported once after selection.

## Recommendation

Use reranking ablation if retrieval coverage remains insufficient; consider gate/selection ablations only as separate safety-scoped work.
