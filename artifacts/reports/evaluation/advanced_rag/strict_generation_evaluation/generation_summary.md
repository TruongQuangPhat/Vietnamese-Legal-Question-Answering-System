# Strict Generation Evaluation

## Scope

- Retrieval strategy: `coverage_aware_quota`.
- Provider/model: `openrouter` / `google/gemini-2.5-flash`.
- Evidence gate defaults are preserved.
- Invalid or unselected citation IDs force fallback.
- Reranking is disabled.
- Held-out results are reporting-only.

## Metrics

- `all`: queries=128, decision_accuracy=0.445, answer_rate=0.427, fallback_rate=0.556, group_coverage=0.373, pass_rate=0.352, citation_validity=1.000, retrieval_errors=0, generation_errors=0
- `development`: queries=85, decision_accuracy=0.435, answer_rate=0.397, fallback_rate=0.588, group_coverage=0.324, pass_rate=0.318, citation_validity=1.000, retrieval_errors=0, generation_errors=0
- `held_out_test`: queries=43, decision_accuracy=0.465, answer_rate=0.476, fallback_rate=0.000, group_coverage=0.451, pass_rate=0.419, citation_validity=1.000, retrieval_errors=0, generation_errors=0

## Case Status

- pass: 45
- partial: 12
- fail: 71
