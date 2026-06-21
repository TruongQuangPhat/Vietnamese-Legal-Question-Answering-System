# Phase 10 Progress Tracer

## Purpose and Authority

This document is the active operational dashboard for Phase 10 benchmark-first
Advanced RAG evaluation work. It tracks current progress, decisions, risks,
deliverables, pilot status, and next actions.

Canonical sources:

- `AGENTS.md` remains the canonical repository instruction source.
- `PROJECT_CONTEXT.md` remains the canonical current-state and roadmap source.
- `docs/evaluation.md` is the canonical durable evaluation protocol and
  implementation reference.
- `docs/naive_rag.md` is the canonical Naive RAG baseline reference.
- `docs/advanced_rag.md` remains the Advanced RAG design reference.

This tracer does not override those files. It should be deleted or archived
after Phase 10 closes and durable information has been consolidated.

## Current Status

- Corpus foundation: 52 legal documents registered, crawled, audited,
  cleaned, parsed, and chunked.
- Processed corpus: `data/processed/legal_chunks.jsonl` contains 40,389
  validated chunks.
- Embedding model: `BAAI/bge-m3`.
- Dense Qdrant collection: `vnlaw_chunks_bgem3_v1_full`.
- Dense baseline: dense retrieval, evidence construction, evidence selection,
  fallback-aware Naive RAG generation, generation evaluation, manual review
  export, manual faithfulness verdicts, and offline quality gate are complete
  under `src/retrieval/` and `scripts/retrieval/`.
- Current quality gate: `quality_gate_passed`.
- Five-case suite: regression and safety suite only, not held-out proof.
- Phase 10 stage: Stage D documentation and pilot stabilization are complete.
  Schema contract version `1.0` is frozen for full benchmark construction.
  Stage E1 full benchmark construction planning is complete. Stage E2A
  created the first 36-case full-benchmark draft batch.
- Not done: remaining full benchmark construction to the 120-case minimum,
  dev/test split, held-out benchmark freeze, frozen Naive RAG baseline run,
  metrics, sparse retrieval, fusion, reranking, GraphRAG, API, UI, and
  fine-tuning.

## Canonical Document Map

| Topic | Canonical source | Purpose | Status |
| --- | --- | --- | --- |
| Repository rules | `AGENTS.md` | Safety, workflow, protected paths, naming, validation | Active |
| Current project state | `PROJECT_CONTEXT.md` | Current architecture, baseline status, roadmap | Active |
| Naive RAG | `docs/naive_rag.md` | Baseline implementation and quality gate reference | Active |
| Evaluation protocol and implementation | `docs/evaluation.md` | Durable benchmark rules, schemas, validation, split, freeze, review policy, CLI, metrics contract | Active |
| Advanced RAG design | `docs/advanced_rag.md` | Future hybrid/fusion/reranking design reference | Active |
| Pilot data and summary | `data/eval/legal_qa_benchmark/pilot/README.md` | Draft pilot purpose, coverage, review results, limitations | Active |
| Detailed review history | `data/eval/legal_qa_benchmark/pilot/review_records.jsonl` | Machine-readable review and adjudication audit trail | Active |

## Phase 10 Objective

Primary experimental question:

```text
Does Advanced RAG improve over the frozen Naive RAG baseline on a legally
reviewed benchmark and untouched held-out test split?
```

Adding BM25, sparse retrieval, RRF, or reranking is not itself success.
Success requires held-out improvements in retrieval and evidence coverage
without unacceptable regressions in legal faithfulness, safety, latency, or
cost.

## Protected Assets and Invariants

Protected paths:

```text
data/raw/
data/interim/
data/reports/
data/processed/legal_chunks.jsonl
```

Baseline assets to preserve:

- Qdrant collection `vnlaw_chunks_bgem3_v1_full`;
- `data/eval/manual_retrieval_queries.jsonl`;
- `data/eval/manual_naive_rag_generation_queries.jsonl`;
- `data/eval/manual_faithfulness_verdicts.json`;
- `configs/retrieval/quality_gate.yml`.

Core invariants:

- trusted source and traceable citation requirements;
- no fabricated legal claims or citations;
- preserved legal hierarchy;
- selected-evidence-only generation;
- auxiliary parent context is not directly citable;
- fallback must not call the LLM;
- existing quality gate must not be weakened;
- five-case suite remains separate from held-out proof;
- test data must not be used for tuning;
- primary comparison changes retrieval only;
- secrets must never be logged or serialized.

## Stage Overview

