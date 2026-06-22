# Phase 10 Progress Tracer

## Purpose and Authority

This document is the active operational dashboard for Phase 10 benchmark-first
Advanced RAG evaluation work. It tracks current progress, decisions, risks,
deliverables, benchmark release status, and next actions.

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
  Stage E1 full benchmark construction planning is complete. Stage E2A,
  E2B-1, and E2B-2 created the 120-case minimum viable full-benchmark draft.
- Stage E final result: scoped benchmark release `v0.1.0` is frozen. The
  frozen dataset contains 128 cases, 85 `development` cases, and 43
  `held_out_test` cases. The held-out scope is low/medium-risk eligible cases
  only; high-risk cases without qualified human legal review remain
  development-only.
- Stage F1: frozen dense retrieval-only baseline is complete for benchmark
  `v0.1.0`.
- Stage F2: frozen Naive RAG generation baseline is complete for benchmark
  `v0.1.0`, using frozen F1 retrieval artifacts and the current Naive RAG
  pipeline without fallback/evidence-gate relaxation.
- Not done: qualified human legal review for high-risk held-out expansion,
  sparse retrieval, fusion, reranking, GraphRAG, API, UI, and fine-tuning.

## Canonical Document Map

| Topic | Canonical source | Purpose | Status |
| --- | --- | --- | --- |
| Repository rules | `AGENTS.md` | Safety, workflow, protected paths, naming, validation | Active |
| Current project state | `PROJECT_CONTEXT.md` | Current architecture, baseline status, roadmap | Active |
| Naive RAG | `docs/naive_rag.md` | Baseline implementation and quality gate reference | Active |
| Evaluation protocol and implementation | `docs/evaluation.md` | Durable benchmark rules, schemas, validation, split, freeze, review policy, CLI, metrics contract | Active |
| Advanced RAG design | `docs/advanced_rag.md` | Future hybrid/fusion/reranking design reference | Active |
| Frozen benchmark data | `data/eval/legal_qa_benchmark/*.jsonl` | Active scoped `v0.1.0` benchmark records and review history | Active |
| Split and benchmark manifests | `data/eval/legal_qa_benchmark/split_manifest.json`, `data/eval/legal_qa_benchmark/benchmark_manifest.json` | Frozen split assignments, checksums, and release metadata | Active |

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
| Stage E - Full Benchmark and Split Freeze | Complete for scoped `v0.1.0` | Stage E1 planning, E2 construction, E-Repair, scoped split, and freeze are complete. `held_out_test` contains low/medium-risk eligible cases only; high-risk sanction/criminal held-out coverage is deferred pending qualified human legal review. |
| Stage F - Frozen Naive RAG Baseline | In progress | Stage F1 dense retrieval-only baseline and Stage F2 frozen Naive RAG generation baseline are complete on frozen development and held-out splits. Regression-suite and quality-gate reruns remain pending. |
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
- [x] second full-benchmark draft batch;
- [x] cumulative full-benchmark corpus-aware validation;
- [x] final draft construction to the 120-case minimum;
- [x] duplicate and near-duplicate audit;
- [x] paraphrase-family and source-provision grouping audit;
- [x] targeted held-out eligibility repair batch;
- [x] high-risk held-out human-review allocation packet;
- [x] deterministic development/test split for scoped `v0.1.0`;
- [x] final split leakage validation;
- [x] test freeze;
- [x] checksums;
- [x] benchmark manifest.

### Stage F - Frozen Naive RAG Baseline

- [x] frozen dense retrieval baseline run;
- [x] development retrieval metrics;
- [x] held-out retrieval metrics;
- [x] retrieval run manifest;
- [x] runtime parameter capture;
- [x] retrieval result validation;
- [x] frozen Naive RAG generation baseline;
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
| Full benchmark release | `data/eval/legal_qa_benchmark/` | Frozen scoped `v0.1.0` | 128 frozen records, 85 development cases, 43 low/medium-risk held-out cases, split and benchmark manifests created. |
| Dense retrieval baseline artifacts | `artifacts/reports/evaluation/naive_rag_baseline/retrieval/` | Created | Runtime artifacts for Stage F1 retrieval-only baseline; not benchmark source data. |

