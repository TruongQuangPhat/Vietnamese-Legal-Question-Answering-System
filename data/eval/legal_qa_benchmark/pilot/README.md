# Legal QA Benchmark Pilot

## Status and Limitations

This directory contains draft pilot annotation for the broader legal QA
benchmark. It is not a held-out benchmark, is not frozen, and must not be used
to claim that any system improves over the Naive RAG baseline.

The pilot has completed source-grounded primary annotation, structured
automated second-pass review, and repository-level adjudication. This does not
constitute qualified human legal review. Qualified human legal review has not
been completed.

Schema/protocol stabilization and schema contract version `1.0` are complete
for full benchmark construction. Split creation and benchmark freeze are still
pending. The existing five-case suite under `data/eval/` remains separate
regression data.

## Files

```text
README.md
benchmark_queries.jsonl
benchmark_targets.jsonl
benchmark_qrels.jsonl
evidence_groups.jsonl
review_records.jsonl
```

No `split_manifest.json` or `benchmark_manifest.json` is present. Every pilot
query is pre-split with `split=null`. Query review statuses after D2 are
18 `independent_reviewed` and 1 `adjudicated`; no query is `frozen`.

Machine-readable review history is canonical in `review_records.jsonl`.

## Source-First Annotation Method

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

- Total pilot queries: 19.
- Complete-evidence cases: 7.
- Blocking cases: 14.
- Regression-overlap bridge cases: 2.
- Temporal/version-sensitive cases: 0.
- Primary review records: 19.
- Structured independent review records: 19.
- Adjudication records: 1.
- Conflict queries: 0.
- Frozen queries: 0.
- Assigned queries: 0.
- Qualified human legal review completed: false.

Expected decisions:

- `answer_allowed`: 17.
- `fallback_required`: 2.

Primary domains:

- `administrative_government_interaction`: 1.
- `business_banking_tax`: 3.
- `civil_family_identity`: 2.
- `civil_procedure_dispute_resolution`: 1.
- `consumer_health_education_digital_ip`: 2.
- `criminal_procedure_penalty`: 2.
- `labor_employment_social_security`: 4.
- `land_real_estate_construction_environment`: 1.
- `traffic_public_order_sanctions`: 3.

Question types:

- `ambiguous`: 1.
- `clause_point_lookup`: 13.
- `complete_list`: 5.
- `conditions_and_exceptions`: 3.
- `cross_law`: 1.
- `definition`: 1.
- `eligibility`: 3.
- `fallback`: 2.
- `lexical_mismatch`: 3.
- `multi_evidence`: 3.
- `near_duplicate_provision`: 1.
- `paraphrase`: 10.
- `procedure`: 2.
- `rights_and_obligations`: 8.
- `sanction_or_penalty`: 5.
- `single_article_lookup`: 10.

The pilot intentionally over-samples difficult cases, including complete-list,
eligibility, sanction, criminal, procedure, cross-law, and fallback-safety
boundaries. This blocking distribution is not a target quota for the full
benchmark.

## Review Workflow

Reviewer identities:

| Role | Reviewer ID | Scope |
| --- | --- | --- |
| Primary annotation | `codex_primary_annotation` | Source-first pilot annotation |
| Structured independent review | `codex_independent_review_v1` | Blind-first second-pass repository review |
| Repository adjudication | `codex_adjudication_v1` | Resolution of material D2 disagreement |

The identity separation is procedural only. It does not make this a qualified
human legal review.

The structured independent pass first reviewed the Vietnamese question,
relevant child chunks, and nearby same-article chunks where material. It then
determined expected decision, legal targets, evidence groups, question types,
fallback status, blocking status, and regression overlap before comparing
with primary annotation.

Pydantic validation and corpus-aware validation were treated as structural
checks only, not proof of legal correctness.

## Independent Review Summary

| Outcome | Count |
| --- | ---: |
| `confirmed` | 7 |
| `confirmed_with_minor_notes` | 11 |
| `material_disagreement` | 1 |
| `reject_from_pilot` | 0 |
| `unresolved_cases_requiring_human_review_for_D2_resolution` | 0 |
| `qualified_human_legal_review_completed` | false |

No case remains in `conflict`, and no case was marked `frozen` or assigned to
a split.

## Material Disagreements and Adjudication

### `pilot_0003`

Independent finding: the original query, "Công ty muốn cho người lao động làm
thêm giờ thì cần có sự đồng ý và phải giới hạn số giờ làm thêm ra sao?", was
too broad for a Clause 2-only annotation. A natural reading could require
Article 107 Clause 3 extended overtime cases. The Clause 3 child chunks list
eligible industries and cases but do not directly contain the parent-header
300-hour cap, so using parent context as direct evidence would violate the
selected-child-evidence rule.

