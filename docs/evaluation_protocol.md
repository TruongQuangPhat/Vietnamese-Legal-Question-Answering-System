# Legal QA Evaluation Protocol

## 1. Purpose and Authority

This document defines the broader legal QA benchmark, annotation, review,
split, freeze, and evaluation protocol for controlled comparison of the frozen
Naive RAG baseline and future retrieval variants.

- `AGENTS.md` is the canonical repository instruction source.
- `PROJECT_CONTEXT.md` is the canonical current-state and roadmap source.
- `docs/naive_rag.md` is the canonical Naive RAG reference.
- `docs/phase10_tracer.md` tracks temporary Phase 10 progress.
- This protocol defines durable evaluation rules for benchmark construction
  and controlled comparison.
- This document does not claim that Advanced RAG is already better than the
  frozen Naive RAG baseline.

## 2. Scope

This protocol covers:

- benchmark query construction;
- legal target annotation;
- evidence judgments;
- evidence groups;
- expected decision annotation;
- legal review and adjudication;
- grouped development and held-out test split;
- benchmark freeze;
- controlled system comparison.

This protocol does not yet cover:

- implementation schemas;
- BM25 or sparse indexing;
- RRF or fusion implementation;
- reranking implementation;
- GraphRAG;
- API or UI;
- fine-tuning;
- production legal advice.

## 3. Core Legal and Safety Principles

- Legal answers require trusted legal sources.
- Every legal answer requires traceable citations.
- Do not fabricate legal provisions, laws, articles, clauses, points,
  penalties, procedures, effective dates, or citations.
- Preserve legal hierarchy: Phần -> Chương -> Mục -> Điều -> Khoản -> Điểm.
- Prefer consolidated documents when available.
- Use fallback when evidence is insufficient, incomplete, unsafe, or only
  indirectly relevant.
- Generation may use selected evidence only.
- Auxiliary parent context is not directly citable unless selected child
  evidence explicitly supports the claim.
- Citation-ID validity is not semantic faithfulness.
- The system supports legal research and must not be represented as production
  legal advice.

## 4. Benchmark Inclusion Policy

A query may be included only when all mandatory criteria are met:

- The query is natural and understandable.
- The query is answerable from the frozen corpus, or is intentionally designed
  as a fallback case.
- The legal scope is explicit enough for review.
- The expected decision is reviewable.
- Traceable legal targets are provided when the expected decision is
  `answer_allowed`.
- Reviewer notes explain the benchmark purpose and known risks.
- The expected legal outcome is based on verified source provisions or an
  explicit fallback objective, not an invented expectation.

Exclude a query when any exclusion criterion applies:

- The query has unresolvable ambiguity.
- The expected answer is unsupported by the frozen corpus.
- The query requires an unavailable external legal source while marked
  `answer_allowed`.
- Reviewer conflict remains unresolved.
- The query is a duplicate without a deliberate benchmark purpose.
- The query cannot be assigned a safe temporal scope when temporal scope is
  material.

## 5. Domain Taxonomy

The domain taxonomy is based on `configs/laws/corpus_registry.yml`. Each case
must have one primary domain. Secondary domains are optional and should be used
only when a cross-law answer genuinely requires them.

