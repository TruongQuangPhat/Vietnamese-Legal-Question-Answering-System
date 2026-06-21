# Legal QA Evaluation

## Purpose and Authority

This file is the canonical durable evaluation reference for VnLaw-QA. It
defines the legal QA benchmark protocol, schema contract, validation behavior,
split and freeze policy, review policy, metrics contract, and CLI usage for
controlled comparison of the frozen Naive RAG baseline and future retrieval
variants.

Authority and supporting references:

- `AGENTS.md` remains the canonical repository instruction source.
- `PROJECT_CONTEXT.md` remains the canonical current-state and roadmap source.
- `docs/naive_rag.md` remains the canonical Naive RAG technical reference.
- `docs/advanced_rag.md` remains the Advanced RAG design reference.
- `docs/phase10_tracer.md` is the active Phase 10 operational dashboard.
- `data/eval/legal_qa_benchmark/pilot/README.md` describes the draft pilot
  dataset and review summary.

This document does not claim that Advanced RAG is already better than the
frozen Naive RAG baseline.

## Evaluation Architecture

Current implemented evaluation code lives under:

```text
src/evaluation/benchmark/
scripts/evaluation/
configs/evaluation/legal_qa_benchmark.yml
tests/unit/evaluation/benchmark/
tests/integration/evaluation/test_benchmark_workflow.py
```

This layer is separate from the Naive RAG regression logic under
`src/retrieval/` and `scripts/retrieval/`. It currently implements benchmark
schemas, deterministic loaders, validation, grouped splitting, fingerprinting,
freeze support, and thin CLI wrappers. It does not implement sparse retrieval,
BM25, RRF, fusion, reranking, GraphRAG, API, UI, fine-tuning, benchmark
metrics, or baseline execution.

## Safety and Legal Accuracy Principles

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
- VnLaw-QA supports legal research and must not be represented as production
  legal advice.

## Benchmark Scope

The benchmark protocol covers:

- benchmark query construction;
- legal target annotation;
- evidence judgments;
- evidence groups;
- expected decision annotation;
- review and adjudication;
- grouped development and held-out split;
- benchmark freeze;
- controlled system comparison.

The protocol does not cover production legal advice, model fine-tuning,
GraphRAG, API/UI, or retrieval variants. Those are separately scoped future
work.

## Inclusion and Exclusion Policy

A query may be included only when all mandatory criteria are met:

- The query is natural and understandable.
- The query is answerable from the frozen corpus, or intentionally designed as
  a fallback case.
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

## Domain Taxonomy

Each case has one primary domain. Secondary domains are optional and should be
used only when cross-law coverage genuinely requires them.

| Domain identifier | Scope |
| --- | --- |
| `constitutional_state_rights` | Constitutional rules, state structure, citizen rights, and public authority organization. |
| `civil_family_identity` | Civil rights, identity, residence, civil status, marriage, family, and personal status. |
| `criminal_procedure_penalty` | Criminal liability, crimes, penalties, and criminal procedure. |
| `civil_procedure_dispute_resolution` | Civil court procedure and private-law dispute process. |
| `land_real_estate_construction_environment` | Land, housing, real estate business, construction, notarization tied to property, and environmental protection. |
| `business_banking_tax` | Enterprise, investment, commerce, banking, competition, bankruptcy, and tax obligations. |
| `traffic_public_order_sanctions` | Traffic rules, road infrastructure, public order, alcohol harm prevention, and administrative violation handling. |
| `labor_employment_social_security` | Labor relations, employment, occupational safety, social insurance, health insurance, and social security benefits. |
| `consumer_health_education_digital_ip` | Consumer rights, health care, education, cybersecurity, electronic transactions, intellectual property, and food safety. |
| `administrative_government_interaction` | Complaints, denunciations, access to information, and citizen interaction with administrative authorities. |
| `maritime_transport` | Maritime law and specialized transport rules not covered by road traffic. |

## Question-Type Taxonomy

Question types are multi-valued. Assign all types that materially affect
annotation, retrieval, or evaluation.

