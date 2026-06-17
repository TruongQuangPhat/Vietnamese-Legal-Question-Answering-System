# Phase 9D - Manual Faithfulness Review

## Scope

Phase 9D reviews the existing Phase 9C Naive RAG generation baseline at the
claim-to-citation level. It does not change retrieval, evidence selection,
fallback, prompting, generation, citation guard behavior, OpenRouter behavior,
Qdrant, indexing, or corpus processing.

The review checks:

```text
generated claim -> cited evidence ID -> safe child evidence preview -> verdict
```

Citation ID validity is not semantic faithfulness. A generated `[E#]` can map to
real selected evidence while still being too broad, incomplete, or only
partially relevant.

## Input Run

- Report path:
  `artifacts/reports/retrieval/naive_rag_generation_eval_expanded_with_evidence.json`
- Report status: `expanded_generation_eval_passed`
- Started at: `2026-06-17T06:06:43.240477+00:00`
- Finished at: `2026-06-17T06:08:20.617124+00:00`
- Provider: `openrouter`
- Model: `google/gemini-2.5-flash-lite`
- Collection: `vnlaw_chunks_bgem3_v1_full`
- Top-k: `20`
- Dataset cases: `5`
- Evidence previews: `20`
- Cited evidence previews: `14`
- Unknown citation IDs: `0`
- Missing citation IDs: `0`
- Secret leak failures: `0`

The report stores bounded `answer_preview` values. All reviewed answer previews
were marked `answer_preview_truncated=false`, so this review covers the full
serialized answer text available in the report. Full parent text is not
serialized; auxiliary parent context is represented only by flags and is not
treated as directly citable evidence.

## Review Method

For each generated-answer case, the answer was split into independently
checkable propositions. Each proposition was compared only against the cited
safe child evidence preview and citation metadata in the Phase 9C.3 report.

For fallback cases, the review checks that no LLM call occurred, citations were
absent, and the answer did not make substantive legal claims.

## Verdict Definitions

Claim-level verdicts:

- `supported`: The cited safe child evidence directly supports the complete
  claim.
- `partially_supported`: The evidence supports part of the claim but not the
  complete wording.
- `unsupported`: The cited evidence does not support the claim.
- `too_broad`: The claim extends materially beyond the question or cited
  provision even though the cited text may be real.
- `missing_key_condition`: The generated answer omits a material condition
  visible from the reviewed target context or reveals incomplete selected
  evidence for a complete answer.
- `irrelevant_citation`: The citation exists but does not directly relate to the
  claim.
- `needs_more_evidence`: The available preview is insufficient for a reliable
  verdict.
- `not_applicable_for_fallback`: The case produced fallback and no generated
  legal answer.

Case-level verdicts:

- `pass`: Every material claim is supported and no material condition is
  omitted.
- `partial`: No clearly fabricated core claim exists, but at least one claim is
  too broad, incomplete, or requires hardening.
- `fail`: At least one material claim is unsupported or uses an irrelevant
  citation.
- `needs_more_evidence`: Evidence previews are insufficient for a reliable case
  verdict.
- `not_applicable_for_fallback`: The case correctly returned fallback and made
  no legal claims.

## Case Summary

| Case | Blocking | Decision | All caution | Case verdict | Main issue |
| ---- | -------: | -------- | ----------: | ------------ | ---------- |
| `health_insurance_children_under_6_generation` | yes | `answer_allowed` | yes | `pass` | Claims are supported, but every selected evidence item is caution and auxiliary context flags require review discipline. |
| `annual_leave_days_generation` | yes | `fallback_required` | no | `not_applicable_for_fallback` | Correct fallback control; no LLM call and no citations. |
| `civil_code_scope_generation` | yes | `answer_allowed` | no | `partial` | Core Article 1 scope claim is supported; extra Article 97 claim broadens beyond the scope question. |
| `marriage_conditions_generation` | no | `answer_allowed` | yes | `partial` | Selected evidence covers only some Article 8 conditions and adds foreign-element/definition material beyond the general question. |
| `civil_rights_protection_generation` | no | `answer_allowed` | no | `partial` | Core Civil Code Article 2 claims are supported; extra criminal-procedure provisions broaden the answer. |

## Detailed Case Reviews

### `health_insurance_children_under_6_generation`

- Query: "Trẻ em dưới 6 tuổi được hưởng bảo hiểm y tế như thế nào?"
- Decision: `answer_allowed`
- Blocking status: blocking
- Manual-review flag: false
- Selected evidence count: 5
- Caution evidence count: 5
- All-caution status: true
- Selection warnings: 11, including `all_selected_evidence_caution` and
  auxiliary parent context warnings
- Case verdict: `pass`

