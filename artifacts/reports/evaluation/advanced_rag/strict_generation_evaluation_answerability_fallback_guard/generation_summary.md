# Strict Generation Evaluation

## Scope

- Retrieval strategy: `coverage_aware_quota`.
- Provider/model: `openrouter` / `google/gemini-2.5-flash`.
- Evidence gate defaults are preserved.
- Invalid or unselected citation IDs force fallback.
- Reranking is disabled.
- Held-out results are reporting-only.

## Metrics

- `all`: queries=128, decision_accuracy=0.875, answer_rate=0.855, fallback_rate=1.000, group_coverage=0.786, pass_rate=0.758, citation_validity=1.000, retrieval_errors=0, generation_errors=0
- `development`: queries=85, decision_accuracy=0.894, answer_rate=0.868, fallback_rate=1.000, group_coverage=0.790, pass_rate=0.765, citation_validity=1.000, retrieval_errors=0, generation_errors=0
- `held_out_test`: queries=43, decision_accuracy=0.837, answer_rate=0.833, fallback_rate=1.000, group_coverage=0.780, pass_rate=0.744, citation_validity=1.000, retrieval_errors=0, generation_errors=0

## Case Status

- pass: 97
- partial: 15
- fail: 16
