# Frozen Sparse BM25 Retrieval Baseline

## Scope

- Retrieval type: sparse BM25.
- Benchmark version is recorded in `baseline_manifest.json`.
- Chunk source: `data/processed/legal_chunks.jsonl`.
- Top-k: 10.
- No dense retrieval, Qdrant, Docker, LLM call, hybrid fusion, reranking, or generation.
- `held_out_test` is evaluated once and must not be used for tuning.

## Headline Metrics

- `all`: queries=128, Recall@10=0.864, MRR@10=0.648, NDCG@10=0.602, required_direct_coverage@10=0.745, evidence_group_coverage@10=0.745
- `development`: queries=85, Recall@10=0.926, MRR@10=0.660, NDCG@10=0.598, required_direct_coverage@10=0.772, evidence_group_coverage@10=0.772
- `held_out_test`: queries=43, Recall@10=0.762, MRR@10=0.629, NDCG@10=0.610, required_direct_coverage@10=0.689, evidence_group_coverage@10=0.689

## Comparison Against Dense Baseline

- `all`: Recall@10 delta=+0.018; evidence_group_coverage@10 delta=+0.176.
- `development`: Recall@10 delta=+0.132; evidence_group_coverage@10 delta=+0.268.
- `held_out_test`: Recall@10 delta=-0.167; evidence_group_coverage@10 delta=-0.016.

## Weakest Breakdowns

### primary_domain

- `maritime_transport`: evidence_group_coverage_at_10=0.500, Recall@10=0.500, answer_allowed=4, queries=5
- `land_real_estate_construction_environment`: evidence_group_coverage_at_10=0.524, Recall@10=0.833, answer_allowed=12, queries=14
- `labor_employment_social_security`: evidence_group_coverage_at_10=0.577, Recall@10=0.818, answer_allowed=11, queries=14
- `consumer_health_education_digital_ip`: evidence_group_coverage_at_10=0.727, Recall@10=0.786, answer_allowed=14, queries=16
- `administrative_government_interaction`: evidence_group_coverage_at_10=0.750, Recall@10=0.750, answer_allowed=8, queries=11

### question_types

- `cross_law`: evidence_group_coverage_at_10=0.400, Recall@10=1.000, answer_allowed=4, queries=4
- `definition`: evidence_group_coverage_at_10=0.591, Recall@10=0.529, answer_allowed=17, queries=17
- `multi_evidence`: evidence_group_coverage_at_10=0.673, Recall@10=0.962, answer_allowed=26, queries=26
- `rights_and_obligations`: evidence_group_coverage_at_10=0.706, Recall@10=0.892, answer_allowed=65, queries=67
- `complete_list`: evidence_group_coverage_at_10=0.714, Recall@10=0.955, answer_allowed=22, queries=23


## Known Limitations

- Sparse lexical retrieval only.
- No dense retrieval in this run.
- No hybrid fusion, reranking, query rewriting, or LLM generation.
- BM25 may miss semantic paraphrases and broad conceptual matches.
- `held_out_test` excludes high-risk sanction/criminal QA.
- Qualified human legal review has not occurred.

## Next Action

- Run fixed dense+sparse RRF retrieval as a separate controlled ablation.