| Claim | Cited IDs | Evidence summary | Claim verdict | Reviewer notes |
| ----- | --------- | ---------------- | ------------- | -------------- |
| Children under six are one of the groups participating in health insurance. | `[E3]` | Point h, Clause 3, Article 12, Law on Health Insurance (VBHN 2025): "Trẻ em dưới 6 tuổi". | `supported` | Direct child evidence supports the participant group. |
| A health-insurance card for a child under six is valid until the child reaches 72 months of age. | `[E1]` | Point d, Clause 3, Article 16 states the card is valid until the child reaches 72 months. | `supported` | Directly supported. |
| If the child reaches 72 months but has not reached the school-entry period, the card remains valid until September 30 of that year. | `[E1]` | The same point states the September 30 extension. | `supported` | Directly supported. |
| When seeking medical examination or treatment, a child under six who has not yet been issued a card must present other lawful papers. | `[E2]` | Clause 1, Article 28 states children under six without a health-insurance card present other lawful papers. | `supported` | Directly supported. |
| In an emergency, the patient must present card information and lawful papers before the treatment episode ends. | `[E2]` | Clause 1, Article 28 states this emergency presentation rule for the patient. | `supported` | Supported by the cited text; it is procedural context rather than a benefit-level rule. |

Completeness findings: The answer covers participant status, card validity, and
basic presentation procedure. It does not state benefit percentage or payment
level; that is not marked as a failure because the selected evidence in this
run did not provide that rule.

Citation relevance findings: Cited IDs are relevant to the claims made.

Auxiliary-context risk: All selected evidence is caution and auxiliary context
is present, but the reviewed claims are supported by the safe child previews
themselves. Auxiliary parent context was not needed as direct support.

Remaining uncertainty: A broader user interpretation of "được hưởng" could
require benefit-level evidence in a future stricter eval case.

### `annual_leave_days_generation`

- Query: "Người lao động được nghỉ hằng năm bao nhiêu ngày?"
- Decision: `fallback_required`
- Blocking status: blocking
- Manual-review flag: false
- LLM called: false
- Fallback reason: `exact_target_missing_in_eval_mode`
- Citation count: 0
- Substantive legal claims present: no
- Case verdict: `not_applicable_for_fallback`

Fallback review:

| Check | Result | Reviewer notes |
| ----- | ------ | -------------- |
| Expected fallback/review decision | pass | Decision was `fallback_required`. |
| LLM not called | pass | `llm_called=false`. |
| Citations absent | pass | `citation_count=0`. |
| Avoided substantive legal claim | pass | The answer says evidence was insufficient and does not state annual leave days. |

### `civil_code_scope_generation`

- Query: "Bộ luật Dân sự điều chỉnh những quan hệ nào?"
- Decision: `answer_allowed`
- Blocking status: blocking
- Manual-review flag: false
- Selected evidence count: 5
- Caution evidence count: 0
- All-caution status: false
- Selection warnings: 0
- Case verdict: `partial`

| Claim | Cited IDs | Evidence summary | Claim verdict | Reviewer notes |
| ----- | --------- | ---------------- | ------------- | -------------- |
| The Civil Code regulates legal status, legal conduct standards, and personal/property rights and obligations of individuals and legal entities in civil relations formed on equality, freedom of will, property independence, and self-responsibility. | `[E1]` | Article 1, Civil Code 2015 states the scope of regulation in those terms. | `supported` | This is the core answer to the query. |
| The State and central/local state agencies participate in civil relations equally with other subjects and bear civil liability. | `[E5]` | Article 97, Civil Code 2015 states this rule for state participation in civil relations. | `too_broad` | The citation supports the statement, but the claim broadens beyond the asked scope-definition question. |

Completeness findings: The core Article 1 scope is present and supported.

Citation relevance findings: `[E1]` is directly relevant. `[E5]` is legally
related but not necessary for the scope question.

Auxiliary-context risk: None identified; cited previews are safe article
context.

Remaining uncertainty: Phase 9E can decide whether extra but supported
provisions should count against answer precision.

### `marriage_conditions_generation`

- Query: "Điều kiện kết hôn theo pháp luật Việt Nam là gì?"
- Decision: `answer_allowed`
- Blocking status: non-blocking
- Manual-review flag: true
- Selected evidence count: 5
- Caution evidence count: 5
- All-caution status: true
- Selection warnings: 9, including `all_selected_evidence_caution`
- Case verdict: `partial`

| Claim | Cited IDs | Evidence summary | Claim verdict | Reviewer notes |
| ----- | --------- | ---------------- | ------------- | -------------- |
| Marriage must be voluntarily decided by the man and woman. | `[E2]` | Point b, Clause 1, Article 8, Law on Marriage and Family (VBHN 2025). | `supported` | Direct child evidence supports this condition. |
| Marriage must not fall into prohibited marriage cases under the law. | `[E1]` | Point d, Clause 1, Article 8 refers to the prohibited cases under Point a-d, Clause 2, Article 5. | `supported` | Directly supported, although the prohibited cases themselves are not expanded in the answer. |
| For marriage between a Vietnamese citizen and a foreigner, each party must comply with their own country's marriage-condition law; if conducted at a competent Vietnamese authority, the foreigner must also comply with Vietnamese marriage-condition rules. | `[E3]` | Clause 1, Article 126 states this foreign-element rule. | `too_broad` | Supported by the citation, but it is special foreign-element content beyond the general question. |
| Marriage between foreigners permanently residing in Vietnam at a Vietnamese competent authority must comply with Vietnamese marriage-condition rules. | `[E5]` | Clause 2, Article 126 states this rule. | `too_broad` | Supported by the citation, but it is special foreigner-residence content beyond the general question. |
| Marriage is the establishment of husband-wife relations under the law's conditions and marriage registration rules. | `[E4]` | Clause 5, Article 3 defines marriage. | `too_broad` | Definition is related but is not itself a marriage condition. |
| The answer presents the conditions as complete while selected Article 8 previews cover only Point b and Point d. | `[E1]`, `[E2]` | The selected safe child previews expose two Article 8 points, not the full Clause 1 condition set. | `missing_key_condition` | The selected evidence is insufficient to support a complete "bao gồm" list of Vietnamese marriage conditions. |

