# Pilot Stabilization Report

## Scope

This report assesses whether the Stage B protocol and Stage C implementation
were successfully exercised by the reviewed pilot.

The pilot is not a held-out benchmark. It is not frozen benchmark data. The
pilot has completed source-grounded primary annotation, structured automated
second-pass review, and repository-level adjudication. This does not
constitute qualified human legal review. Qualified human legal review has not
been completed. This report does not claim legal-expert validation and does
not claim any system improvement.

## Pilot Review Summary

- Query count: 19.
- Primary review count: 19.
- Structured independent review count: 19.
- Adjudication count: 1.
- Confirmed count: 7.
- Confirmed-with-minor-notes count: 11.
- Material-disagreement count: 1.
- Rejected count: 0.
- Unresolved-conflict count: 0.
- Frozen count: 0.
- Assigned-split count: 0.

## Issue Classification

| Category | Finding | Stabilization outcome |
| --- | --- | --- |
| `annotation_error` | `pilot_0003` original query scope was too broad for the annotated Article 107 Clause 2 evidence. | Corrected through repository-level adjudication. |
| `schema_gap` | Review assurance was not explicit enough to distinguish structured automated review from qualified human legal review before schema-contract freeze. | Backward-compatible optional `reviewer_kind` and `review_assurance` metadata were added. |
| `validator_gap` | Structural validation cannot reliably infer natural-language overbreadth such as the original `pilot_0003` scope. | Kept as semantic review responsibility; no validator weakening. |
| `protocol_gap` | The protocol did not explicitly separate independent-review workflow stage from qualified human legal review claims. | Clarified generally in `docs/evaluation_protocol.md`. |
| `documentation_gap` | Pilot documentation used ambiguous human-review statistics. | Replaced with D2-resolution and qualified-human-review concepts. |
| `no_issue` | Evidence groups, qrel consistency, fallback representation, regression overlap, and draft pre-split representation were exercised without unresolved structural issues. | No blocking issue. |

No unresolved issue blocks schema stabilization.

## Schema Stability Assessment

- Schema expressiveness: sufficient for query metadata, fallback decisions,
  legal targets, qrels, evidence groups, review history, adjudication, and
  draft pre-split records.
- Evidence-group representation: stable for required groups with explicit
  chunk-level qrels and hierarchy-level legal targets.
- Qrel/group consistency: validator enforces direct qrels for acceptable
  chunks and prevents supporting evidence from completing required groups.
- Fallback representation: stable for the pilot's `incomplete_evidence` and
  `unsafe_ambiguity` boundaries.
- Review-history representation: stable after adding `reviewer_kind` and
  `review_assurance` metadata.
- Adjudication representation: sufficient for the `pilot_0003` material
  disagreement and correction history.
- Regression-overlap representation: sufficient for bridge cases through
  `regression_case_ids`.
- Pre-split draft representation: stable with `split=null`.
- Corpus-aware validation: sufficient for law IDs, chunk IDs, hierarchy, qrels,
  and review-status consistency.
- Freeze protections: implemented and tested separately; no benchmark freeze
  was performed here.

Conclusion: `stable_for_full_benchmark_construction`.

## Protocol Stability Assessment

The pilot exercised direct versus supporting evidence, complete-list coverage,
fallback decisions, blocking cases, ambiguity, cross-law evidence, independent
review, adjudication, and regression contamination. It did not exercise a
temporal/version-sensitive case because the processed chunk metadata did not
support a defensible pilot temporal label.

The stabilization task added a general review-assurance clarification. No
other protocol revision is required before full benchmark construction.

## Validator Stability Assessment

The validator can enforce record shape, enum values, referential integrity,
fallback invariants, qrel and evidence-group consistency, corpus-aware law and
chunk references, review-record support for query review summaries, split
consistency, regression-overlap restrictions, and freeze preconditions.

The validator remains structural. Natural-language overbreadth, such as the
original `pilot_0003` scope, cannot be inferred reliably by structural
validation alone and remains a semantic review responsibility.

## Review Assurance Limitation

Primary annotation and second-pass review were performed as structured
repository workflows.

They do not constitute qualified human legal review.

```text
structured_automated_review_completed = true
qualified_human_legal_review_completed = false
```

Development items may proceed after primary annotation, structured independent
review, and adjudication of material disagreements if they are accurately
labeled. Held-out items require an independent reviewer pass. Before frozen
held-out use, any blocking or high-risk held-out item involving criminal
liability, sanctions or penalties, eligibility, procedural deadlines,
cross-law interpretation, fallback safety, complete legal conditions, or
material temporal/version applicability must receive qualified human legal
review. If qualified human legal review is not available, the item must remain
development-only or be excluded from the frozen held-out split.

The benchmark must not be described as `expert-reviewed`, `lawyer-reviewed`,
or `legally validated` unless qualified human legal review actually occurred
and is recorded. It may be described as `source-grounded`,
`schema-validated`, `corpus-aware validated`,
`structured-review-completed`, or `repository-adjudicated` when those
statements are accurate.

## Remaining Risks

- No qualified human legal review has been completed.
- High-risk held-out items require qualified human legal review or exclusion
  from the frozen held-out split.
- The pilot over-samples blocking and high-risk cases.
- Semantic regression overlap still requires manual review.
- Temporal/version-sensitive cases were not exercised.
- Final benchmark quotas remain unresolved.
- Full benchmark annotation may expose new edge cases.

## Stabilization Decision

The current schema version `1.0` may be used for full benchmark construction.
This freezes the schema contract, not the pilot data.

No held-out use of the pilot is authorized. No split manifest, benchmark
manifest, benchmark release, baseline run, or retrieval comparison was created
or performed.
