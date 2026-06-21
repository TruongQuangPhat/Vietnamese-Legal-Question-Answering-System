# Pilot Independent Review Report

## Scope and Limitations

This report records the Stage D2 structured second-pass repository review for
the draft pilot legal QA benchmark annotation.

The review covered all 19 pilot cases in:

```text
data/eval/legal_qa_benchmark/pilot/
```

The review used only repository-local, read-only corpus and regression
references:

```text
configs/laws/corpus_registry.yml
data/processed/legal_chunks.jsonl
data/eval/manual_retrieval_queries.jsonl
data/eval/manual_naive_rag_generation_queries.jsonl
data/eval/manual_faithfulness_verdicts.json
```

The pilot has completed source-grounded primary annotation, structured
automated second-pass review, and repository-level adjudication. This does not
constitute qualified human legal review. Qualified human legal review has not
been completed. This report does not claim legal-expert validation.

No split, held-out assignment, frozen benchmark, benchmark manifest, baseline
run, retrieval experiment, Qdrant call, or OpenRouter call was performed.

## Reviewer Identities

| Role | Reviewer ID | Scope |
| --- | --- | --- |
| Primary annotation | `codex_primary_annotation` | Stage D1 source-first pilot annotation |
| Independent review | `codex_independent_review_v1` | Stage D2 blind-first second-pass review |
| Adjudication | `codex_adjudication_v1` | Resolution of material D2 disagreement |

The identity separation is procedural only. It does not make this a qualified
human legal review.

## Method

For each query, the independent pass first reviewed the Vietnamese question,
the relevant child chunks, and nearby same-article chunks where material. It
then determined the expected decision, legal targets, evidence groups,
question types, fallback status, blocking status, and regression overlap before
comparing with the primary annotation.

Pydantic validation and corpus-aware validation were treated as structural
checks only, not proof of legal correctness.

## Outcome Summary

| Outcome | Count |
| --- | ---: |
| `confirmed` | 7 |
| `confirmed_with_minor_notes` | 11 |
| `material_disagreement` | 1 |
| `reject_from_pilot` | 0 |
| `unresolved_cases_requiring_human_review_for_D2_resolution` | 0 |
| `qualified_human_legal_review_completed` | false |

One material disagreement was adjudicated during this task. No case remains in
`conflict`, and no case was marked `frozen` or assigned to a split.

## Per-Case Outcomes

| Case | Outcome | Disputed fields | Proposed correction | Adjudication requirement |
| --- | --- | --- | --- | --- |
| `pilot_0001` | `confirmed_with_minor_notes` | None | None | Not required |
| `pilot_0002` | `confirmed_with_minor_notes` | None | None | Not required |
| `pilot_0003` | `material_disagreement` | `query`, `question_types`, `review_status`, `reviewer_notes` | Narrow query to ordinary Article 107 Clause 2 overtime scope and remove `conditions_and_exceptions` | Required and completed |
| `pilot_0004` | `confirmed` | None | None | Not required |
| `pilot_0005` | `confirmed_with_minor_notes` | None | None | Not required |
| `pilot_0006` | `confirmed` | None | None | Not required |
| `pilot_0007` | `confirmed_with_minor_notes` | None | None | Not required |
| `pilot_0008` | `confirmed` | None | None | Not required |
| `pilot_0009` | `confirmed_with_minor_notes` | None | None | Not required |
| `pilot_0010` | `confirmed_with_minor_notes` | None | None | Not required |
| `pilot_0011` | `confirmed` | None | None | Not required |
| `pilot_0012` | `confirmed_with_minor_notes` | None | None | Not required |
| `pilot_0013` | `confirmed` | None | None | Not required |
| `pilot_0014` | `confirmed` | None | None | Not required |
| `pilot_0015` | `confirmed` | None | None | Not required |
| `pilot_0016` | `confirmed_with_minor_notes` | None | None | Not required |
| `pilot_0017` | `confirmed_with_minor_notes` | None | None | Not required |
| `pilot_0018` | `confirmed_with_minor_notes` | None | None | Not required |
| `pilot_0019` | `confirmed_with_minor_notes` | None | None | Not required |

## Material Disagreement and Adjudication

### `pilot_0003`

Independent finding: the original query, "Công ty muốn cho người lao động làm
thêm giờ thì cần có sự đồng ý và phải giới hạn số giờ làm thêm ra sao?", was
too broad for a Clause 2-only annotation. A natural reading could require
Article 107 Clause 3 extended overtime cases. The Clause 3 child chunks list
eligible industries and cases but do not directly contain the parent-header
300-hour cap, so using the parent context as direct evidence would violate the
selected-child-evidence rule.

Adjudication decision: adopt a third corrected resolution. The query was
narrowed to ordinary overtime under Article 107 Clause 2, and
`conditions_and_exceptions` was removed from `question_types`. Legal targets,
qrels, and evidence groups remain unchanged because they are sufficient for the
corrected query scope.

Corrected query:

```text
Trong trường hợp thông thường theo khoản 2 Điều 107, công ty muốn cho người
lao động làm thêm giờ thì cần có sự đồng ý và phải giới hạn số giờ làm thêm ra
sao?
```

## High-Risk Cases

The pilot intentionally over-samples high-risk cases. The following remain
important for later qualified human legal review:

```text
pilot_0001
pilot_0002
pilot_0003
pilot_0005
pilot_0007
pilot_0009
pilot_0010
pilot_0011
pilot_0012
pilot_0013
pilot_0016
pilot_0017
pilot_0018
pilot_0019
```

## Regression-Overlap Findings

Declared regression-overlap bridge cases remain:

```text
pilot_0001
pilot_0018
```

Both are permanently ineligible for `held_out_test`. No additional deliberate
regression overlap was identified during this structured second pass. Manual
semantic-overlap review remains limited and should be repeated during full
benchmark construction.

## Schema, Validator, Protocol, and Documentation Feedback

| Category | Finding | Action |
| --- | --- | --- |
| `annotation_error` | `pilot_0003` query scope was too broad for the annotated Clause 2-only evidence. | Corrected through adjudication. |
| `schema_gap` | Review assurance was not explicit enough for schema-contract freeze. | Added optional `reviewer_kind` and `review_assurance` metadata in the stabilization task. |
| `validator_gap` | The validator cannot determine whether a natural-language query is too broad for its evidence groups. | No validator change; this remains a legal-review responsibility. |
| `protocol_gap` | Independent review did not yet explicitly distinguish structured automated review from qualified human legal review. | Clarified in the stabilization task. |
| `documentation_gap` | Pilot README did not yet record D2 status and the non-human-review limitation. | README updated. |

## Final Review State

- Total queries: 19.
- Primary review records: 19.
- Independent review records: 19.
- Adjudication records: 1.
- Query statuses: 18 `independent_reviewed`, 1 `adjudicated`.
- Frozen queries: 0.
- Assigned queries: 0.
- Unresolved cases requiring human review for D2 resolution: 0.
- Qualified human legal review completed: false.

The pilot completed schema/protocol stabilization assessment in
`stabilization_report.md`, but it still does not represent a frozen benchmark,
held-out proof, or qualified human legal review.