Completeness findings: The answer does not establish a complete Article 8
condition set from the selected child previews. This is a baseline hardening
issue, not a runtime behavior change.

Citation relevance findings: Every cited ID maps to real selected evidence, but
several citations support special cases or definitions rather than the direct
general-condition answer.

Auxiliary-context risk: All selected evidence is caution. Several cited
previews have auxiliary context flags, but the verdicts above use only the safe
child previews.

Remaining uncertainty: Full legal correctness requires a human legal reviewer
to compare against the complete Article 8 and Article 5 context, not only the
selected previews.

### `civil_rights_protection_generation`

- Query: "Quyền dân sự được công nhận và bảo vệ như thế nào?"
- Decision: `answer_allowed`
- Blocking status: non-blocking
- Manual-review flag: true
- Selected evidence count: 5
- Caution evidence count: 2
- All-caution status: false
- Selection warnings: 3
- Case verdict: `partial`

| Claim | Cited IDs | Evidence summary | Claim verdict | Reviewer notes |
| ----- | --------- | ---------------- | ------------- | -------------- |
| In Vietnam, civil rights are recognized, respected, protected, and guaranteed under the Constitution and law. | `[E1]` | Clause 1, Article 2, Civil Code 2015 states this. | `supported` | Directly answers the core query. |
| Civil rights may be restricted only by law when necessary for national defense, national security, social order and safety, social morality, or community health. | `[E2]` | Clause 2, Article 2, Civil Code 2015 states these restriction grounds. | `supported` | Directly supported and relevant. |
| The law protects life, health, honor, dignity, and property of individuals. | `[E4]` | Article 11, Criminal Procedure Code (VBHN 2025) states protection of those interests. | `too_broad` | Citation supports the statement, but it shifts from Civil Code Article 2 to criminal-procedure protections. |
| Procedure-conducting authorities must respect and protect human rights and lawful rights/interests of individuals. | `[E5]` | Article 8, Criminal Procedure Code (VBHN 2025) states this duty. | `too_broad` | Citation supports the statement, but it broadens the answer into criminal-procedure authority duties. |

Completeness findings: The core Article 2 recognition/protection and
restriction rules are present.

Citation relevance findings: `[E1]` and `[E2]` are directly relevant. `[E4]`
and `[E5]` are legally related but broaden the answer beyond the Civil Code
target context.

Auxiliary-context risk: `[E1]` carries auxiliary context flags, but the direct
child preview itself supports the claim.

Remaining uncertainty: Phase 9E should decide whether cross-code, supported but
question-broadening claims should be warning-only or blocking.

## Aggregate Findings

- Dataset cases reviewed: 5
- Generated-answer cases reviewed: 4
- Fallback cases reviewed: 1
- Generated claim/finding rows reviewed: 17
- Supported claims: 10
- Partially supported claims: 0
- Unsupported claims: 0
- Too-broad claims: 6
- Missing-key-condition findings: 1
- Irrelevant-citation findings: 0
- Needs-more-evidence findings: 0
- All-caution cases reviewed: 2
- Fallback cases reviewed: 1

Case verdict counts:

- `pass`: 1
- `partial`: 3
- `fail`: 0
- `needs_more_evidence`: 0
- `not_applicable_for_fallback`: 1

## Issues for Phase 9E

Phase 9E may convert these observations into regression thresholds or QA gates:

1. Penalize or warn on extra cited provisions that broaden beyond the user's
   question even when the citation text is real.
2. Require complete coverage for known Article-level condition lists before an
   answer can use wording such as "bao gồm".
3. Track all-caution answer-allowed cases separately from safe-evidence cases.
4. Add an answer-precision metric distinct from citation ID coverage.
5. Keep fallback controls that verify `decision != answer_allowed` implies
   `llm_called=false`.

## Remaining Limitations

- This review is based on one evaluated run and its serialized evidence
  previews.
- It is not a complete legal audit of every applicable Vietnamese legal rule.
- Model outputs can vary between runs.
- Citation ID coverage remains an ID-integrity metric, not semantic
  faithfulness.
- No automated semantic-faithfulness guarantee exists.
- Phase 9D does not implement Phase 10 retrieval improvements.

## Phase 9D Status

`phase9d_faithfulness_review_partial`

The baseline did not produce unsupported or irrelevantly cited claims in this
review, but three generated cases were only partially acceptable because they
included too-broad material or incomplete condition coverage. These findings
should be carried into Phase 9E regression threshold design.
