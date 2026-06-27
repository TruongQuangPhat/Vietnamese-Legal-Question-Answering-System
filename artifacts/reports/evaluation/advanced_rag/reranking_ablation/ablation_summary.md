# Reranking Ablation

- Selection split: `development`.
- Held-out test used for selection: `false`.
- Decision: `no_adoption_no_eligible_reranker`.
- Selected config: `None`.

| Config | Pool | NDCG@10 | MRR@10 | Group@10 | Recall@10 | Group@5 | Recall@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline_no_rerank` | 10 | 0.617 | 0.692 | 0.748 | 0.956 | 0.520 | 0.838 |
| `pure_reranker_pool30` | 30 | 0.562 | 0.628 | 0.551 | 0.809 | 0.465 | 0.750 |
| `mixed_reranker_70_base_30_pool30` | 30 | 0.602 | 0.685 | 0.591 | 0.882 | 0.520 | 0.779 |
| `mixed_equal_pool30` | 30 | 0.607 | 0.691 | 0.606 | 0.897 | 0.535 | 0.809 |
| `pure_reranker_pool50` | 50 | 0.553 | 0.618 | 0.543 | 0.794 | 0.457 | 0.735 |
| `mixed_reranker_70_base_30_pool50` | 50 | 0.599 | 0.674 | 0.591 | 0.882 | 0.512 | 0.765 |
| `quota_preserved_reranker_pool50` | 50 | 0.553 | 0.618 | 0.543 | 0.794 | 0.457 | 0.735 |