| Domain identifier | Definition | Inclusion examples | Boundary notes |
| --- | --- | --- | --- |
| `constitutional_state_rights` | Constitutional rules, state structure, citizen rights, and public authority organization. | Constitution, National Assembly, Government, local government, courts, procuracy. | Use this for institutional power and fundamental rights; use `administrative_government_interaction` for complaint or information-access procedures. |
| `civil_family_identity` | Civil rights, identity, residence, civil status, marriage, family, and personal status. | Civil Code, identity, residence, civil status, marriage and family. | Use secondary domains when property, labor, or administrative procedure is essential to the answer. |
| `criminal_procedure_penalty` | Criminal liability, crimes, penalties, and criminal procedure. | Criminal Code and Criminal Procedure Code questions. | Administrative sanctions belong to `traffic_public_order_sanctions` unless the question is criminal. |
| `civil_procedure_dispute_resolution` | Civil court procedure and private-law dispute process. | Civil Procedure Code, court filing, procedural rights. | Substantive civil-law questions belong to `civil_family_identity` unless procedure is central. |
| `land_real_estate_construction_environment` | Land, housing, real estate business, construction, notarization tied to property, and environmental protection. | Land-use rights, housing ownership, real estate business, construction permits, environmental duties. | Use `business_banking_tax` for commercial obligations not tied to real estate or construction. |
| `business_banking_tax` | Enterprise, investment, commerce, banking, competition, bankruptcy, and tax obligations. | Company formation, investment conditions, credit institutions, personal or corporate tax. | Consumer protection belongs to `consumer_health_education_digital_ip` unless business/tax law is the direct target. |
| `traffic_public_order_sanctions` | Traffic rules, road infrastructure, public order, alcohol harm prevention, and administrative violation handling. | Road traffic safety, road law, administrative sanctions, alcohol-related public safety. | Criminal traffic offenses belong to `criminal_procedure_penalty`. |
| `labor_employment_social_security` | Labor relations, employment, occupational safety, social insurance, health insurance, and social security benefits. | Annual leave, employment, unemployment insurance, social insurance, health insurance. | Health-care service rules belong to `consumer_health_education_digital_ip` unless insurance entitlement is central. |
| `consumer_health_education_digital_ip` | Consumer rights, health care, education, cybersecurity, electronic transactions, intellectual property, and food safety. | Consumer protection, medical examination, education, digital transactions, cybersecurity, IP, food safety. | Use secondary domains for business, tax, or sanctions when those are necessary legal targets. |
| `administrative_government_interaction` | Complaints, denunciations, access to information, and citizen interaction with administrative authorities. | Complaint, denunciation, information access. | Institutional organization belongs to `constitutional_state_rights`; administrative court procedure belongs to `constitutional_state_rights` or procedure-specific annotation when the court process is central. |
| `maritime_transport` | Maritime law and specialized transport rules not covered by road traffic. | Ship, maritime activity, sea carriage. | Road traffic belongs to `traffic_public_order_sanctions`. |

## 6. Question-Type Taxonomy

Question types are multi-valued. Assign all types that materially affect
annotation, retrieval, or evaluation.

| Question type | Definition | Inclusion rule | Common annotation risk | Multi-valued |
| --- | --- | --- | --- | --- |
| `single_article_lookup` | The answer is anchored mainly in one article. | Use when one article is enough for a complete answer. | Treating child clauses as complete when the article has exceptions. | Yes |
| `clause_point_lookup` | The answer requires a specific clause or point. | Use when article-level evidence is too broad. | Accepting sibling clauses or points as direct support. | Yes |
| `complete_list` | The answer must list all required legal elements in scope. | Use for conditions, rights, prohibited acts, or procedures requiring completeness. | Missing one required element while still answering confidently. | Yes |
| `conditions_and_exceptions` | The answer requires both conditions and exceptions or exclusions. | Use when the legal result depends on both positive and negative rules. | Omitting exceptions or presenting partial conditions as complete. | Yes |
| `multi_evidence` | The answer requires multiple provisions within one or more documents. | Use when no single provision satisfies the scope. | Counting supporting evidence as complete direct evidence. | Yes |
| `cross_law` | The answer requires provisions from multiple laws. | Use when at least two law IDs are required direct targets. | Mixing unrelated provisions or missing conflict resolution. | Yes |
| `temporal_version_sensitive` | The applicable answer depends on date or legal version. | Use when effective or expiry metadata matters. | Combining incompatible legal versions. | Yes |
| `paraphrase` | The query uses common-language phrasing rather than legal phrasing. | Use when lexical overlap with law text is low but intent is clear. | Over-broad semantic matches. | Yes |
| `lexical_mismatch` | The query and relevant provision use materially different terminology. | Use when exact-term retrieval is expected to struggle. | Mistaking semantic similarity for legal support. | Yes |
| `ambiguous` | The query has more than one plausible legal interpretation. | Use when ambiguity is intentional and reviewable. | Letting the evaluator infer facts not stated by the query. | Yes |
| `fallback` | The expected decision is fallback. | Use when answer generation should be declined. | Treating weak or indirect evidence as answerable. | Yes |
| `near_duplicate_provision` | Similar provisions may confuse retrieval or selection. | Use when near-miss provisions are intentionally present. | Counting a similar but legally wrong provision as relevant. | Yes |
| `definition` | The answer asks for a legal definition or defined term. | Use when a definitional provision is the direct target. | Pulling explanatory context instead of the definition. | Yes |
| `procedure` | The answer asks about process, filings, steps, or deadlines. | Use when procedural sequence or deadline matters. | Missing a required step or timing condition. | Yes |
| `eligibility` | The answer asks who qualifies or under what criteria. | Use when person, entity, or condition eligibility is central. | Ignoring exclusions or special groups. | Yes |
| `rights_and_obligations` | The answer asks about rights, duties, prohibitions, or guarantees. | Use when legal entitlement or duty is central. | Stating duties without the subject or scope. | Yes |
| `sanction_or_penalty` | The answer asks about sanctions, penalties, or liability consequences. | Use when penalty severity or sanction type is central. | Unsafe answer from wrong hierarchy level or legal version. | Yes |

