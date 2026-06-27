# Frozen Coverage-Aware Hybrid Retrieval

- Selected config: `selected_coverage_aware_quota`.
- Retrieval method: `coverage_aware_quota`.
- No generation, LLM call, reranking, or fallback-gate change.

## Headline Metrics

- `all`: queries=128, Recall@10=0.955, MRR@10=0.688, NDCG@10=0.647, required_direct_coverage@10=0.771, evidence_group_coverage@10=0.771
- `development`: queries=85, Recall@10=0.956, MRR@10=0.692, NDCG@10=0.617, required_direct_coverage@10=0.748, evidence_group_coverage@10=0.748
- `held_out_test`: queries=43, Recall@10=0.952, MRR@10=0.683, NDCG@10=0.704, required_direct_coverage@10=0.820, evidence_group_coverage@10=0.820

## Weakest Breakdowns

### primary_domain

- `land_real_estate_construction_environment`: evidence_group_coverage_at_10=0.571, Recall@10=0.917, answer_allowed=12, queries=14
- `labor_employment_social_security`: evidence_group_coverage_at_10=0.577, Recall@10=0.909, answer_allowed=11, queries=14
- `civil_procedure_dispute_resolution`: evidence_group_coverage_at_10=0.636, Recall@10=1.000, answer_allowed=11, queries=11
- `administrative_government_interaction`: evidence_group_coverage_at_10=0.750, Recall@10=0.750, answer_allowed=8, queries=11
- `maritime_transport`: evidence_group_coverage_at_10=0.833, Recall@10=1.000, answer_allowed=4, queries=5

### question_types

- `complete_list`: evidence_group_coverage_at_10=0.615, Recall@10=1.000, answer_allowed=22, queries=23
- `multi_evidence`: evidence_group_coverage_at_10=0.635, Recall@10=1.000, answer_allowed=26, queries=26
- `procedure`: evidence_group_coverage_at_10=0.698, Recall@10=0.929, answer_allowed=28, queries=36
- `near_duplicate_provision`: evidence_group_coverage_at_10=0.708, Recall@10=1.000, answer_allowed=8, queries=8
- `rights_and_obligations`: evidence_group_coverage_at_10=0.752, Recall@10=0.923, answer_allowed=65, queries=67


## Known Limitations

- Retrieval-only evaluation.
- No generation or reranking.
- Development-selected config.
- Fixed ablation search space.
- Held-out test evaluated once after selection.
- Coverage-aware ranking uses metadata proxies, not gold evidence groups.
