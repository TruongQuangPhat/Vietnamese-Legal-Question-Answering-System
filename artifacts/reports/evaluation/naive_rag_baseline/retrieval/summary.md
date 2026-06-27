# Frozen Dense Retrieval Baseline

## Scope

- Retrieval type: dense.
- Benchmark version is recorded in `baseline_manifest.json`.
- Qdrant collection: `vnlaw_chunks_bgem3_v1_full`.
- Embedding model: `BAAI/bge-m3`.
- Vector name: `dense`.
- Top-k: 10.
- No answer generation, LLM call, sparse retrieval, fusion, reranking, or query rewriting.
- `held_out_test` is scoped to low/medium-risk cases only.

## Headline Metrics

- `all`: queries=128, Recall@10=0.845, MRR@10=0.657, NDCG@10=0.610, required_direct_coverage@10=0.569, evidence_group_coverage@10=0.569
- `development`: queries=85, Recall@10=0.794, MRR@10=0.583, NDCG@10=0.524, required_direct_coverage@10=0.504, evidence_group_coverage@10=0.504
- `held_out_test`: queries=43, Recall@10=0.929, MRR@10=0.777, NDCG@10=0.779, required_direct_coverage@10=0.705, evidence_group_coverage@10=0.705

## Fallback Diagnostics

- `all`: fallback_cases=18, near_miss@10=0 (0.000), supporting@10=4 (0.222), direct_evidence@10=0 (0.000)
- `development`: fallback_cases=17, near_miss@10=0 (0.000), supporting@10=4 (0.235), direct_evidence@10=0 (0.000)
- `held_out_test`: fallback_cases=1, near_miss@10=0 (0.000), supporting@10=0 (0.000), direct_evidence@10=0 (0.000)

## Weakest Breakdowns

### primary_domain

- `labor_employment_social_security`: recall_at_10=0.727, answer_allowed=11, queries=14, MRR@10=0.336
- `business_banking_tax`: recall_at_10=0.750, answer_allowed=12, queries=14, MRR@10=0.688
- `land_real_estate_construction_environment`: recall_at_10=0.750, answer_allowed=12, queries=14, MRR@10=0.482
- `civil_procedure_dispute_resolution`: recall_at_10=0.818, answer_allowed=11, queries=11, MRR@10=0.601
- `traffic_public_order_sanctions`: recall_at_10=0.818, answer_allowed=11, queries=13, MRR@10=0.773

### question_types

- `complete_list`: recall_at_10=0.591, answer_allowed=22, queries=23, MRR@10=0.334
- `near_duplicate_provision`: recall_at_10=0.625, answer_allowed=8, queries=8, MRR@10=0.448
- `multi_evidence`: recall_at_10=0.654, answer_allowed=26, queries=26, MRR@10=0.350
- `sanction_or_penalty`: recall_at_10=0.700, answer_allowed=10, queries=15, MRR@10=0.392
- `eligibility`: recall_at_10=0.800, answer_allowed=15, queries=16, MRR@10=0.576
- Buckets with no `answer_allowed` cases are excluded from direct-recall ranking and covered by fallback diagnostics.


## Known Limitations

- Retrieval-only baseline; no generation behavior is measured.
- No reranking, sparse retrieval, RRF, fusion, or query rewriting.
- `held_out_test` excludes high-risk sanction/criminal QA.
- Qualified human legal review has not occurred.
