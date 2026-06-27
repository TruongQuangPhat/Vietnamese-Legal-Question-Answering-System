# Strict Generation Comparison

| System | Split | Decision accuracy | Answer rate | Safe fallback rate | Group coverage | Pass rate | Citation validity | Retrieval errors | Generation errors |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `generation_baseline` | `all` | 0.430 | 0.391 | 0.667 | 0.357 | 0.375 | 1.000 | 0 | 0 |
| `generation_baseline` | `development` | 0.529 | 0.500 | 0.647 | 0.452 | 0.459 | 1.000 | 0 | 0 |
| `generation_baseline` | `held_out_test` | 0.233 | 0.214 | 1.000 | 0.202 | 0.209 | 1.000 | 0 | 0 |
| `strict_generation_evaluation` | `all` | 0.734 | 0.855 | 0.111 | 0.786 | 0.617 | 1.000 | 0 | 0 |
| `strict_generation_evaluation` | `development` | 0.694 | 0.868 | 0.118 | 0.790 | 0.565 | 1.000 | 0 | 0 |
| `strict_generation_evaluation` | `held_out_test` | 0.814 | 0.833 | 0.000 | 0.780 | 0.721 | 1.000 | 0 | 0 |

## Key Questions

- `decision_accuracy_improved`: True
- `answer_allowed_answer_rate_improved`: True
- `fallback_required_fallback_rate_remained_safe`: False
- `selected_evidence_group_coverage_improved`: True
- `case_pass_rate_improved`: True
- `citation_validity_remained_strict`: True
- `retrieval_error_count_acceptable`: True
- `generation_error_count_acceptable`: True