## Historical Pilot Note

Stage D produced a 19-case pilot to exercise the schema, validation, structured
automated review, and repository-level adjudication workflow. That pilot is no
longer an active repository asset after the scoped `v0.1.0` freeze. Historical
details remain available in Git history.

## Full Benchmark Draft Snapshot

Stage E2A, E2B-1, E2B-2, E-Repair, and the final scoped freeze created the
current canonical full benchmark under `data/eval/legal_qa_benchmark/`.
Benchmark release `v0.1.0` is frozen with a scoped held-out split.

- Query count: 128.
- Remaining gap to `minimum_viable_benchmark_size=120`: 0 cases.
- Expected decisions: 110 `answer_allowed`, 18 `fallback_required`.
- Complete-evidence cases: 28.
- Blocking/high-risk cases: 80.
- Low/medium-risk cases: 48.
- Fallback cases: 18.
- Regression-overlap cases: 0.
- Primary review records: 128.
- Structured independent review records: 128.
- Adjudication records: 0.
- Conflict queries: 0.
- Frozen queries: 128.
- Assigned queries: 128.
- Development split: 85 cases.
- Held-out split: 43 cases.
- Held-out high-risk cases: 0.
- Benchmark version: `v0.1.0`.
- Split manifest: `data/eval/legal_qa_benchmark/split_manifest.json`.
- Benchmark manifest: `data/eval/legal_qa_benchmark/benchmark_manifest.json`.

Domain counts:

- `consumer_health_education_digital_ip`: 16;
- `business_banking_tax`: 14;
- `labor_employment_social_security`: 14;
- `land_real_estate_construction_environment`: 14;
- `civil_family_identity`: 14;
- `traffic_public_order_sanctions`: 13;
- `administrative_government_interaction`: 11;
- `civil_procedure_dispute_resolution`: 11;
- `criminal_procedure_penalty`: 9;
- `constitutional_state_rights`: 7;
- `maritime_transport`: 5.

Question-type counts:

- `ambiguous`: 14;
- `clause_point_lookup`: 100;
- `complete_list`: 23;
- `conditions_and_exceptions`: 19;
- `cross_law`: 4;
- `definition`: 17;
- `eligibility`: 16;
- `fallback`: 18;
- `lexical_mismatch`: 38;
- `multi_evidence`: 26;
- `near_duplicate_provision`: 8;
- `paraphrase`: 125;
- `procedure`: 36;
- `rights_and_obligations`: 67;
- `sanction_or_penalty`: 15;
- `single_article_lookup`: 64;
- `temporal_version_sensitive`: 0.

### Scoped `v0.1.0` Held-Out Eligibility

The repair batch added eight low/medium-risk draft cases:

```text
bench_0121
bench_0122
bench_0123
bench_0124
bench_0125
bench_0126
bench_0127
bench_0128
```

Repair focus:

- additional `maritime_transport` coverage;
- one low/medium-risk fallback boundary;
- additional `definition`, `procedure`, `complete_list`, and
  `rights_and_obligations` coverage;
- no qualified human legal-review record was added;
- no high-risk case was downgraded to force split eligibility.

Final scoped held-out eligibility audit:

- query-level held-out eligible candidates: 48;
- grouped held-out eligible candidates after transitive grouping: 43;
- development-only cases due high-risk without qualified human legal review:
  80;
- excluded cases: 0;
- exact normalized duplicate queries: 0;
- exact regression overlaps: 0;
- exact pilot overlaps: 0;
- transitive grouping components: 116;
- final held-out assignment: 43 grouped low/medium-risk cases;
- final development assignment: 85 cases.

Grouped held-out-eligible coverage now includes:

