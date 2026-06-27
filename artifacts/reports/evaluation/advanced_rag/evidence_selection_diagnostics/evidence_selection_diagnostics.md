# Evidence Selection Diagnostics

## Scope

- Workflow: `evidence_selection_diagnostics`.
- Source workflow: `strict_generation_evaluation`.
- Retrieval strategy: `coverage_aware_quota`.
- Development split is used for improvement decisions.
- Held-out test is reporting-only.

## Main reason selected evidence coverage is low

Development diagnostics indicate evidence selection is the main bottleneck: 38 cases had required evidence retrieved but not selected, 50 cases fell back because of parent-context-only behavior, and 50 cases carried caution-only selection signals.

## Development counts

- Retrieved-but-not-selected required evidence cases: 38.
- Required evidence not retrieved cases: 3.
- Parent-context-only fallback cases: 50.
- Caution-only cases: 50.
- Exact target missing cases: 3.

## Retrieved vs selected matrix

- `no_required_evidence_defined`: 18
- `required_evidence_not_retrieved`: 5
- `required_evidence_retrieved_and_selected`: 47
- `required_evidence_retrieved_but_not_selected`: 58
- `selected_evidence_empty`: 73

## Weakest domains

- `traffic_public_order_sanctions`: selection_bottleneck_rate=1.000, retrieved_but_not_selected=9, selected_empty=11, cases=13.
- `land_real_estate_construction_environment`: selection_bottleneck_rate=0.857, retrieved_but_not_selected=10, selected_empty=12, cases=14.
- `labor_employment_social_security`: selection_bottleneck_rate=0.857, retrieved_but_not_selected=5, selected_empty=9, cases=14.
- `criminal_procedure_penalty`: selection_bottleneck_rate=0.667, retrieved_but_not_selected=5, selected_empty=6, cases=9.
- `civil_family_identity`: selection_bottleneck_rate=0.643, retrieved_but_not_selected=7, selected_empty=8, cases=14.

## Weakest question types

- `near_duplicate_provision`: selection_bottleneck_rate=0.875, retrieved_but_not_selected=4, selected_empty=4, cases=8.
- `complete_list`: selection_bottleneck_rate=0.826, retrieved_but_not_selected=9, selected_empty=9, cases=23.
- `sanction_or_penalty`: selection_bottleneck_rate=0.800, retrieved_but_not_selected=7, selected_empty=10, cases=15.
- `multi_evidence`: selection_bottleneck_rate=0.769, retrieved_but_not_selected=8, selected_empty=8, cases=26.
- `eligibility`: selection_bottleneck_rate=0.750, retrieved_but_not_selected=10, selected_empty=12, cases=16.

## Manual inspection priority

- Start with development cases in `top_selector_failure_cases.jsonl`.
- Prioritize cases with required evidence retrieved but not selected.
- Then inspect parent-context-only and caution-only fallback cases.

## Recommended next actions

- Inspect why retrieved child evidence is marked caution or parent-context-only.
- Prefer improving selection diagnostics before changing selection policy.
- Do not relax citation guard.
- Do not make parent context directly citable.
- Do not change benchmark labels, qrels, legal chunks, retrieval artifacts, or generated results.
- Use development split only for policy changes.
- Keep held-out test reporting-only.