## 7. Expected Decision Policy

The broader frozen benchmark uses two final ground-truth decisions:

```text
answer_allowed
fallback_required
```

`answer_allowed` is conservative. It requires sufficient direct and citable
evidence in the frozen corpus for the scope of the question. The evidence must
support the legal claim at the required hierarchy depth and must satisfy all
required evidence groups.

`fallback_required` applies when any of these conditions are true:

- no relevant legal target exists in the frozen corpus;
- evidence is incomplete;
- evidence is indirect-only;
- ambiguity is unsafe;
- temporal or version scope is unresolved;
- complete-list evidence is incomplete.

Fallback consistency invariants:

```text
expected_decision=fallback_required requires the fallback question type
the fallback question type requires expected_decision=fallback_required
```

Every fallback case must include `fallback_reason`. Planned semantic
categories are:

```text
no_relevant_target
incomplete_evidence
indirect_only_evidence
unsafe_ambiguity
unresolved_temporal_scope
out_of_corpus
```

Stage C may encode these categories as an enum only after confirming they cover
all protocol cases.

Existing Phase 9 regression assets may still contain `needs_review`. The
broader frozen benchmark must adjudicate final ground truth to either
`answer_allowed` or `fallback_required`. Do not modify existing Phase 9
regression assets.

## 8. Evidence Relevance Policy

Only `required_direct` and `alternative_direct` evidence may satisfy a
required evidence group.

| Relevance level | Directly citable | Can satisfy a required evidence group | Positive relevance gain | Can contribute to `answer_allowed` |
| --- | --- | --- | --- | --- |
| `required_direct` | Yes | Yes | Yes | Yes, when it satisfies an approved required group. |
| `alternative_direct` | Yes | Yes, when it is an approved alternative for that group | Yes | Yes, when it is an approved alternative for that group. |
| `supporting` | When supporting evidence is citable for a contextual or secondary claim, it must still be selected child evidence and must be explicitly linked to that non-core claim. Auxiliary parent context remains non-citable. | No | Unresolved until metric implementation | No |
| `near_miss` | No | No | No | No |
| `irrelevant` | No | No | No | No |

No individual evidence item is sufficient when the query contains additional
unsatisfied required evidence groups.

Required semantic rules:

```text
supporting evidence never completes a required evidence group
supporting evidence does not repair missing direct evidence
contextual usefulness is separate from legal sufficiency
supporting != sufficient direct evidence
near_miss != relevant evidence
lexical similarity != legal support
parent context != directly citable evidence
```

Direct evidence is a provision that itself supports the required legal claim at
the annotated hierarchy depth. Contextual evidence helps interpretation but
does not independently answer the query or repair missing direct evidence.
Supporting evidence may support an explicitly annotated contextual or secondary
claim, but it must not satisfy a required evidence group. Alternative evidence
is another approved direct route for the same legal element. Near-miss evidence
may share terms or a topic but is legally incorrect for the query scope.