- expected decisions: 42 `answer_allowed`, 1 `fallback_required`;
- domains: `business_banking_tax`, `traffic_public_order_sanctions`,
  `constitutional_state_rights`, `civil_family_identity`,
  `civil_procedure_dispute_resolution`,
  `administrative_government_interaction`,
  `consumer_health_education_digital_ip`,
  `land_real_estate_construction_environment`,
  `labor_employment_social_security`, and `maritime_transport`;
- question types: `single_article_lookup`, `clause_point_lookup`,
  `definition`, `lexical_mismatch`, `complete_list`, `paraphrase`,
  `multi_evidence`, `rights_and_obligations`, `procedure`, `cross_law`,
  `conditions_and_exceptions`, `eligibility`, and `fallback`.

Known scoped `v0.1.0` limitations:

- high-risk sanction, penalty, fallback-safety, criminal, and some eligibility
  cases still need qualified human legal review before future held-out use;
- `v0.1.0` held-out results must not be used to validate performance on
  high-risk sanction, penalty, or criminal legal QA;
- no qualified human legal review has been completed;
- temporal/version-sensitive held-out coverage remains excluded.

### High-Risk Human Review Allocation Packet

The following cases are priority candidates if high-risk held-out coverage is
required. Current assurance for all listed cases is structured automated
review only; qualified human legal review has not been completed.

| Query ID | Domain | Coverage need | High-risk reason | Reviewer must verify |
| --- | --- | --- | --- | --- |
| `bench_0120` | `criminal_procedure_penalty` | fallback, sanction/penalty, criminal coverage | fact-specific criminal penalty fallback safety | Whether fallback is required and whether no direct penalty answer is safe without offense facts. |
| `bench_0023` | `traffic_public_order_sanctions` | fallback and traffic sanction coverage | exact fine amount absent from corpus | Whether incomplete-evidence fallback is correct and no decree-level fine is directly available. |
| `bench_0089` | `traffic_public_order_sanctions` | fallback and traffic sanction coverage | exact sidewalk-stop fine amount absent from corpus | Whether supporting sanction provisions remain non-direct and fallback is required. |
| `bench_0024` | `criminal_procedure_penalty` | criminal eligibility and penalty-scope coverage | juvenile criminal-liability scope | Whether the age and offense-scope conditions are complete and directly cited. |
| `bench_0078` | `criminal_procedure_penalty` | criminal procedure fallback coverage | case-specific investigation deadline conclusion | Whether unsafe ambiguity and conditions/exceptions are properly handled. |
| `bench_0022` | `traffic_public_order_sanctions` | complete-list sanction coverage | omission of sanction forms changes legal meaning | Whether all in-scope sanction forms are complete and correctly grouped. |
| `bench_0025` | `criminal_procedure_penalty` | criminal mitigation coverage | penalty consequence and mitigation scope | Whether the mitigation provision is direct and not over-broad. |
| `bench_0026` | `criminal_procedure_penalty` | near-duplicate criminal penalty coverage | theft aggravation/condition risk | Whether the queried condition is exact and near-miss provisions are not treated as alternatives. |
| `bench_0040` | `civil_family_identity` | fallback sanction boundary | exact identity-card loss fine absent from corpus | Whether fallback is required and no sanction amount is directly available. |
| `bench_0075` | `criminal_procedure_penalty` | criminal responsibility coverage | intoxication and liability consequence | Whether the provision supports the answer scope without broader criminal-law interpretation. |
| `bench_0076` | `criminal_procedure_penalty` | aggravating-circumstance coverage | criminal penalty consequence | Whether the target provision is direct and hierarchy depth is correct. |
| `bench_0087` | `traffic_public_order_sanctions` | complete-list sanction coverage | administrative sanction list completeness | Whether the evidence groups fully cover the in-scope list and avoid duplicate leakage. |
| `bench_0102` | `consumer_health_education_digital_ip` | fallback sanction/digital safety coverage | AI/personal-data penalty source gap | Whether fallback is required and whether the question is too broad for corpus-only answer. |
| `bench_0088` | `traffic_public_order_sanctions` | rights/procedure in sanction context | burden-of-proof and sanction-process consequence | Whether the rights/procedure claim is complete and directly grounded. |

