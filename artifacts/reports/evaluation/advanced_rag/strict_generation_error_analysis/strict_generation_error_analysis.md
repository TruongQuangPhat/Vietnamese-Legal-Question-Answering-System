# Strict Generation Error Analysis

## Scope

- Source workflow: `strict_generation_evaluation`.
- Retrieval strategy: `coverage_aware_quota`.
- Development split is analyzed first.
- Held-out test is reporting-only and must not drive tuning.

## Why many cases failed

Most failures should be read through development split buckets first: 41 answer-allowed cases fell back, 10 cases had incomplete required evidence coverage, 51 cases had no selected evidence, 0 cases fell back through citation guard behavior, 0 cases had retrieval errors, and 0 cases had provider/generation errors.

## Key counts

- Development answer_allowed fallback cases: 41.
- All answer_allowed fallback cases: 63.
- Development fallback_required answered cases: 7.
- All fallback_required answered cases: 8.

## Weakest domains

- `land_real_estate_construction_environment`: fail_rate=0.857, missing_required_evidence_rate=0.857, cases=14.
- `traffic_public_order_sanctions`: fail_rate=0.692, missing_required_evidence_rate=0.846, cases=13.
- `criminal_procedure_penalty`: fail_rate=0.667, missing_required_evidence_rate=0.556, cases=9.
- `business_banking_tax`: fail_rate=0.571, missing_required_evidence_rate=0.500, cases=14.
- `civil_procedure_dispute_resolution`: fail_rate=0.545, missing_required_evidence_rate=0.636, cases=11.

## Weakest question types

- `eligibility`: fail_rate=0.688, missing_required_evidence_rate=0.750, cases=16.
- `clause_point_lookup`: fail_rate=0.630, missing_required_evidence_rate=0.750, cases=100.
- `sanction_or_penalty`: fail_rate=0.600, missing_required_evidence_rate=0.600, cases=15.
- `single_article_lookup`: fail_rate=0.594, missing_required_evidence_rate=0.594, cases=64.
- `procedure`: fail_rate=0.583, missing_required_evidence_rate=0.500, cases=36.

## Main bottleneck

- Primary bottleneck: `evidence_selection`.
- Signals: `{"evidence_selection": 110, "fallback_policy": 48, "generation": 0, "retrieval": 61}`.

## Recommended next actions

- Review evidence selection warnings for parent-context-only and caution-only decisions.
- Tighten citation-safe child evidence selection without making parent context directly citable.
- Use development split diagnostics for fixes; keep held_out_test reporting-only.
- Do not change benchmark labels, qrels, legal chunks, retrieval artifacts, or generated results.