## 9. Legal Target Policy

Each legal target annotation must include:

```text
law_id
document_title
article_number
clause_number
point_label
match_level
target_role
```

Approved `target_role` values:

```text
required
alternative
supporting
exclusion
```

Use canonical `law_id` values from `configs/laws/corpus_registry.yml`.
`document_title` is useful for review but must not be the primary identifier.

Hierarchy must be internally consistent:

```text
document
-> article_number
-> clause_number
-> point_label
```

Do not annotate `point_label` without its parent `clause_number` and
`article_number`. Do not annotate `clause_number` without its parent
`article_number`.

## 10. Evidence-Group and Completeness Policy

Evidence groups are semantic requirements, not simple lists of gold chunks.
Each required group represents one legal element necessary for a complete
answer.

Each group should define:

- `evidence_group_id`;
- whether the group is required or optional;
- `acceptable_chunk_ids`;
- `acceptable_legal_targets`;
- minimum hits;
- alternative chunks;
- group completion rules;
- query-level complete evidence rules.

`acceptable_chunk_ids` support exact qrels, retrieval evaluation, and frozen
evidence references. `acceptable_legal_targets` support hierarchy-level
validation and approved alternatives. At least one must be present during draft
annotation. A frozen `answer_allowed` benchmark item must include explicit
`acceptable_chunk_ids` for every required evidence group.
`acceptable_legal_targets` support hierarchy validation and alternative-target
review, but they must not replace chunk-level qrels in a frozen benchmark.
Any exception must be resolved before freeze; an unresolved exception prevents
the item from receiving `frozen` review status. Legal targets must not silently replace exact chunk-level qrels in metrics that
require chunk judgments.

Distinguish three stages:

```text
retrieved complete evidence
selected complete evidence
generated complete answer
```

A retrieval system may retrieve complete evidence while selection or generation
remains incomplete. For complete-list questions, all required groups must be
satisfied.

Illustrative example using existing regression concepts, not a new legal
conclusion:

```text
query_id: existing_health_insurance_children_under_6_illustration
evidence_group_id: covered_participant_group
required: true
acceptable_chunk_ids:
  - LBHYT_VBHN__placeholder_article_12_clause_3_point_h_chunk
acceptable_legal_targets:
  - law_id: LBHYT_VBHN
    article_number: "12"
    clause_number: "3"
    point_label: h
    match_level: point
minimum_hits: 1
completion: one approved direct point is enough for this group
```

Illustrative placeholder example using non-authoritative IDs:

```text
query_id: placeholder_complete_list_illustration
evidence_group_id: required_condition_a
required: true
acceptable_chunk_ids:
  - LAW_PLACEHOLDER__article_x_clause_y_point_a_chunk
acceptable_legal_targets:
  - law_id: LAW_PLACEHOLDER
    article_number: X
    clause_number: Y
    point_label: a
    match_level: point
evidence_group_id: required_condition_b
required: true
acceptable_chunk_ids:
  - LAW_PLACEHOLDER__article_x_clause_y_point_b_chunk
acceptable_legal_targets:
  - law_id: LAW_PLACEHOLDER
    article_number: X
    clause_number: Y
    point_label: b
    match_level: point
query_completion: all required condition groups must be satisfied
```

## 11. Blocking-Case Policy

This protocol separates global hard violations from case-level blocking
failures.

### Global Hard Violations

These apply to every case regardless of the case-level `blocking` flag:

- fabricated legal provision or citation;
- unknown or invalid citation ID;
- substantive legal answer when `expected_decision=fallback_required`;
- direct citation of auxiliary parent context;
- secret leakage;
- semantically irrelevant citation used as direct legal support for a
  substantive claim.
- unsupported substantive legal claim;
- substantive legal claim without the required direct citation;

### Case-Level Blocking Failures

These depend on the benchmark item's risk profile and documented rationale:

- missing required condition in a complete-list answer;
- incorrect eligibility result;
- material temporal or version error;
- incorrect sanction or penalty;
- incorrect procedural deadline;
- incorrect hierarchy target.