| Question type | Definition |
| --- | --- |
| `single_article_lookup` | The answer is anchored mainly in one article. |
| `clause_point_lookup` | The answer requires a specific clause or point. |
| `complete_list` | The answer must list all required legal elements in scope. |
| `conditions_and_exceptions` | The answer requires both conditions and exceptions or exclusions. |
| `multi_evidence` | The answer requires multiple provisions within one or more documents. |
| `cross_law` | The answer requires provisions from multiple laws. |
| `temporal_version_sensitive` | The applicable answer depends on date or legal version. |
| `paraphrase` | The query uses common-language phrasing rather than legal phrasing. |
| `lexical_mismatch` | The query and relevant provision use materially different terminology. |
| `ambiguous` | The query has more than one plausible legal interpretation. |
| `fallback` | The expected decision is fallback. |
| `near_duplicate_provision` | Similar provisions may confuse retrieval or selection. |
| `definition` | The answer asks for a legal definition or defined term. |
| `procedure` | The answer asks about process, filings, steps, or deadlines. |
| `eligibility` | The answer asks who qualifies or under what criteria. |
| `rights_and_obligations` | The answer asks about rights, duties, prohibitions, or guarantees. |
| `sanction_or_penalty` | The answer asks about sanctions, penalties, or liability consequences. |

## Expected Decision Policy

The frozen benchmark uses two final ground-truth decisions:

```text
answer_allowed
fallback_required
```

`answer_allowed` is conservative. It requires sufficient direct and citable
evidence in the frozen corpus for the query scope. The evidence must support
the legal claim at the required hierarchy depth and satisfy all required
evidence groups.

`fallback_required` applies when any condition is true:

- no relevant legal target exists in the frozen corpus;
- evidence is incomplete;
- evidence is indirect-only;
- ambiguity is unsafe;
- temporal or version scope is unresolved;
- complete-list evidence is incomplete.

Fallback invariants:

```text
expected_decision=fallback_required requires the fallback question type
the fallback question type requires expected_decision=fallback_required
```

Every fallback case requires `fallback_reason`. Approved categories are:

```text
no_relevant_target
incomplete_evidence
indirect_only_evidence
unsafe_ambiguity
unresolved_temporal_scope
out_of_corpus
```

Existing Phase 9 regression assets may still contain `needs_review`. The
broader frozen benchmark must adjudicate final ground truth to either
`answer_allowed` or `fallback_required`.

## Legal Targets

Legal target annotations use stable snake_case fields:

```text
law_id
document_title
article_number
clause_number
point_label
match_level
target_role
```

Approved `target_role` values are:

```text
required
alternative
supporting
exclusion
```

Use canonical `law_id` values from `configs/laws/corpus_registry.yml`.
`document_title` is review metadata and must not be the primary identifier.
Hierarchy must be internally consistent:

```text
document -> article_number -> clause_number -> point_label
```

## Evidence Relevance

Only `required_direct` and `alternative_direct` evidence may satisfy a
required evidence group.

| Relevance level | Directly citable | Can satisfy required group | Can contribute to `answer_allowed` |
| --- | --- | --- | --- |
| `required_direct` | Yes | Yes | Yes, when it satisfies an approved required group. |
| `alternative_direct` | Yes | Yes, when approved for that group. | Yes, when it is an approved alternative for that group. |
| `supporting` | Only for an explicitly annotated contextual or secondary claim using selected child evidence. | No | No |
| `near_miss` | No | No | No |
| `irrelevant` | No | No | No |

Required semantic rules:

```text
supporting evidence never completes a required evidence group
supporting evidence does not repair missing direct evidence
contextual usefulness is separate from legal sufficiency
near_miss != relevant evidence
lexical similarity != legal support
parent context != directly citable evidence
```

## Evidence Groups and Completeness

Evidence groups are semantic requirements, not simple lists of gold chunks.
Each required group represents one legal element necessary for a complete
answer.

Each group should define:

- `evidence_group_id`;
- `requirement`;
- `minimum_hits`;
- `acceptable_chunk_ids`;
- `acceptable_legal_targets`;
- `review_notes`.

`acceptable_chunk_ids` support exact qrels, retrieval evaluation, and frozen
evidence references. `acceptable_legal_targets` support hierarchy-level
validation and approved alternatives. At least one must be present during
draft annotation. A frozen `answer_allowed` benchmark item must include
explicit `acceptable_chunk_ids` for every required evidence group.
`acceptable_legal_targets` must not replace chunk-level qrels in a frozen
benchmark.

Distinguish:

```text
retrieved complete evidence
selected complete evidence
generated complete answer
```

For complete-list questions, all required groups must be satisfied.

## Blocking Cases and Global Hard Violations

Global hard violations apply to every case regardless of the case-level
`blocking` flag:

- fabricated legal provision or citation;
- unknown or invalid citation ID;
- substantive legal answer when `expected_decision=fallback_required`;
- direct citation of auxiliary parent context;
- secret leakage;
- semantically irrelevant citation used as direct legal support;
- unsupported substantive legal claim;
- substantive legal claim without the required direct citation.