## Frozen Dense Retrieval Baseline Snapshot

Stage F1 ran the current dense retrieval stack against frozen benchmark
release `v0.1.0`. This was retrieval-only: no answer generation, LLM call,
sparse retrieval, fusion, reranking, or query rewriting was used.

Runtime identity:

- retrieval type: dense;
- embedding model: `BAAI/bge-m3`;
- Qdrant collection: `vnlaw_chunks_bgem3_v1_full`;
- vector name: `dense`;
- distance: cosine;
- collection points: 40,389;
- top-k: 10;
- artifact directory:
  `artifacts/reports/evaluation/naive_rag_baseline/retrieval/`.

Headline metrics:

| Split | Queries | Recall@10 | MRR@10 | NDCG@10 | Required direct coverage@10 | Evidence group coverage@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `all` | 128 | 0.845 | 0.657 | 0.610 | 0.569 | 0.569 |
| `development` | 85 | 0.794 | 0.583 | 0.524 | 0.504 | 0.504 |
| `held_out_test` | 43 | 0.929 | 0.777 | 0.779 | 0.705 | 0.705 |

Fallback diagnostics:

- `all`: 18 fallback cases, near-miss@10 = 0, supporting@10 = 4,
  direct-evidence@10 = 0;
- `development`: 17 fallback cases, near-miss@10 = 0, supporting@10 = 4,
  direct-evidence@10 = 0;
- `held_out_test`: 1 fallback case, near-miss@10 = 0, supporting@10 = 0,
  direct-evidence@10 = 0.

Weakest answer-allowed direct-recall breakdowns:

- domains: `labor_employment_social_security` (Recall@10 0.727),
  `business_banking_tax` (0.750),
  `land_real_estate_construction_environment` (0.750),
  `civil_procedure_dispute_resolution` (0.818),
  `traffic_public_order_sanctions` (0.818);
- question types: `complete_list` (Recall@10 0.591),
  `near_duplicate_provision` (0.625), `multi_evidence` (0.654),
  `sanction_or_penalty` (0.700), `eligibility` (0.800).

Known Stage F1 limitations:

- retrieval-only metrics do not measure legal answer quality;
- no generation, fallback answer behavior, or citation wording was evaluated;
- no sparse retrieval, RRF, reranking, fusion, or query rewriting was used;
- `held_out_test` remains scoped to low/medium-risk v0.1 cases only;
- qualified human legal review has not occurred.

## Frozen Naive RAG Generation Baseline Snapshot

Stage F2 ran the current Naive RAG generation pipeline against frozen
benchmark release `v0.1.0`, reusing the frozen dense retrieval results from
Stage F1. This was a baseline run only: no fallback/evidence gate was relaxed,
no prompt or selector tuning was applied, and no sparse retrieval, fusion,
reranking, query rewriting, or Advanced RAG behavior was introduced.

Runtime identity:

- LLM provider/model: `openrouter` / `google/gemini-2.5-flash`;
- generation temperature: 0.0;
- max tokens: 1024;
- retrieval input:
  `artifacts/reports/evaluation/naive_rag_baseline/retrieval/case_results.jsonl`;
- artifact directory:
  `artifacts/reports/evaluation/naive_rag_baseline/generation/`;
- generated case results: 128;
- generation errors: 0.

Headline metrics:

| Split | Queries | Decision accuracy | Answer-allowed answer rate | Fallback-required fallback rate | Citation ID validity | Evidence group coverage | Missing required evidence rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `all` | 128 | 0.430 | 0.391 | 0.667 | 1.000 | 0.357 | 0.673 |
| `development` | 85 | 0.529 | 0.500 | 0.647 | 1.000 | 0.452 | 0.588 |
| `held_out_test` | 43 | 0.233 | 0.214 | 1.000 | 1.000 | 0.202 | 0.810 |

