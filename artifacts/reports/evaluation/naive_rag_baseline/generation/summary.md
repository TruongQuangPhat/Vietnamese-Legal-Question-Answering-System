# Frozen Naive RAG Generation Baseline

## Scope

- Benchmark version is recorded in `baseline_manifest.json`.
- Uses frozen dense retrieval results from F1.
- LLM provider/model: `openrouter` / `google/gemini-2.5-flash`.
- Sample mode: `false`.
- No sparse retrieval, fusion, reranking, query rewriting, or Advanced RAG.
- `held_out_test` is scoped to low/medium-risk cases only.

## Headline Metrics

- `all`: queries=128, decision_accuracy=0.430, answer_rate=0.391, fallback_rate=0.667, citation_validity=1.000, group_coverage=0.357
- `development`: queries=85, decision_accuracy=0.529, answer_rate=0.500, fallback_rate=0.647, citation_validity=1.000, group_coverage=0.452
- `held_out_test`: queries=43, decision_accuracy=0.233, answer_rate=0.214, fallback_rate=1.000, citation_validity=1.000, group_coverage=0.202

## Case Status

- pass: 48
- partial: 7
- fail: 73

## Known Limitations

- Naive RAG baseline only.
- LLM outputs may be nondeterministic unless the provider enforces determinism.
- No semantic claim-level human faithfulness review is performed in this run.
- `held_out_test` excludes high-risk sanction/criminal QA.
- Qualified human legal review has not occurred.