Case-level blocking failures depend on the benchmark item's risk profile and
documented rationale:

- missing required condition in a complete-list answer;
- incorrect eligibility result;
- material temporal or version error;
- incorrect sanction or penalty;
- incorrect procedural deadline;
- incorrect hierarchy target.

The case-level `blocking` flag does not weaken global hard gates. Every
blocking case requires `blocking_rationale`.

## Annotation Workflow

Annotation follows:

```text
source provision selection
-> query drafting
-> primary annotation
-> independent review
-> disagreement recording
-> adjudication
-> frozen annotation
```

Primary annotation must begin from verified legal provisions or an explicitly
designed fallback objective, not from an invented expected answer.

## Independent Review and Adjudication

Independent review is required for all held-out test cases and for cases
tagged `complete_list`, `cross_law`, `temporal_version_sensitive`,
`fallback`, `ambiguous`, or blocking. Review must verify query clarity, legal
scope, hierarchy targets, direct evidence support, missing conditions and
exceptions, completeness, expected decision, blocking status, and temporal
applicability.

Disagreements must be recorded. Adjudication is mandatory for disagreements
about expected decision, legal target, relevance level, evidence sufficiency,
evidence-group completeness, blocking status, temporal scope, or benchmark
inclusion.

Allowed review statuses:

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

## Review Assurance Policy

Review assurance is separate from workflow stage. Independent review means a
reviewer pass independent from the primary annotator; it does not by itself
mean qualified human legal review. Structured automated second-pass review may
satisfy development workflow discipline when clearly labeled, but it must not
be described as `expert-reviewed`, `lawyer-reviewed`, or `legally validated`.

`ReviewRecord` supports:

```text
reviewer_kind
review_assurance
reviewer_id
review_stage
status
resolution_notes
```

Before frozen held-out use, any blocking or high-risk held-out item involving
criminal liability, sanctions or penalties, eligibility, procedural deadlines,
cross-law interpretation, fallback safety, complete legal conditions, or
material temporal/version applicability must receive qualified human legal
review. If qualified human legal review is not available, the item must remain
development-only or be excluded from the frozen held-out split.

Allowed descriptions, when accurate:

```text
source-grounded
schema-validated
corpus-aware validated
structured-review-completed
repository-adjudicated
```

The benchmark must not be described as `expert-reviewed`, `lawyer-reviewed`,
or `legally validated` unless qualified human legal review actually occurred
and is recorded.

## Temporal and Ambiguity Policy

Temporal metadata:

```text
version_sensitive
as_of_date
applicable_law_id
applicable_version_notes
```

Queries containing relative temporal language such as "currently" must be
normalized to a specific benchmark reference date. Do not combine evidence
from incompatible legal versions. If temporal applicability cannot be
established safely, mark the case `fallback_required` or exclude it.

Ambiguous queries may remain only when the ambiguity category is annotated and
the expected decision is reviewable. Unsafe ambiguity should generally result
in `fallback_required`. The evaluator must not infer missing facts that were
not supplied in the query.

## Duplicate and Leakage Policy

Official duplicate normalization may include Unicode, whitespace, controlled
case, and controlled punctuation normalization. It must preserve Vietnamese
diacritics. Diacritic-insensitive similarity may flag potential duplicates for
manual review only; it must not automatically merge, exclude, group, relabel,
or split Vietnamese legal queries.

These keys must stay in one split:

```text
case_family_id
source_provision_group_id
```

The existing five-case regression suite remains separate from held-out proof.
A benchmark case that substantially overlaps an existing regression case must
not be assigned to `held_out_test`; it may be assigned to `development` under
the same `case_family_id` or excluded.

## Development and Held-Out Policy

If no learned component is trained, use:

```text
development
held_out_test
```

Development may be used for threshold selection, fusion tuning,
candidate-depth tuning, reranker configuration selection, and error analysis.
Held-out test must not be used for parameter tuning, prompt tuning,
selection-policy tuning, repeated configuration selection, or benchmark-label
revision based on system performance.

Run the frozen dense baseline and frozen candidate systems together during the
final held-out evaluation after configurations are fixed. If learned
components are trained later, require train/validation/test splits.

## Full Benchmark Construction Policy

Full benchmark construction must use the schema contract version `1.0` and
the canonical files listed below. Draft annotation may be built before a split
exists, but frozen benchmark data requires a complete review history,
corpus-aware validation with zero errors, a deterministic grouped split, and
manifest fingerprints.

Case eligibility tiers:

| Tier | Meaning |
| --- | --- |
| `dev_eligible` | The case can be used for development after primary annotation, independent review, adjudication of material conflicts, complete qrels, and validation. |
| `held_out_eligible` | The case satisfies `dev_eligible`, has no regression overlap, has no unresolved conflict, has complete split grouping keys, and satisfies the qualified-review gate when high-risk. |
| `development_only` | The case is useful for tuning, diagnostics, bridge coverage, or pilot continuity, but must not enter held-out evaluation. |
| `excluded` | The case should not be used in benchmark scoring because it is unsupported, unresolved, duplicate without purpose, temporally unsafe, or otherwise fails protocol requirements. |

Additional eligibility rules:

- regression-overlap bridge cases are not held-out eligible;
- unresolved conflict cases are not held-out eligible;
- `answer_allowed` cases require direct chunk-level qrels;
- fallback cases require `fallback_reason`;
- temporal cases require defensible `as_of_date` and applicable version
  metadata;
- duplicate, paraphrase, and source-provision groups must stay in one split;
- high-risk held-out cases require qualified human legal review or exclusion
  from held-out use.

Before `split_manifest.json` is created, all benchmark JSONL files must pass
schema and corpus-aware validation, review histories must be complete enough
for split eligibility, regression-overlap declarations must be present, and
duplicate/paraphrase/source-provision grouping must be reviewed.

Before `benchmark_manifest.json` is created, every frozen record must have an
assigned split matching the split manifest, all material conflicts must be
resolved or excluded, all high-risk held-out review requirements must be met,
raw and canonical fingerprints must be computed, and `benchmark_version` must
be a release-valid value rather than `draft`.

## Benchmark Schemas

Typed schema boundaries live under `src/evaluation/benchmark/`:

- `BenchmarkQuery`: query text, domain, question types, expected decision,
  fallback metadata, grouping keys, review status, split, and regression
  overlap declarations.
- `TemporalMetadata`: version sensitivity, `as_of_date`, and
  `applicable_law_id`.
- `LegalTarget`: reviewed legal hierarchy targets using canonical `law_id`.
- `EvidenceJudgment`: chunk-level relevance judgments.
- `EvidenceGroup`: semantic evidence requirements with
  `acceptable_chunk_ids` and `acceptable_legal_targets`.
- `ReviewRecord`: primary review, independent review, adjudication,
  reviewer-kind, and review-assurance provenance.
- `SplitManifest`: deterministic grouped split assignments.
- `BenchmarkManifest`: frozen benchmark manifest with checksums.
- `BenchmarkConfig`: non-secret benchmark configuration.

All public input models reject unknown fields.

## Canonical Data Files

Future canonical benchmark data is expected under:

```text
data/eval/legal_qa_benchmark/benchmark_queries.jsonl
data/eval/legal_qa_benchmark/benchmark_targets.jsonl
data/eval/legal_qa_benchmark/benchmark_qrels.jsonl
data/eval/legal_qa_benchmark/evidence_groups.jsonl
data/eval/legal_qa_benchmark/review_records.jsonl
data/eval/legal_qa_benchmark/split_manifest.json
data/eval/legal_qa_benchmark/benchmark_manifest.json
```

The current draft pilot lives under `data/eval/legal_qa_benchmark/pilot/`.
It is not frozen and is not held-out proof. Runtime or draft diagnostics may
be written under `artifacts/reports/evaluation/`.

## Loaders and Validation

Loaders provide deterministic UTF-8 JSON/JSONL parsing, typed model returns,
malformed JSON failures with filename and one-based line number, duplicate ID
rejection, unknown-field rejection, and Vietnamese Unicode preservation.

`BenchmarkValidator` separates:

- record-level checks enforced by Pydantic models;
- referential integrity across query, target, qrel, group, and review files;
- decision and evidence sufficiency invariants;
- hierarchy and question-type consistency;
- review, conflict, adjudication, and freeze requirements;
- split leakage and regression contamination checks;
- qrel and evidence-group consistency checks;
- optional corpus-aware validation against `configs/laws/corpus_registry.yml`
  and `data/processed/legal_chunks.jsonl`.

Corpus-aware validation is read-only. It does not call Qdrant, OpenRouter,
indexing, generation, or retrieval.

## Grouped Deterministic Splitting

`create_grouped_split` builds transitive connected components over:

```text
case_family_id
source_provision_group_id
```

Regression-overlap cases are forced to `development`. The splitter records a
canonical semantic input fingerprint of query records sorted by stable query
ID, uses a configurable seed, keeps output ordering stable, and reports
stratification summaries. Multi-label stratification for `question_types` is
diagnostic, not a hard quota.