Adjudication decision: adopt a third corrected resolution. The query was
narrowed to ordinary overtime under Article 107 Clause 2, and
`conditions_and_exceptions` was removed from `question_types`. Legal targets,
qrels, and evidence groups remain unchanged because they are sufficient for
the corrected query scope.

Corrected query:

```text
Trong trường hợp thông thường theo khoản 2 Điều 107, công ty muốn cho người
lao động làm thêm giờ thì cần có sự đồng ý và phải giới hạn số giờ làm thêm ra
sao?
```

## Per-Case Review Outcomes

| Case | Outcome | Adjudication |
| --- | --- | --- |
| `pilot_0001` | `confirmed_with_minor_notes` | Not required |
| `pilot_0002` | `confirmed_with_minor_notes` | Not required |
| `pilot_0003` | `material_disagreement` | Required and completed |
| `pilot_0004` | `confirmed` | Not required |
| `pilot_0005` | `confirmed_with_minor_notes` | Not required |
| `pilot_0006` | `confirmed` | Not required |
| `pilot_0007` | `confirmed_with_minor_notes` | Not required |
| `pilot_0008` | `confirmed` | Not required |
| `pilot_0009` | `confirmed_with_minor_notes` | Not required |
| `pilot_0010` | `confirmed_with_minor_notes` | Not required |
| `pilot_0011` | `confirmed` | Not required |
| `pilot_0012` | `confirmed_with_minor_notes` | Not required |
| `pilot_0013` | `confirmed` | Not required |
| `pilot_0014` | `confirmed` | Not required |
| `pilot_0015` | `confirmed` | Not required |
| `pilot_0016` | `confirmed_with_minor_notes` | Not required |
| `pilot_0017` | `confirmed_with_minor_notes` | Not required |
| `pilot_0018` | `confirmed_with_minor_notes` | Not required |
| `pilot_0019` | `confirmed_with_minor_notes` | Not required |

## Regression-Overlap Cases

- `pilot_0001`: deliberate bridge to the marriage-conditions regression
  target; permanently ineligible for `held_out_test`.
- `pilot_0018`: deliberate ambiguous-leave bridge related to the annual-leave
  regression target; permanently ineligible for `held_out_test`.

No other pilot case intentionally copies a regression query. Exact official
normalized query overlap was checked through the validator. Manual semantic
overlap review remains required because semantic overlap detection is not
fully automatic.

## Known Annotation Limitations

- Qualified human legal review has not been completed.
- High-risk held-out items require qualified human legal review or exclusion
  from the frozen held-out split.
- The pilot over-samples blocking and high-risk cases.
- `temporal_version_sensitive` was omitted because the processed chunk schema
  does not expose enough effective/expiry metadata to assign a defensible
  `as_of_date` and applicable version for pilot ground truth.
- Real held-out split behavior is omitted because pilot records remain
  pre-split.
- Frozen benchmark manifests are omitted because the pilot is draft data.
- Full benchmark construction may expose schema or protocol edge cases not
  represented in this pilot.

## Human Review Boundary

The pilot has completed source-grounded primary annotation, structured
automated second-pass review, and repository-level adjudication.

This does not constitute qualified human legal review.

```text
structured_automated_review_completed = true
qualified_human_legal_review_completed = false
```

Before frozen held-out use, any blocking or high-risk held-out item involving
criminal liability, sanctions or penalties, eligibility, procedural deadlines,
cross-law interpretation, fallback safety, complete legal conditions, or
material temporal/version applicability must receive qualified human legal
review. If qualified human legal review is not available, the item must remain
development-only or be excluded from the frozen held-out split.

## Validation Status

Latest corpus-aware pilot validation passed with:

- errors: 0;
- expected warnings: 2;
- warning cases: `pilot_0001`, `pilot_0018`;
- warning reason: regression-overlap bridge cases are unsplit and must be
  assigned to `development` or excluded before any freeze.

Record counts:

- `benchmark_queries.jsonl`: 19.
- `benchmark_targets.jsonl`: 47.
- `benchmark_qrels.jsonl`: 47.
- `evidence_groups.jsonl`: 39.
- `review_records.jsonl`: 39.

No split or benchmark manifest exists.

## Role in Full Benchmark Construction

The pilot should be used as seed patterns, schema/protocol exercise data, and
review-workflow examples. It is not automatically part of the full benchmark.

A pilot case may be promoted later only if it is rechecked under the full
benchmark review workflow and assigned an eligibility tier. `pilot_0001` and
`pilot_0018` are deliberate regression-overlap bridge cases and are
permanently ineligible for `held_out_test`. High-risk pilot cases require
qualified human legal review before any held-out use; otherwise they must
remain development-only or be excluded from frozen held-out evaluation.

## Next Steps

```text
annotation workload and qualified-review allocation
-> full benchmark construction
-> grouped split and leakage validation
-> split and benchmark manifest freeze
```

Do not use the pilot as held-out proof. Do not run benchmark freeze on pilot
data.