| Stage | Status | Notes |
| --- | --- | --- |
| Stage A - Repository Inspection | Complete | Canonical instructions, skills, evaluation assets, retrieval models, utilities, CLIs, and tests inspected. |
| Stage B - Benchmark Protocol | Complete | Durable rules consolidated into `docs/evaluation.md`. |
| Stage C - Benchmark Implementation | Complete | Schemas, loaders, validator, splitting, fingerprinting, freeze support, CLIs, config, and tests implemented. |
| Stage D - Pilot Annotation and Stabilization | Complete | 19-case draft pilot, primary annotation, structured automated review, repository adjudication, and schema contract freeze complete. |
| Stage E - Full Benchmark and Split Freeze | In progress | Stage E1 planning is complete. Stage E2A created and validated the first 36-case full-benchmark draft batch. Additional batches, grouped split, leakage validation, and manifest freeze remain pending. |
| Stage F - Frozen Naive RAG Baseline | Not started | Baseline execution on frozen development and held-out splits remains pending. |
| Stage G - Hybrid Retrieval | Not started | Sparse retrieval and fusion must wait until benchmark freeze. |
| Stage H - Reranking | Not started | Reranking ablation must wait until benchmark freeze and controlled hybrid comparison. |
| Stage I - Held-Out Comparison | Not started | Final comparison must occur after candidate configurations are fixed. |
| Stage J - Closure | Not started | Adoption/rejection decision and documentation consolidation remain future work. |

## Detailed Progress Checklist

### Stage A - Repository Inspection

- [x] canonical instruction review;
- [x] relevant skill review;
- [x] git status inspection;
- [x] evaluation asset inventory;
- [x] retrieval model inventory;
- [x] reusable utility inventory;
- [x] test and CLI convention inventory;
- [x] stale documentation or instruction conflict review.

### Stage B - Benchmark Protocol

- [x] benchmark inclusion and exclusion policy;
- [x] domain taxonomy;
- [x] question-type taxonomy;
- [x] expected-decision definitions;
- [x] relevance definitions;
- [x] complete-evidence semantics;
- [x] blocking-case policy;
- [x] annotation guidelines;
- [x] independent review policy;
- [x] adjudication policy;
- [x] temporal/version-sensitive policy.

### Stage C - Benchmark Implementation

- [x] Pydantic schema models;
- [x] loaders;
- [x] validators;
- [x] grouped split implementation;
- [x] fingerprinting;
- [x] CLI wrappers;
- [x] unit tests;
- [x] integration tests;
- [x] configuration;
- [x] technical documentation.

### Stage D - Pilot Annotation

- [x] 15-20 pilot queries;
- [x] coverage of difficult question types;
- [x] primary annotation;
- [x] structured automated independent review;
- [x] repository-level adjudication;
- [x] schema/protocol stabilization;
- [x] schema version freeze;
- [ ] qualified human legal review, required before eligible high-risk
  held-out use.

### Stage E - Full Benchmark and Split Freeze

- [x] minimum reviewed benchmark size proposed;
- [x] preferred benchmark size proposed;
- [x] domain and question-type quota proposal;
- [x] case eligibility tiers;
- [x] pilot reuse policy;
- [x] full benchmark file layout;
- [x] grouped split strategy;
- [x] full benchmark review workflow;
- [x] high-risk held-out human-review gate;
- [x] Stage E2 acceptance criteria;
- [x] first full-benchmark draft batch;
- [x] batch primary annotation;
- [x] batch structured automated independent review;
- [x] batch corpus-aware validation;
- [x] narrow `.gitignore` exceptions for full benchmark JSONL files;
- [ ] duplicate and near-duplicate detection;
- [ ] paraphrase-family grouping;
- [ ] source-provision grouping;
- [ ] deterministic development/test split;
- [ ] leakage validation;
- [ ] test freeze;
- [ ] checksums;
- [ ] benchmark manifest.

### Stage F - Frozen Naive RAG Baseline

- [ ] development baseline run;
- [ ] held-out baseline execution plan;
- [ ] held-out baseline run;
- [ ] run manifest;
- [ ] runtime parameter capture;
- [ ] result validation;
- [ ] regression-suite rerun;
- [ ] quality-gate rerun.

### Stage G - Hybrid Retrieval

- [ ] sparse retrieval design;
- [ ] sparse index strategy;
- [ ] dense+sparse candidate generation;
- [ ] RRF or fusion strategy;
- [ ] development tuning;
- [ ] retrieval metric comparison;
- [ ] evidence-coverage comparison;
- [ ] latency and memory profiling.