`SplitManifest.assignments` is the canonical split assignment.
`BenchmarkQuery.split` is a denormalized review and freeze summary that must
match the manifest before freeze.

## Fingerprinting and Freeze

Fingerprint helpers distinguish:

```text
raw_file_sha256
canonical_content_sha256
```

`raw_file_sha256` hashes exact stored bytes. `canonical_content_sha256` parses
records through typed schemas, serializes canonical JSON with sorted object
keys, sorts record collections by stable IDs where order is not semantic, and
preserves Vietnamese Unicode content.

Freeze support:

1. loads all benchmark files;
2. validates the dataset;
3. refuses freeze when validation errors exist;
4. refuses freeze when `benchmark_version` is `draft` or another placeholder;
5. refuses to overwrite an existing output manifest;
6. refuses freeze when queries are not frozen;
7. computes raw file checksums and canonical content fingerprints;
8. writes `BenchmarkManifest` atomically to a caller-provided path;
9. reloads and verifies the written manifest.

Manifests reject secret-like keys and values. They must not contain local
environment dumps, API keys, tokens, Authorization headers, or access tokens.

## CLI Usage

Validate benchmark files:

```bash
uv run python scripts/evaluation/validate_benchmark.py \
  --queries data/eval/legal_qa_benchmark/benchmark_queries.jsonl \
  --legal-targets data/eval/legal_qa_benchmark/benchmark_targets.jsonl \
  --evidence-judgments data/eval/legal_qa_benchmark/benchmark_qrels.jsonl \
  --evidence-groups data/eval/legal_qa_benchmark/evidence_groups.jsonl \
  --review-records data/eval/legal_qa_benchmark/review_records.jsonl \
  --config configs/evaluation/legal_qa_benchmark.yml
```

Create a grouped split manifest:

```bash
uv run python scripts/evaluation/create_benchmark_split.py \
  --queries data/eval/legal_qa_benchmark/benchmark_queries.jsonl \
  --config configs/evaluation/legal_qa_benchmark.yml \
  --output data/eval/legal_qa_benchmark/split_manifest.json
```

Freeze a benchmark manifest:

```bash
uv run python scripts/evaluation/freeze_benchmark.py \
  --queries data/eval/legal_qa_benchmark/benchmark_queries.jsonl \
  --legal-targets data/eval/legal_qa_benchmark/benchmark_targets.jsonl \
  --evidence-judgments data/eval/legal_qa_benchmark/benchmark_qrels.jsonl \
  --evidence-groups data/eval/legal_qa_benchmark/evidence_groups.jsonl \
  --review-records data/eval/legal_qa_benchmark/review_records.jsonl \
  --split-manifest data/eval/legal_qa_benchmark/split_manifest.json \
  --change-log "Initial reviewed benchmark freeze." \
  --output data/eval/legal_qa_benchmark/benchmark_manifest.json
```

Exit codes:

- `0`: command completed and validation passed where applicable.
- `1`: validation completed but found benchmark errors.
- `2`: command could not run because inputs, config, or file I/O failed.

## Metrics Contract

Required metric groups are defined but not yet implemented in this layer.

Retrieval:

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

Decision and safety:

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

Generation:

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

Operational:

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

## Schema Versioning

The schema contract version `1.0` is frozen for full benchmark construction as
of 2026-06-21. This freezes the field contract, enum values, validation
semantics, and review-assurance metadata. It does not freeze pilot records,
create held-out splits, release a benchmark version, or prevent documented bug
fixes.

Breaking schema changes require a new incompatible schema version and an
explicit migration. Examples include removing a field, renaming a field,
changing field meaning, changing an enum incompatibly, or changing cross-file
identity semantics.

Backward-compatible schema changes require an explicit version decision and
tests. Documentation or validation clarifications that do not change accepted
data shape or semantic meaning may keep the schema version, but they must be
recorded in the change log. Existing frozen data must not be silently
reinterpreted.

## Current Limitations

- The reviewed generation suite in `src/retrieval/` has only five regression
  cases and is not held-out proof.
- The draft pilot is not frozen, not held-out, and has not received qualified
  human legal review.
- Metric computation for the broader benchmark is not implemented yet.
- Temporal/version-sensitive pilot cases were not exercised because current
  processed chunk metadata is insufficient for a defensible pilot temporal
  label.
- Semantic regression overlap detection is not fully automatic.
- Domain quotas, final benchmark size, numeric relevance gains, sparse
  architecture, and reranker choices remain open.
- There is no overwrite mode for frozen benchmark manifests. Corrections
  should normally use a new benchmark version and output path.
