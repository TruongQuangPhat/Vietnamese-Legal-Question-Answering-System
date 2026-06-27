# Strict Generation Comparison

| System | Split | Decision accuracy | Answer rate | Safe fallback rate | Group coverage | Pass rate | Citation validity | Retrieval errors | Generation errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `generation_baseline` | `all` | 0.430 | 0.391 | 0.667 | 0.357 | 0.375 | 1.000 | 0 | 0 |
| `generation_baseline` | `development` | 0.529 | 0.500 | 0.647 | 0.452 | 0.459 | 1.000 | 0 | 0 |
| `generation_baseline` | `held_out_test` | 0.233 | 0.214 | 1.000 | 0.202 | 0.209 | 1.000 | 0 | 0 |
| `strict_generation_evaluation` | `all` | 0.445 | 0.427 | 0.556 | 0.373 | 0.352 | 1.000 | 0 | 0 |
| `strict_generation_evaluation` | `development` | 0.435 | 0.397 | 0.588 | 0.324 | 0.318 | 1.000 | 0 | 0 |
| `strict_generation_evaluation` | `held_out_test` | 0.465 | 0.476 | 0.000 | 0.451 | 0.419 | 1.000 | 0 | 0 |

## Key Questions

- `decision_accuracy_improved`: True
- `answer_allowed_answer_rate_improved`: True
- `fallback_required_fallback_rate_remained_safe`: False
- `selected_evidence_group_coverage_improved`: True
- `case_pass_rate_improved`: False
- `citation_validity_remained_strict`: True
- `retrieval_error_count_acceptable`: True
- `generation_error_count_acceptable`: True