### Stage H - Reranking

- [ ] reranker selection;
- [ ] candidate input contract;
- [ ] development-only tuning;
- [ ] reranking ablation;
- [ ] operational profiling;
- [ ] regression analysis.

### Stage I - Held-Out Comparison

- [ ] configuration freeze;
- [ ] held-out execution;
- [ ] aggregate metrics;
- [ ] domain breakdown;
- [ ] question-type breakdown;
- [ ] blocking-case review;
- [ ] safety review;
- [ ] latency and cost comparison;
- [ ] per-query wins and regressions.

### Stage J - Closure

- [ ] final conclusion;
- [ ] Advanced RAG adoption decision;
- [ ] known limitations;
- [ ] documentation consolidation;
- [ ] `PROJECT_CONTEXT.md` update;
- [ ] tracer removal or archival.

## Current Deliverables

| Deliverable | Path | Status | Notes |
| --- | --- | --- | --- |
| Durable evaluation reference | `docs/evaluation.md` | Consolidated | Canonical protocol and implementation reference. |
| Phase 10 operational dashboard | `docs/phase10_tracer.md` | Active | Current status, decisions, risks, and next actions. |
| Evaluation config | `configs/evaluation/legal_qa_benchmark.yml` | Created | Non-secret config; final split ratio and quotas not approved. |
| Benchmark implementation | `src/evaluation/benchmark/` | Created | Schemas, loaders, validator, splitting, fingerprinting, freeze support. |
| Evaluation CLIs | `scripts/evaluation/` | Created | Thin wrappers; no Qdrant or OpenRouter calls. |
| Evaluation tests | `tests/unit/evaluation/benchmark/`, `tests/integration/evaluation/test_benchmark_workflow.py` | Created | Synthetic fixtures only. |
| Pilot dataset | `data/eval/legal_qa_benchmark/pilot/` | Draft | Pre-split, non-frozen, not held-out proof. |
| Full benchmark draft batch 1 | `data/eval/legal_qa_benchmark/*.jsonl` | Draft | 36 pre-split, non-frozen cases; structured automated review complete; no manifests. |

## Pilot Snapshot

- Query count: 19.
- Expected decisions: 17 `answer_allowed`, 2 `fallback_required`.
- Primary domains covered: 9.
- Domain counts:
  - `labor_employment_social_security`: 4;
  - `business_banking_tax`: 3;
  - `traffic_public_order_sanctions`: 3;
  - `civil_family_identity`: 2;
  - `criminal_procedure_penalty`: 2;
  - `consumer_health_education_digital_ip`: 2;
  - `administrative_government_interaction`: 1;
  - `civil_procedure_dispute_resolution`: 1;
  - `land_real_estate_construction_environment`: 1.
- Complete-evidence cases: 7.
- Blocking cases: 14.
- Regression-overlap bridge cases: 2.
- Primary review records: 19.
- Structured independent review records: 19.
- Adjudication records: 1.
- Conflict queries: 0.
- Frozen queries: 0.
- Assigned queries: 0.

## Full Benchmark Batch Snapshot

Stage E2A created the first canonical full-benchmark draft batch under
`data/eval/legal_qa_benchmark/`. It is draft data only: no query has a split,
no query is frozen, and no `split_manifest.json` or `benchmark_manifest.json`
exists.

- Query count: 36.
- Remaining gap to `minimum_viable_benchmark_size=120`: 84 cases.
- Expected decisions: 32 `answer_allowed`, 4 `fallback_required`.
- Complete-evidence cases: 10.
- Blocking/high-risk cases: 34.
- Fallback cases: 4.
- Regression-overlap cases: 0.
- Primary review records: 36.
- Structured independent review records: 36.
- Adjudication records: 0.
- Conflict queries: 0.
- Frozen queries: 0.
- Assigned queries: 0.

Domain counts:

- `business_banking_tax`: 5;
- `labor_employment_social_security`: 5;
- `land_real_estate_construction_environment`: 5;
- `civil_family_identity`: 4;
- `traffic_public_order_sanctions`: 4;
- `criminal_procedure_penalty`: 4;
- `consumer_health_education_digital_ip`: 4;
- `administrative_government_interaction`: 3;
- `civil_procedure_dispute_resolution`: 2.

Question-type counts:

- `ambiguous`: 2;
- `clause_point_lookup`: 30;
- `complete_list`: 8;
- `conditions_and_exceptions`: 3;
- `cross_law`: 1;
- `definition`: 2;
- `eligibility`: 8;
- `fallback`: 4;
- `lexical_mismatch`: 12;
- `multi_evidence`: 9;
- `near_duplicate_provision`: 2;
- `paraphrase`: 34;
- `procedure`: 6;
- `rights_and_obligations`: 16;
- `sanction_or_penalty`: 6;
- `single_article_lookup`: 24.

## Stage E1 Construction Plan

### Corpus Planning Inventory

Read-only inventory was derived from
`configs/laws/corpus_registry.yml` and `data/processed/legal_chunks.jsonl`.
The corpus contains 52 registered laws and 40,389 processed chunks. The
processed chunks expose `law_id`, `law_name`, article/clause/point hierarchy,
chunk text, parent text, citations, source URL, hashes, and warnings. The
sampled chunk schema does not expose effective or expiry date fields, so
temporal/version-sensitive cases are excluded from the initial frozen
benchmark unless defensible temporal metadata is added through reviewed
annotation.

Registered corpus groups and chunk counts:

| Registry group | Laws | Chunks | Planning use |
| --- | ---: | ---: | --- |
| Bộ luật cốt lõi | 6 | 11,725 | Core civil, criminal, labor, procedure, and maritime coverage. |
| Kinh tế, Doanh nghiệp, Ngân hàng & Thuế | 10 | 7,165 | Business, banking, tax, bankruptcy, investment, and commerce. |
| Đất đai, BĐS, Xây dựng & Môi trường | 6 | 6,882 | Land, housing, real estate, construction, environment, notarization. |
| Tiêu dùng, Y tế, Giáo dục & Công nghệ số | 7 | 4,056 | IP, health, consumer, education, cybersecurity, e-transactions, food safety. |
| Tổ chức bộ máy Nhà nước & Tố tụng Hành chính | 6 | 3,692 | State organization and administrative procedure. |
| Giao thông, Trật tự & Xử phạt | 4 | 2,275 | Road traffic, roads, administrative sanctions, alcohol harm prevention. |
| Lao động, Việc làm & An sinh xã hội | 4 | 2,011 | Labor, employment, social insurance, health insurance, labor safety. |
| Dân sự, Gia đình & Nhân thân | 5 | 1,480 | Marriage, identity, residence, civil status, military service. |
| Khiếu nại, Tố cáo & Tương tác chính quyền | 3 | 813 | Complaints, denunciations, access to information. |
| Hiến pháp | 1 | 290 | Constitutional rights and state authority. |

Point-rich laws suitable for clause/point lookup and complete-list stress
include `BLHS_VBHN`, `LDD_VBHN`, `BLTTHS_VBHN`, `LBVMT_VBHN`, `LDN_VBHN`,
`BLTTDS_VBHN`, `LTCTD_VBHN`, `LNO_VBHN`, `LXD_VBHN`, `LSHTT_VBHN`,
`LKBCB_VBHN`, `LTTHC`, `LQLT_VBHN`, `LTATGT_VBHN`, and `LDT_VBHN`.

### Benchmark Size Proposal

| Size tier | Proposed count | Purpose |
| --- | ---: | --- |
| `minimum_viable_benchmark_size` | 120 cases | Covers every approved domain except temporal if unsupported, all major question types, and enough high-risk/fallback cases to validate the pipeline. |
| `preferred_benchmark_size` | 180 cases | Supports a 70/30 development/held-out split with meaningful domain and question-type diagnostics while remaining reviewable. |
| `maximum_initial_benchmark_size` | 240 cases | Upper bound before Stage F, used only if annotation and qualified-review capacity are available. |

`development_ratio=0.7` remains the provisional Stage C default. It should be
reconfirmed before split freeze and adjusted only before held-out assignments
exist.

### Domain Quotas