Case status:

- pass: 48;
- partial: 7;
- fail: 73.

Fallback and citation behavior:

- Pipeline fallback count: 79 total, 45 development, 34 held-out.
- Fallbacks were produced without LLM calls and without citations.
- Citation ID validity for answered cases was 1.000.
- Unsupported or uncited claim checking in this run is citation-ID-guard only,
  not semantic claim-level faithfulness review.

Weakest generation breakdowns:

- domains with lowest decision accuracy or evidence-group coverage:
  `maritime_transport`, `business_banking_tax`,
  `traffic_public_order_sanctions`, `constitutional_state_rights`, and
  `labor_employment_social_security`;
- question types with weakest evidence coverage or highest missing-evidence
  rates: `complete_list`, `multi_evidence`, `lexical_mismatch`,
  `conditions_and_exceptions`, and `definition`;
- expected `answer_allowed` cases are the main failure source: many retrieved
  cases still fall back because strict selected-evidence coverage does not
  satisfy required evidence groups.

Known Stage F2 limitations:

- Naive RAG baseline only;
- uses frozen dense retrieval results from F1;
- no hybrid retrieval, sparse retrieval, fusion, reranking, or query rewriting;
- `held_out_test` excludes high-risk sanction/criminal QA;
- qualified human legal review has not occurred;
- unsupported claim check is citation-ID-guard only, not full semantic
  faithfulness review;
- LLM output may be nondeterministic despite temperature 0;
- fallback/evidence gate was intentionally not relaxed in this baseline.

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
| `development_only` | Useful for diagnostics, bridge coverage, temporal exploration, or unresolved qualified-review capacity limits. | Must stay in `development` or remain outside frozen scoring. |
| `excluded` | Unsupported expectation, unsafe temporal scope, unresolved conflict, duplicate without purpose, missing direct qrels for `answer_allowed`, or failed validation. | Must not enter scored benchmark. |

### Historical Pilot Reuse Policy

The pilot is historical only. It must not be used as active benchmark data. Any
future case inspired by the pilot must be reconstructed from source-first
inspection, assigned a new benchmark ID, reviewed under the full benchmark
workflow, and evaluated under the current eligibility rules.

### Full Benchmark File Layout

Canonical full benchmark files live at:

```text
data/eval/legal_qa_benchmark/benchmark_queries.jsonl
data/eval/legal_qa_benchmark/benchmark_targets.jsonl
data/eval/legal_qa_benchmark/benchmark_qrels.jsonl
data/eval/legal_qa_benchmark/evidence_groups.jsonl
data/eval/legal_qa_benchmark/review_records.jsonl
data/eval/legal_qa_benchmark/split_manifest.json
data/eval/legal_qa_benchmark/benchmark_manifest.json
```

The scoped `v0.1.0` freeze created the active JSONL records, split manifest,
and benchmark manifest. `.gitignore` keeps narrow exceptions for these
canonical files only.

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
- obsolete pilot data has been removed or clearly marked historical.

## Review and Adjudication Snapshot

- D1 completed source-grounded primary annotation.
- D2 completed structured automated second-pass review.
- This review does not constitute qualified human legal review.
- Qualified human legal review has not been completed.
- One material scope disagreement was found during the historical pilot
  review and was resolved through repository-level adjudication.
