# Frozen Hybrid Dense+Sparse RRF Retrieval Baseline

## Scope

- Retrieval type: hybrid dense+sparse RRF.
- Benchmark version is recorded in `baseline_manifest.json`.
- Dense candidates: 50.
- Sparse candidates: 50.
- Final top-k: 10.
- RRF k: 60.
- No LLM call, generation, reranking, query rewriting, or fallback-gate change.

## Headline Metrics

- `all`: queries=128, Recall@10=0.873, MRR@10=0.687, NDCG@10=0.625, required_direct_coverage@10=0.622, evidence_group_coverage@10=0.622
- `development`: queries=85, Recall@10=0.897, MRR@10=0.699, NDCG@10=0.607, required_direct_coverage@10=0.614, evidence_group_coverage@10=0.614
- `held_out_test`: queries=43, Recall@10=0.833, MRR@10=0.666, NDCG@10=0.660, required_direct_coverage@10=0.639, evidence_group_coverage@10=0.639

## Comparison Against F1 Dense and G1 Sparse

- `all` vs dense: Recall@10 +0.027; group coverage +0.053. Vs sparse: Recall@10 +0.009; group coverage -0.122.
- `development` vs dense: Recall@10 +0.103; group coverage +0.110. Vs sparse: Recall@10 -0.029; group coverage -0.157.
- `held_out_test` vs dense: Recall@10 -0.095; group coverage -0.066. Vs sparse: Recall@10 +0.071; group coverage -0.049.

## Weakest Breakdowns

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


## Known Limitations

- Retrieval-only evaluation.
- No generation or reranking.
- Fixed RRF parameters.
- `held_out_test` evaluated once and not used for tuning.
- `held_out_test` excludes high-risk sanction/criminal QA.
- Qualified human legal review has not occurred.

## Next Action

- Run Stage H reranking ablation as a separate controlled experiment.