The case-level blocking flag does not weaken global hard gates. A global hard
violation remains blocking regardless of the benchmark item's blocking value.

Not every difficult query must be blocking. Each blocking case requires a
documented `blocking_rationale`.

## 12. Annotation Workflow

Annotation follows this sequence:

```text
source provision selection
-> query drafting
-> primary annotation
-> independent review
-> disagreement recording
-> adjudication
-> frozen annotation
```

Primary annotator responsibilities:

- start from verified legal provisions or an explicitly designed fallback
  objective;
- draft the natural-language query;
- annotate the primary domain;
- annotate optional secondary domains;
- assign question types;
- assign expected decision;
- annotate legal targets;
- annotate evidence judgments;
- define evidence groups;
- define complete-evidence requirements;
- assign blocking status;
- record temporal metadata;
- write reviewer notes.

Annotation must not begin from an invented expected answer.

## 13. Independent Review Policy

Independent review is required for all held-out test cases. It is also required
for cases tagged:

- `complete_list`;
- `cross_law`;
- `temporal_version_sensitive`;
- `fallback`;
- `ambiguous`;
- blocking.

Reviewer responsibilities:

- verify query clarity;
- verify legal scope;
- verify hierarchy targets;
- verify direct evidence support;
- check missing conditions and exceptions;
- verify completeness;
- verify expected decision;
- verify blocking status;
- verify temporal applicability.

The reviewer must not merely confirm that chunk IDs exist. Citation-ID or
chunk-ID validity is not semantic faithfulness.

## 14. Conflict and Adjudication Policy

Disagreements must be recorded rather than silently overwritten. Adjudication
is mandatory for disagreement concerning:

- expected decision;
- legal target;
- relevance level;
- evidence sufficiency;
- evidence-group completeness;
- blocking status;
- temporal scope;
- benchmark inclusion.

Allowed final review statuses:

```text
draft
primary_reviewed
independent_reviewed
conflict
adjudicated
frozen
```

Do not encode reviewer personal information beyond the minimum identifier
needed for review provenance.

## 15. Temporal and Version-Sensitive Policy

Required metadata:

```text
version_sensitive
as_of_date
applicable_law_id
applicable_version_notes
```

Queries containing relative temporal language such as "currently" must be
normalized to a specific benchmark reference date. Prefer applicable
consolidated documents when available. `applicable_law_id` must use the
canonical identifier from the corpus registry. If the repository later
introduces a separate immutable document-version ID, that must be documented
explicitly in a future schema revision rather than being silently conflated
with `law_id`. Do not combine evidence from incompatible legal versions.

If temporal applicability cannot be established safely, mark the case
`fallback_required` or exclude it.

## 16. Ambiguity Policy

Ambiguity categories:

- harmless linguistic variation;
- ambiguity resolvable from normal legal context;
- ambiguity requiring clarification;
- ambiguity unsafe for answer generation.

Ambiguous queries may remain in the benchmark only when the ambiguity category
is annotated and the expected decision is reviewable. Unsafe ambiguity should
generally result in `fallback_required`.

The evaluator must not infer missing facts that were not supplied in the query.

## 17. Duplicate, Near-Duplicate, and Leakage Policy

Definitions:

- Exact query duplicates: identical query text after whitespace normalization.
- Normalized duplicates: queries that become identical after official
  duplicate normalization.
- Paraphrase families: different query text with the same legal intent and
  target set.
- Source-provision groups: benchmark cases derived from the same provision or
  same required evidence group.
- Near-duplicate legal provisions: provisions with similar wording or legal
  topic but different legal effect.

Official duplicate normalization may include:

- Unicode normalization;
- whitespace normalization;
- controlled case normalization;
- controlled punctuation normalization.

Official duplicate normalization must preserve Vietnamese diacritics. Do not
define two queries as normalized duplicates solely because removing Vietnamese
diacritics makes them identical.

Diacritic-insensitive similarity may be used only to flag potential duplicates
for manual review. It must not automatically merge, exclude, group, or relabel
Vietnamese legal queries.

