# Fusion Ablation

- Split used for selection: `development`.
- Held-out test used for selection: `false`.
- Selected config: `selected_coverage_aware_quota`.

## Selected Development Metrics

- `selected`: queries=85, Recall@10=0.956, MRR@10=0.692, NDCG@10=0.617, required_direct_coverage@10=0.748, evidence_group_coverage@10=0.748

## Variants

| Config | Mode | Group@10 | Required@10 | Recall@10 | MRR@10 | NDCG@10 | Latency ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `equal_weight_rrf` | `weighted_rrf` | 0.614 | 0.614 | 0.897 | 0.699 | 0.607 | 1972.5 |
| `sparse_weight_1_25` | `weighted_rrf` | 0.606 | 0.606 | 0.897 | 0.677 | 0.591 | 1972.5 |
| `sparse_weight_1_5` | `weighted_rrf` | 0.598 | 0.598 | 0.897 | 0.680 | 0.591 | 1972.5 |
| `sparse_weight_2` | `weighted_rrf` | 0.606 | 0.606 | 0.912 | 0.681 | 0.590 | 1972.5 |
| `dense_weight_1_25` | `weighted_rrf` | 0.591 | 0.591 | 0.868 | 0.684 | 0.595 | 1972.5 |
| `sparse_weight_1_5_pool_50_100` | `weighted_rrf` | 0.575 | 0.575 | 0.868 | 0.677 | 0.586 | 1972.5 |
| `sparse_weight_1_5_pool_100_100` | `weighted_rrf` | 0.591 | 0.591 | 0.897 | 0.682 | 0.595 | 1972.5 |
| `sparse_weight_2_pool_50_100` | `weighted_rrf` | 0.598 | 0.598 | 0.912 | 0.681 | 0.590 | 1972.5 |
| `sparse_weight_2_pool_100_100` | `weighted_rrf` | 0.606 | 0.606 | 0.926 | 0.686 | 0.595 | 1972.5 |
| `quota_fused6_sparse3_dense1` | `quota` | 0.724 | 0.724 | 0.956 | 0.689 | 0.614 | 1972.5 |
| `quota_fused5_sparse3_dense2` | `quota` | 0.701 | 0.701 | 0.956 | 0.692 | 0.610 | 1972.5 |
| `quota_fused4_sparse4_dense2` | `quota` | 0.732 | 0.732 | 0.956 | 0.695 | 0.617 | 1972.5 |
| `selected_coverage_aware_quota` | `quota` | 0.748 | 0.748 | 0.956 | 0.692 | 0.617 | 1972.5 |
| `diversity_penalty_0_001` | `diversity` | 0.591 | 0.591 | 0.882 | 0.675 | 0.582 | 1972.5 |
| `diversity_penalty_0_002` | `diversity` | 0.567 | 0.567 | 0.882 | 0.670 | 0.574 | 1972.5 |
| `diversity_penalty_0_001_distinct_detail` | `diversity` | 0.591 | 0.591 | 0.882 | 0.677 | 0.585 | 1972.5 |
