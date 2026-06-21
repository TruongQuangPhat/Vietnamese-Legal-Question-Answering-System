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
- Not done: full benchmark construction, dev/test split, held-out benchmark
  freeze, frozen Naive RAG baseline run, metrics, sparse retrieval, fusion,
  reranking, GraphRAG, API, UI, and fine-tuning.

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
| Stage E - Full Benchmark and Split Freeze | Not started | Full benchmark construction, grouped split, leakage validation, and manifest freeze remain pending. |
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

- [ ] minimum reviewed benchmark size;
- [ ] preferred benchmark size;
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
- Generation output can be non-deterministic even with fixed prompts and
  inputs.
- Sparse retrieval, fusion, and reranking may add latency and cost.

Open questions:

- What minimum and preferred benchmark sizes will be approved?
- What final domain quotas will be approved?
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

Documentation consolidation validation is tracked in the current task result.

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
full benchmark construction planning
-> annotation workload and qualified-review allocation
-> full benchmark construction
-> grouped split and leakage validation
```

Sparse retrieval, RRF, and reranking must not begin yet.