- No unresolved conflict remains.
- The active benchmark review history is stored in
  `data/eval/legal_qa_benchmark/review_records.jsonl`.

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
| 2026-06-21 | Keep Stage E2B-1 conflict-free cases at `independent_reviewed` without fake adjudication records | No material disagreements were recorded, so adjudication records would create false review history. | Implemented |
| 2026-06-21 | Keep `temporal_version_sensitive` coverage at 0 for E2B-1 | Current processed chunks still lack defensible temporal metadata for safe temporal ground truth. | Implemented |
| 2026-06-21 | Keep Stage E2B-2 conflict-free cases at `independent_reviewed` without fake adjudication records | No material disagreements were recorded, so adjudication records would create false review history. | Implemented |
| 2026-06-21 | Treat the 120-case dataset as a minimum viable draft, not a frozen benchmark | Grouping, leakage review, qualified-review allocation, split creation, and manifests are still pending. | Implemented |
| 2026-06-21 | Keep `temporal_version_sensitive` coverage at 0 for E2B-2 | Current processed chunks still lack defensible temporal metadata for safe temporal ground truth. | Implemented |
| 2026-06-21 | Block split and freeze after Stage E-Final audit | Held-out candidate pool has 35 grouped eligible low/medium-risk cases and lacks fallback, sanction/penalty, criminal-procedure, and maritime coverage because high-risk cases have no qualified human legal review. | Implemented |
| 2026-06-21 | Use targeted low/medium-risk repair instead of downgrading high-risk cases | Held-out eligibility can be improved safely with additional source-grounded definition, procedure, maritime, and fallback cases; high-risk sanction/criminal cases still require qualified human review before held-out use. | Implemented |
| 2026-06-21 | Do not create split or manifests after E-Repair | Although grouped held-out eligibility improved to 43 candidates, `benchmark_version` remains `draft` and high-risk held-out allocation still requires qualified human review decisions. | Implemented |
| 2026-06-21 | Freeze scoped `v0.1.0` with low/medium-risk held-out only | A safe held-out split is available when all high-risk cases without qualified human legal review are development-only and sanction/criminal held-out coverage is explicitly deferred. | Implemented |
| 2026-06-21 | Defer high-risk sanction/criminal held-out claims | `v0.1.0` must not be described as validating high-risk sanction, penalty, or criminal legal QA. | Active |

## Risks and Open Questions

Confirmed risks:

- Qualified human legal review has not been completed.
- High-risk held-out items require qualified human legal review or exclusion
  from the frozen held-out split.
- Temporal/version-sensitive cases are not included in the scoped `v0.1.0`
  held-out split.
- Semantic regression overlap still requires manual review.
- The active benchmark has high blocking/high-risk density in development
  (80 of 128 cases), though the held-out split contains only low/medium-risk
  eligible cases.
- `v0.1.0` has a valid held-out split, but the held-out split intentionally
  contains low/medium-risk cases only.
- `v0.1.0` held-out excludes high-risk sanction/penalty and criminal-procedure
  coverage unless qualified human legal review is completed in a future
  release.
- `cross_law`, `definition`, `eligibility`, `sanction_or_penalty`,
  `maritime_transport`, and `temporal_version_sensitive` coverage remain
  below preferred quotas and need explicit split/freeze review.
- Future benchmark releases need an explicit version decision and should not
  overwrite `v0.1.0` manifests.
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

Historical Stage D pilot hardening checks passed before pilot removal:

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
- heading inventory: completed for `docs/evaluation.md` and
  `docs/phase10_tracer.md`;
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

Latest Stage E2B-1 draft-batch checks passed:

- full-benchmark corpus-aware validation: 0 errors, 0 warnings;
- review-history audit: 78 queries, 78 primary review records, 78 structured
  independent review records, 0 adjudication records, 0 conflicts, 0 frozen
  queries, 0 assigned queries;
- draft record counts: 78 queries, 124 targets, 124 qrels, 112 evidence
  groups, 156 review records;
- manifest absence check: no split or benchmark manifest exists;
- no held-out assignments and no frozen records;
- Python compile for benchmark modules and evaluation CLIs: passed;
- evaluation unit tests: 68 passed;
- evaluation integration tests: 1 passed;
- retrieval unit regression tests: 173 passed;
- Ruff lint and format check: passed;
- `uv lock --check`: passed;
- removed-document reference search: no active references;
- `git diff --check`: passed.