| Domain | Minimum cases | Preferred cases | High-risk share | Candidate laws | Reason |
| --- | ---: | ---: | --- | --- | --- |
| `constitutional_state_rights` | 6 | 8 | Low to medium | `HP_2013` | Ensures constitutional rights and state-structure coverage. |
| `civil_family_identity` | 12 | 16 | Medium | `BLDS_2015`, `LHNGD_VBHN`, `LCC_VBHN`, `LCT_VBHN`, `LHT_2014`, `LNVQS_VBHN` | Covers identity, marriage/family, residence, civil status, and civil rights. |
| `criminal_procedure_penalty` | 14 | 22 | High | `BLHS_VBHN`, `BLTTHS_VBHN` | Required for criminal liability, penalties, and criminal procedure. |
| `civil_procedure_dispute_resolution` | 8 | 12 | Medium | `BLTTDS_VBHN` | Covers civil procedure and dispute workflows. |
| `land_real_estate_construction_environment` | 14 | 22 | Medium to high | `LDD_VBHN`, `LNO_VBHN`, `LXD_VBHN`, `LKDBDS_VBHN`, `LBVMT_VBHN`, `LCCONGCHUNG_VBHN` | High-volume property, construction, environment, and notarization issues. |
| `business_banking_tax` | 16 | 24 | Medium to high | `LDN_VBHN`, `LTCTD_VBHN`, `LQLT_VBHN`, `LTM_VBHN`, `LDT_VBHN`, `LPS_VBHN`, `LCT_2018`, tax laws | Broad business and obligation coverage with many point-level provisions. |
| `traffic_public_order_sanctions` | 12 | 18 | High | `LTATGT_VBHN`, `LDB_VBHN`, `LXLVPHC_VBHN`, `LPCTRB_2019` | Traffic and sanction boundaries are safety-sensitive and common. |
| `labor_employment_social_security` | 14 | 20 | Medium to high | `BLLD_VBHN`, `LBHXH_VBHN`, `LBHYT_VBHN`, `LATVSLD_VBHN`, `LVL_2025` | Labor, employment, insurance, and benefit questions require complete conditions. |
| `consumer_health_education_digital_ip` | 14 | 20 | Medium to high | `LSHTT_VBHN`, `LKBCB_VBHN`, `LBVQLNTD_VBHN`, `LANM_2025`, `LGD_VBHN`, `LATTP_VBHN`, `LGDDT_VBHN` | Exercises health, education, consumer, IP, food safety, and digital rules. |
| `administrative_government_interaction` | 8 | 12 | Medium | `LKN`, `LTC`, `LTCTT`, `LTTHC` | Covers complaint, denunciation, information access, and administrative interaction. |
| `maritime_transport` | 2 | 6 | Medium | `BLHH_VBHN` | Keeps specialized transport represented without over-weighting a niche domain. |

### Question-Type Quotas

Question types are multi-valued, so counts intentionally exceed total case
count.

| Question type | Minimum cases | Preferred cases | Required review assurance | Reason |
| --- | ---: | ---: | --- | --- |
| `single_article_lookup` | 30 | 45 | Structured review; qualified review if high-risk | Basic retrieval and citation anchor coverage. |
| `clause_point_lookup` | 50 | 75 | Structured review; qualified review if high-risk | Tests hierarchy precision and point-level retrieval. |
| `complete_list` | 20 | 30 | Structured review plus qualified review for held-out high-risk complete legal conditions | Completeness is a known baseline risk. |
| `conditions_and_exceptions` | 18 | 28 | Structured review; qualified review if high-risk | Prevents too-broad answers that omit exclusions. |
| `multi_evidence` | 25 | 40 | Structured review; qualified review for cross-law/high-risk held-out | Tests evidence-group coverage beyond one chunk. |
| `cross_law` | 8 | 14 | Qualified review before held-out use | Requires careful legal interaction review. |
| `definition` | 12 | 18 | Structured review | Covers defined-term lookup and lexical matching. |
| `procedure` | 16 | 24 | Qualified review before held-out use when deadlines or rights are affected | Procedure and deadline errors can be material. |
| `eligibility` | 18 | 28 | Qualified review before high-risk held-out use | Eligibility errors materially affect rights and obligations. |
| `rights_and_obligations` | 30 | 45 | Structured review; qualified review if high-risk | Core legal QA category across domains. |
| `sanction_or_penalty` | 18 | 30 | Qualified review before held-out use | Penalty errors are high-risk. |
| `fallback` | 18 | 28 | Structured review; qualified review for high-risk held-out fallback safety | Tests refusal and no-LLM fallback behavior. |
| `ambiguous` | 8 | 14 | Structured review; qualified review if high-risk | Tests unsafe ambiguity handling. |
| `near_duplicate_provision` | 8 | 12 | Structured review | Exercises confusing sibling provisions. |
| `lexical_mismatch` | 30 | 45 | Structured review | Tests semantic retrieval beyond exact wording. |
| `paraphrase` | 50 | 75 | Structured review | Ensures natural Vietnamese query coverage. |
| `temporal_version_sensitive` | 0 initial frozen | 0 initial frozen | Qualified review if later included | Excluded from initial frozen benchmark until temporal metadata is defensible. |

### Case Eligibility Tiers

