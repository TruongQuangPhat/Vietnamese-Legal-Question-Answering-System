# Legal QA Benchmark Pilot Annotation

This directory contains draft pilot annotation for the broader legal QA
benchmark.

It is not a held-out benchmark, is not frozen, and must not be used to claim
that any system improves over the Naive RAG baseline. The pilot has completed
source-grounded primary annotation, structured automated second-pass review,
and repository-level adjudication. This does not constitute qualified human
legal review. Qualified human legal review has not been completed.
Schema/protocol stabilization and the schema contract freeze are complete for
full benchmark construction, but split creation and benchmark freeze are still
pending. The existing five-case suite under `data/eval/` remains separate
regression data.

## Files

```text
benchmark_queries.jsonl
benchmark_targets.jsonl
benchmark_qrels.jsonl
evidence_groups.jsonl
review_records.jsonl
independent_review_report.md
stabilization_report.md
```

No `split_manifest.json` or `benchmark_manifest.json` is present. Every pilot
query is pre-split with `split=null`. Query review statuses after D2 are
18 `independent_reviewed` and 1 `adjudicated`; no query is `frozen`.

## Source and Annotation Method

The pilot was built source-first from read-only corpus files:

```text
configs/laws/corpus_registry.yml
data/processed/legal_chunks.jsonl
```

For `answer_allowed` cases, annotation followed:

```text
verified source provision
-> verified child chunks
-> legal elements
-> natural Vietnamese query
-> legal targets
-> evidence groups
-> qrels
-> query metadata
```

For `fallback_required` cases, annotation followed:

```text
explicit fallback objective
-> corpus coverage inspection
-> supporting or near-miss provisions where available
-> documented insufficiency or ambiguity
-> fallback_reason
-> natural Vietnamese query
```

Parent context was used only to understand provisions. Direct evidence uses
selected child chunks from `data/processed/legal_chunks.jsonl`.

## Coverage Summary

- Total pilot queries: 19
- Complete-evidence cases: 7
- Blocking cases: 14
- Regression-overlap bridge cases: 2
- Temporal/version-sensitive cases: 0
- Independent-reviewed queries: 18
- Adjudicated queries: 1
- Unresolved cases requiring human review for D2 resolution: 0
- Qualified human legal review completed: false

The pilot intentionally over-samples difficult cases, including complete-list,
eligibility, sanction, criminal, procedure, cross-law, and fallback-safety
boundaries. This blocking distribution is not a target quota for the full
benchmark.

### Primary Domain Counts

- `administrative_government_interaction`: 1
- `business_banking_tax`: 3
- `civil_family_identity`: 2
- `civil_procedure_dispute_resolution`: 1
- `consumer_health_education_digital_ip`: 2
- `criminal_procedure_penalty`: 2
- `labor_employment_social_security`: 4
- `land_real_estate_construction_environment`: 1
- `traffic_public_order_sanctions`: 3

### Expected Decision Counts

- `answer_allowed`: 17
- `fallback_required`: 2

### Question-Type Counts

- `ambiguous`: 1
- `clause_point_lookup`: 13
- `complete_list`: 5
- `conditions_and_exceptions`: 3
- `cross_law`: 1
- `definition`: 1
- `eligibility`: 3
- `fallback`: 2
- `lexical_mismatch`: 3
- `multi_evidence`: 3
- `near_duplicate_provision`: 1
- `paraphrase`: 10
- `procedure`: 2
- `rights_and_obligations`: 8
- `sanction_or_penalty`: 5
- `single_article_lookup`: 10

## Cases Requiring Careful Independent Review

- `pilot_0001`
- `pilot_0002`
- `pilot_0003`
- `pilot_0005`
- `pilot_0007`
- `pilot_0009`
- `pilot_0010`
- `pilot_0011`
- `pilot_0012`
- `pilot_0013`
- `pilot_0016`
- `pilot_0017`
- `pilot_0018`
- `pilot_0019`

## Regression-Overlap Bridge Cases

- `pilot_0001`: deliberate bridge to the marriage-conditions regression target;
  permanently ineligible for `held_out_test`.
- `pilot_0018`: deliberate ambiguous-leave bridge related to the annual-leave
  regression target; permanently ineligible for `held_out_test`.

No other pilot case intentionally copies a regression query. Exact official
normalized query overlap was checked through the Stage C validator. Manual
semantic-overlap review remains required because semantic overlap detection is
not fully automatic.

## Categories Not Covered

- `temporal_version_sensitive`: omitted because the processed chunk schema
  inspected during this task does not expose enough effective/expiry metadata
  to assign a defensible `as_of_date` and applicable version for pilot ground
  truth.
- Real held-out split behavior: omitted because pilot records must remain
  pre-split until independent review and adjudication are complete.
- Frozen benchmark manifests: omitted because the pilot is draft data.

## D2 Review Findings

Detailed findings are recorded in
`data/eval/legal_qa_benchmark/pilot/independent_review_report.md`.
The stabilization decision is recorded in
`data/eval/legal_qa_benchmark/pilot/stabilization_report.md`.

Summary:

- 19 cases received independent review records using
  `codex_independent_review_v1`.
- 1 material disagreement was found for `pilot_0003`.
- `pilot_0003` was adjudicated by `codex_adjudication_v1` by narrowing the
  query to ordinary overtime under Article 107 Clause 2 and removing
  `conditions_and_exceptions` from `question_types`.
- No case was rejected from the pilot.
- No unresolved case requires human review for D2 conflict resolution.
- The pilot has completed source-grounded primary annotation, structured
  automated second-pass review, and repository-level adjudication.
- This does not constitute qualified human legal review.
- Qualified human legal review has not been completed.

## Human Review Checklist

- Query clarity.
- Legal scope.
- Canonical `law_id` and hierarchy correctness.
- Direct evidence sufficiency.
- Missing conditions and exceptions.
- Evidence-group completeness.
- Fallback correctness and `fallback_reason`.
- Blocking rationale.
- Temporal applicability or justified omission.
- Regression overlap and held-out ineligibility.

## Current Status

All records are still draft pilot annotations and pre-split. Source-grounded
primary annotation, structured automated second-pass review, and the one
required repository-level adjudication are complete. The pilot remains
non-frozen and has not received qualified human legal review. Schema/protocol
stabilization and schema contract freeze are complete for full benchmark
construction. A benchmark split, benchmark freeze, baseline run, or controlled
retrieval comparison has not been performed.