These keys must stay in one split:

```text
case_family_id
source_provision_group_id
```

The existing five-case regression suite must remain separate from held-out
proof. A benchmark case that substantially overlaps an existing regression case must
not be assigned to `held_out_test`.
It may be assigned to `development` under the same `case_family_id` or excluded
from the broader benchmark.
Grouping alone does not make an already observed case eligible for held-out
evaluation.

## 18. Development and Held-Out Test Policy

If no learned component is trained, use:

```text
development
held_out_test
```

Development is used for:

- threshold selection;
- fusion tuning;
- candidate-depth tuning;
- reranker configuration selection;
- error analysis.

Held-out test must not be used for:

- parameter tuning;
- prompt tuning;
- selection-policy tuning;
- repeated configuration selection;
- benchmark-label revision based on system performance.

Run the frozen dense baseline and frozen candidate systems together during the
final held-out evaluation after configurations are fixed.

If learned components are trained later, require train/validation/test splits.

## 19. Benchmark Freeze and Versioning Policy

Each frozen benchmark release must record:

- schema version;
- benchmark version;
- split manifest;
- dataset fingerprints;
- query and qrel checksums;
- corpus fingerprint;
- chunk fingerprint;
- review status;
- freeze date;
- change log.

Frozen held-out labels must not be edited in place. Corrections require a new
benchmark version and documented reason.

Do not include secrets or environment-variable dumps in manifests.

## 20. Metrics Contract

This section defines required metric groups only. It does not implement them.

### Retrieval

```text
Recall@1
Recall@5
Recall@10
Recall@20
MRR@10
nDCG@10
document hit rate
article hit rate
clause hit rate
point hit rate
evidence-group recall
complete-evidence coverage
irrelevant-evidence rate
near-miss rate
```

### Decision and Safety

```text
answer-allowed precision
answer-allowed recall
answer-allowed F1
fallback precision
fallback recall
fallback F1
unsafe-evidence rejection rate
all-caution answer rate
invalid citation-ID rate
parent-context citation violation rate
unsupported answer on fallback rate
```

### Generation

```text
claim support rate
unsupported claim rate
too-broad claim rate
missing-key-condition rate
citation precision
citation coverage
complete-list accuracy
blocking-case pass rate
```

### Operational

```text
retrieval latency
fusion latency
reranking latency
selection latency
generation latency
end-to-end latency
token usage
cost per query
peak memory
throughput
```

Latency aggregation should include mean, median, p95, and p99 where
appropriate.

## 21. Protocol Validation Checklist

Future schema and benchmark work must satisfy:

- [ ] all labels are defined;
- [ ] decisions are adjudicable;
- [ ] direct and contextual evidence are separated;
- [ ] complete-list semantics are explicit;
- [ ] temporal cases contain a reference date;
- [ ] fallback cases contain a reason;
- [ ] blocking cases contain a rationale;
- [ ] grouped split keys are available;
- [ ] held-out contamination rules are enforceable;
- [ ] no legal expectations are invented;
- [ ] protected corpus assets remain unchanged.

## 22. Open Questions

Unresolved design choices:

- final minimum and preferred benchmark size;
- final domain quotas;
- whether secondary domains are needed for all cross-law cases or only
  selected cases;
- relevance gain values for nDCG;
- exact blocking-case thresholds;
- reviewer identifier format;
- adjudication staffing;
- benchmark versioning convention;
- sparse retrieval architecture;
- future reranker selection.

These questions are intentionally not finalized in this protocol.

## 23. Stage B Exit Criteria

Stage B is complete when:

- inclusion and exclusion policies are approved;
- domain taxonomy is approved;
- question taxonomy is approved;
- expected decisions are defined;
- relevance levels are defined;
- evidence-group completeness is defined;
- blocking policy is defined;
- annotation and review workflows are defined;
- adjudication is defined;
- temporal and ambiguity policies are defined;
- split and leakage protection are defined;
- freeze and versioning policy are defined;
- the protocol is sufficient for Stage C schema implementation without
  inventing business rules.