| Tier | Criteria | Split eligibility |
| --- | --- | --- |
| `dev_eligible` | Complete schema records, direct qrels where required, primary + structured independent review, material conflicts adjudicated, corpus-aware validation passes. | May enter `development`. |
| `held_out_eligible` | Satisfies `dev_eligible`, no regression overlap, no unresolved conflict, complete grouping metadata, no leakage risk, and high-risk review gate satisfied. | May enter `held_out_test`. |
| `development_only` | Useful for diagnostics, bridge coverage, pilot continuity, temporal exploration, or unresolved qualified-review capacity limits. | Must stay in `development` or remain outside frozen scoring. |
| `excluded` | Unsupported expectation, unsafe temporal scope, unresolved conflict, duplicate without purpose, missing direct qrels for `answer_allowed`, or failed validation. | Must not enter scored benchmark. |

### Pilot Reuse Policy

The 19 pilot cases remain draft and pre-split. They should be used primarily
as seed patterns and validator/protocol examples. A pilot case may be promoted
later only after the full benchmark review workflow confirms it under the
same schema contract and applies the eligibility rules above.

`pilot_0001` and `pilot_0018` have declared regression overlap and are
permanently ineligible for `held_out_test`. High-risk pilot cases require
qualified human legal review before held-out use; without that review they
remain `development_only` or seed patterns.

### Full Benchmark File Layout

Canonical full benchmark files will live at:

```text
data/eval/legal_qa_benchmark/benchmark_queries.jsonl
data/eval/legal_qa_benchmark/benchmark_targets.jsonl
data/eval/legal_qa_benchmark/benchmark_qrels.jsonl
data/eval/legal_qa_benchmark/evidence_groups.jsonl
data/eval/legal_qa_benchmark/review_records.jsonl
data/eval/legal_qa_benchmark/split_manifest.json
data/eval/legal_qa_benchmark/benchmark_manifest.json
```

Stage E2A created the five canonical draft JSONL files and added narrow
`.gitignore` exceptions for those JSONL files only. `split_manifest.json` and
`benchmark_manifest.json` remain uncreated and ignored until a later split and
freeze task explicitly scopes them.

### Split Strategy

- Use `development` and `held_out_test` unless learned components later
  require train/validation/test.
- Start from the provisional `development_ratio=0.7` and
  `split_seed=20260619`, then confirm before split creation.
- Group transitively by `case_family_id` and `source_provision_group_id`.
- Keep regression-overlap bridge cases out of `held_out_test`.
- Keep duplicate, near-duplicate, paraphrase-family, and source-provision
  groups in one split.
- Require high-risk held-out qualified review before assignment; otherwise
  force to development or exclude.
- Validate minimum held-out coverage by domain and question type before
  freezing.
- If a connected group is too large, keep it intact and document the coverage
  deviation rather than splitting it.
- If held-out lacks a required type, revise annotation before split freeze or
  document the approved exclusion; never tune after observing held-out system
  performance.

### Full Benchmark Review Workflow

```text
source-first annotation
-> primary annotation
-> structured independent review
-> repository-level adjudication
-> qualified human legal review for eligible high-risk held-out cases
-> schema and corpus-aware validation
-> split eligibility audit
-> grouped split
-> freeze
```

Review records must use schema `1.0` fields including `reviewer_kind`,
`review_assurance`, `review_stage`, `status`, `reviewer_id`, and
`resolution_notes`. The benchmark may be described as source-grounded,
schema-validated, corpus-aware validated, structured-review-completed, or
repository-adjudicated only when those statements are accurate. It must not
be described as expert-reviewed, lawyer-reviewed, or legally validated unless
qualified human legal review actually occurred and is recorded.

### Stage E2 Acceptance Criteria

Before split and benchmark manifests are created:

- benchmark JSONL files pass schema validation;
- corpus-aware validation has 0 errors;
- review history is complete;
- all material conflicts are resolved or excluded;
- high-risk held-out candidates have qualified human legal review or are
  excluded from held-out;
- regression-overlap cases are not in held-out;
- duplicate, paraphrase, near-duplicate, and source-provision leakage is
  prevented;
- `.gitignore` has narrow exceptions for approved canonical full benchmark
  JSONL files and manifests;
- split coverage by domain and question type is acceptable;
- raw and canonical checksums/fingerprints are recorded;
- `benchmark_version` is release-valid and not `draft`;
- pilot data remains clearly separate from frozen benchmark data.

## Review and Adjudication Snapshot