Latest Stage E2B-2 draft-batch checks passed:

- full-benchmark corpus-aware validation: 0 errors, 0 warnings;
- review-history audit: 120 queries, 120 primary review records, 120
  structured independent review records, 0 adjudication records, 0 conflicts,
  0 frozen queries, 0 assigned queries;
- draft record counts: 120 queries, 200 targets, 200 qrels, 181 evidence
  groups, 240 review records;
- remaining gap to `minimum_viable_benchmark_size=120`: 0 cases;
- manifest absence check: no split or benchmark manifest exists;
- no held-out assignments and no frozen records.

Latest Stage E-Final pre-freeze audit:

- full-benchmark corpus-aware validation: 0 errors, 0 warnings;
- normalized duplicate query audit: 0 duplicates;
- exact regression-overlap audit: 0 matches;
- exact pilot-overlap audit: 0 matches;
- transitive grouping components: 108;
- query-level held-out candidates without qualified human review: 40;
- grouped held-out-eligible candidates: 35;
- development-only cases due high-risk without qualified human review: 80;
- excluded-from-freeze cases: 0;
- result: split/freeze gate did not pass; no split or manifests were created.

Latest Stage E-Repair audit:

- repair batch added: 8 low/medium-risk draft cases;
- full-benchmark corpus-aware validation: 0 errors, 0 warnings;
- draft record counts: 128 queries, 207 targets, 207 qrels, 188 evidence
  groups, 256 review records;
- review-history audit: 128 primary review records, 128 structured
  independent review records, 0 adjudication records, 0 conflicts, 0 frozen
  queries, 0 assigned queries;
- normalized duplicate query audit: 0 duplicates;
- exact regression-overlap audit: 0 matches;
- exact pilot-overlap audit: 0 matches;
- transitive grouping components: 116;
- query-level held-out candidates without qualified human review: 48;
- grouped held-out-eligible candidates: 43;
- development-only cases due high-risk without qualified human review: 80;
- excluded-from-freeze cases: 0;
- manifest absence check: no split or benchmark manifest exists;
- result: held-out pool improved, but freeze remains blocked by release-version
  and high-risk qualified-review gates.

Latest scoped `v0.1.0` freeze audit:

- full-benchmark validation with split manifest: 0 errors, 0 warnings;
- benchmark version: `v0.1.0`;
- draft record counts at freeze: 128 queries, 207 targets, 207 qrels, 188
  evidence groups, 256 review records;
- frozen query count: 128;
- split counts: 85 `development`, 43 `held_out_test`;
- held-out high-risk cases: 0;
- development high-risk cases: 80;
- benchmark manifest created:
  `data/eval/legal_qa_benchmark/benchmark_manifest.json`;
- split manifest created:
  `data/eval/legal_qa_benchmark/split_manifest.json`;
- result: scoped `v0.1.0` freeze completed.

Latest Stage F1 frozen dense retrieval baseline checks:

- frozen benchmark validation with split manifest: 0 errors, 0 warnings;
- retrieval config: `configs/retrieval/retrieval.yml`;
- Qdrant collection: `vnlaw_chunks_bgem3_v1_full`;
- embedding model: `BAAI/bge-m3`;
- vector name: `dense`;
- collection points verified at runtime: 40,389;
- retrieval cutoff: top-k 10;
- per-case retrieval results: 128 records;
- retrieval errors: 0;
- development metrics: Recall@10 0.794, MRR@10 0.583, NDCG@10 0.524,
  evidence group coverage@10 0.504;
- held-out metrics: Recall@10 0.929, MRR@10 0.777, NDCG@10 0.779,
  evidence group coverage@10 0.705;
- artifacts written under
  `artifacts/reports/evaluation/naive_rag_baseline/retrieval/`;