- D1 completed source-grounded primary annotation.
- D2 completed structured automated second-pass review.
- This review does not constitute qualified human legal review.
- Qualified human legal review has not been completed.
- One material disagreement was found for `pilot_0003`.
- `pilot_0003` was adjudicated by narrowing the query to ordinary overtime
  under Article 107 Clause 2 and removing `conditions_and_exceptions` from
  `question_types`.
- No unresolved conflict remains.
- No pilot case is frozen or assigned to a split.
- Detailed machine-readable review history remains in
  `data/eval/legal_qa_benchmark/pilot/review_records.jsonl`.

## Current Decisions

| Date | Decision | Rationale | Status |
| --- | --- | --- | --- |
| 2026-06-19 | Benchmark-first development | Broader reviewed benchmark and frozen splits must precede Advanced RAG comparison. | Active |
| 2026-06-19 | Preserve five-case suite as regression only | Existing suite is safety/regression, not held-out proof. | Active |
| 2026-06-19 | Keep baseline logic under `src/retrieval/` and benchmark logic under `src/evaluation/` | Prevents Phase 0-9 regression logic from being moved or weakened. | Implemented |
| 2026-06-19 | Use grouped deterministic splitting | Prevents paraphrase-family and source-provision leakage. | Implemented |
| 2026-06-19 | Do not tune on held-out test data | Held-out comparison is valid only after configurations are fixed. | Active |
| 2026-06-19 | Change retrieval only in the primary comparison | Generator, prompt, selection, fallback, corpus, and evaluation code remain fixed unless ablated. | Active |
| 2026-06-19 | Use binary final benchmark decisions | Frozen benchmark uses `answer_allowed` or `fallback_required`. | Implemented |
| 2026-06-19 | Treat direct evidence and evidence groups as legal sufficiency requirements | Supporting evidence cannot complete required groups. | Implemented |
| 2026-06-19 | Treat protocol invariants as non-configurable | Review, chunk qrels, Vietnamese diacritics, and mandatory grouping are safety rules. | Implemented |
| 2026-06-19 | Use manifest assignments and review records as sources of truth | Query split/review fields are denormalized summaries. | Implemented |
| 2026-06-20 | Keep pilot pre-split and non-frozen | Pilot validates schema/protocol only. | Implemented |
| 2026-06-20 | Use two regression bridge cases only | Bridge cases remain permanently ineligible for held-out proof. | Implemented |
| 2026-06-20 | Omit temporal pilot cases | Current chunk metadata is insufficient for defensible temporal labels. | Implemented |
| 2026-06-21 | Freeze schema contract version `1.0` | Pilot and tests exercised schema, validation, review history, and adjudication. | Approved |
| 2026-06-21 | Require qualified review or exclusion for high-risk held-out items | Structured automated review must not be confused with human legal validation. | Approved |
| 2026-06-21 | Use 120 / 180 / 240 as Stage E1 benchmark size tiers | Balances domain/type coverage with legal-review cost before Stage F. | Proposed |
| 2026-06-21 | Treat temporal cases as excluded from the initial frozen benchmark unless defensible metadata exists | Processed chunks do not expose effective/expiry metadata needed for safe temporal ground truth. | Proposed |
| 2026-06-21 | Treat pilot cases as seed patterns unless re-reviewed for full benchmark eligibility | Pilot is draft, pre-split, non-frozen, and not qualified-human-reviewed. | Proposed |
| 2026-06-21 | Preserve provisional 70/30 split only as a pre-freeze default | The ratio is implemented in config but must be confirmed before split creation. | Proposed |
| 2026-06-21 | Keep Stage E2A conflict-free cases at `independent_reviewed` without fake adjudication records | Adjudication records are only valid when a material disagreement exists. | Implemented |
| 2026-06-21 | Add narrow Git exceptions only for full benchmark JSONL files | Draft benchmark records must be tracked, while split and benchmark manifests remain later freeze artifacts. | Implemented |

## Risks and Open Questions

Confirmed risks:

- Qualified human legal review has not been completed.
- High-risk held-out items require qualified human legal review or exclusion
  from the frozen held-out split.
- Temporal/version-sensitive cases were not exercised in the pilot.
- Semantic regression overlap still requires manual review.
- Pilot over-samples blocking and high-risk cases.
- Full benchmark construction may expose schema or protocol edge cases not
  represented in the pilot.
- Stage E2A over-samples blocking/high-risk cases and does not define final
  held-out eligibility.
- Generation output can be non-deterministic even with fixed prompts and
  inputs.
- Sparse retrieval, fusion, and reranking may add latency and cost.

Open questions:

- Whether the Stage E1 proposed size tiers and quotas need adjustment after
  annotation capacity and qualified-review staffing are confirmed.
- Who will staff qualified human legal review and later adjudication?
- What benchmark versioning convention will be used?
- What numeric relevance gains should be used for nDCG?
- What exact blocking-case thresholds should gate system comparison?
- Which sparse retrieval architecture and reranker are acceptable after the
  benchmark is frozen?

## Validation Summary

Latest Stage D documentation and pilot hardening checks passed:

- corpus-aware pilot validation: 0 errors, 2 expected warnings for unsplit
  regression bridge cases;
- Python compile for benchmark modules and evaluation CLIs: passed;
- evaluation unit tests: 68 passed;
- evaluation integration tests: 1 passed;
- retrieval unit regression tests: 173 passed;
- Ruff lint and format check: passed;
- `uv lock --check`: passed;
- `git diff --check`: passed;
- pilot record counts: 19 queries, 47 targets, 47 qrels, 39 evidence groups,
  39 review records;
- manifest absence check: no split or benchmark manifest exists;
- protected-path status check: no protected corpus path, regression asset, or
  quality-gate config changes.

Latest Stage E1 planning documentation checks passed:

- `git diff --check`: passed;
- removed-document reference search: no active references;
- heading inventory: completed for `docs/evaluation.md`,
  `docs/phase10_tracer.md`, and the pilot README;
- `.gitignore` audit: Stage E2 must keep full benchmark JSONL exceptions
  narrow and leave canonical manifests separately scoped;
- changed files are documentation only.

Latest Stage E2A draft-batch checks passed:

- full-benchmark corpus-aware validation: 0 errors, 0 warnings;
- review-history audit: 36 queries, 36 primary review records, 36 structured
  independent review records, 0 adjudication records, 0 conflicts, 0 frozen
  queries, 0 assigned queries;
- draft record counts: 36 queries, 61 targets, 61 qrels, 55 evidence groups,
  72 review records;
- Python compile for benchmark modules and evaluation CLIs: passed;
- evaluation unit tests: 68 passed;
- evaluation integration tests: 1 passed;
- retrieval unit regression tests: 173 passed;
- Ruff lint and format check: passed;
- `uv lock --check`: passed;
- removed-document reference search: no active references;
- `git diff --check`: passed.

## Change Log

| Date | Change |
| --- | --- |
| 2026-06-19 | Created Phase 10 progress tracer after repository inspection. |
| 2026-06-19 | Defined durable evaluation protocol. |
| 2026-06-19 | Implemented benchmark schemas, loaders, validator, grouped splitting, fingerprinting, CLI wrappers, tests, config, and technical docs. |
| 2026-06-19 | Hardened protocol invariants, split/review sources of truth, fingerprints, qrel/group consistency, and freeze immutability. |
| 2026-06-20 | Created and hardened 19-case draft pilot annotation. |
| 2026-06-20 | Completed structured D2 review and adjudicated the `pilot_0003` scope conflict. |
| 2026-06-21 | Added review-assurance metadata and froze schema contract version `1.0`. |
| 2026-06-21 | Hardened D2 assurance wording and high-risk held-out review policy. |
| 2026-06-21 | Consolidated evaluation documentation into the current canonical structure. |
| 2026-06-21 | Added Stage E1 full benchmark construction planning, quota proposal, eligibility tiers, split strategy, and Stage E2 acceptance criteria. |
| 2026-06-21 | Created the first 36-case full-benchmark draft batch with primary annotation, structured automated review, and corpus-aware validation. |

## Exit Criteria

Phase 10 can close only after:

- broader legally reviewed benchmark completed;
- deterministic development/test split frozen;
- held-out test protected from tuning;
- benchmark and baseline manifests fingerprinted;
- frozen Naive RAG baseline recorded;
- dense, hybrid, and reranking variants evaluated as controlled comparisons;
- retrieval, safety, generation, and operational metrics reported;
- unsupported claims do not increase beyond accepted policy;
- blocking cases meet the approved gate;
- wins, losses, regressions, latency, and cost are documented;
- justified adoption or rejection decision is recorded;
- durable documentation is consolidated;
- this tracer is removed or archived.

## Next Immediate Action

```text
Stage E2B full-benchmark draft batch construction
-> coverage gap closure toward the 120-case minimum
-> annotation workload and qualified-review allocation
-> grouped split and leakage validation
-> split and benchmark manifest freeze
```

Sparse retrieval, RRF, and reranking must not begin yet.