- result: frozen dense retrieval-only baseline completed without generation,
  OpenRouter, Qdrant writes, sparse retrieval, fusion, or reranking.

Latest Stage F2 frozen Naive RAG generation baseline checks:

- frozen benchmark validation with split manifest: 0 errors, 0 warnings;
- F1 retrieval artifacts reused and compatibility-checked;
- LLM provider/model: `openrouter` / `google/gemini-2.5-flash`;
- query count: 128;
- sample mode: false;
- generation errors: 0;
- development metrics: decision accuracy 0.529, answer-allowed answer rate
  0.500, fallback-required fallback rate 0.647, citation ID validity 1.000,
  evidence group coverage 0.452;
- held-out metrics: decision accuracy 0.233, answer-allowed answer rate
  0.214, fallback-required fallback rate 1.000, citation ID validity 1.000,
  evidence group coverage 0.202;
- artifacts written under
  `artifacts/reports/evaluation/naive_rag_baseline/generation/`;
- result: frozen Naive RAG generation baseline completed without benchmark
  data changes, fallback-gate relaxation, retrieval tuning, Qdrant writes, or
  Advanced RAG behavior.

## Change Log

| Date | Change |
| --- | --- |
| 2026-06-19 | Created Phase 10 progress tracer after repository inspection. |
| 2026-06-19 | Defined durable evaluation protocol. |
| 2026-06-19 | Implemented benchmark schemas, loaders, validator, grouped splitting, fingerprinting, CLI wrappers, tests, config, and technical docs. |
| 2026-06-19 | Hardened protocol invariants, split/review sources of truth, fingerprints, qrel/group consistency, and freeze immutability. |
| 2026-06-20 | Created and hardened 19-case draft pilot annotation. |
| 2026-06-20 | Completed structured D2 review and adjudicated the pilot scope conflict. |
| 2026-06-21 | Added review-assurance metadata and froze schema contract version `1.0`. |
| 2026-06-21 | Hardened D2 assurance wording and high-risk held-out review policy. |
| 2026-06-21 | Consolidated evaluation documentation into the current canonical structure. |
| 2026-06-21 | Added Stage E1 full benchmark construction planning, quota proposal, eligibility tiers, split strategy, and Stage E2 acceptance criteria. |
| 2026-06-21 | Created the first 36-case full-benchmark draft batch with primary annotation, structured automated review, and corpus-aware validation. |
| 2026-06-21 | Added the second 42-case full-benchmark draft batch, bringing the cumulative draft to 78 cases with corpus-aware validation passing. |
| 2026-06-21 | Added the final 42-case minimum-viable draft batch, bringing the cumulative draft to 120 cases with corpus-aware validation passing. |
| 2026-06-21 | Completed Stage E-Final pre-freeze audit and blocked split/freeze because held-out eligibility and coverage gates did not pass. |
| 2026-06-21 | Added an 8-case Stage E-Repair batch, improved grouped held-out eligibility to 43 cases, and recorded high-risk human-review allocation candidates without creating split or benchmark manifests. |
| 2026-06-21 | Froze scoped benchmark release `v0.1.0` with 43 low/medium-risk held-out cases, 85 development cases, and manifest fingerprints. |
| 2026-06-22 | Ran frozen dense retrieval-only baseline on benchmark `v0.1.0` and recorded split-level metrics, per-case retrieval results, and a baseline manifest. |
| 2026-06-22 | Ran frozen Naive RAG generation baseline on benchmark `v0.1.0`, reusing frozen F1 retrieval artifacts and recording split-level generation metrics. |

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
Stage F3 regression and quality-gate refresh
-> rerun the existing five-case regression suite
-> rerun the existing offline quality gate
-> compare frozen benchmark baseline observations with existing regression
   warnings
-> keep `v0.1.0` limitations visible in all comparison reports
-> do not start sparse retrieval, RRF, or reranking until regression and
   quality-gate refresh results are recorded
```

Sparse retrieval, RRF, and reranking must not begin yet.
