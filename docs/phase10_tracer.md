# Phase 10 Progress Tracer

## Document Purpose

This document tracks active Phase 10 progress for the benchmark-first Advanced
RAG comparison.

- `AGENTS.md` remains the canonical repository instruction source.
- `PROJECT_CONTEXT.md` remains the canonical current-state and roadmap source.
- `docs/naive_rag.md` remains the canonical Naive RAG technical reference.
- This tracer must not override those files.
- Durable technical decisions must eventually be consolidated into functional
  documentation.
- This tracer should be deleted or archived after Phase 10 closure and durable
  information has been consolidated.

## Current Status

Verified repository state as of 2026-06-20:

- Trusted corpus source: `https://thuvienphapluat.vn`.
- Corpus status: 52 registered legal documents have completed ingestion,
  normalization, hierarchy parsing, chunking, validation, embedding, and dense
  indexing according to `PROJECT_CONTEXT.md` and current documentation.
- Processed chunk count: `data/processed/legal_chunks.jsonl` contains 40,389
  JSONL rows.
- Embedding model: `BAAI/bge-m3`.
- Qdrant collection: `vnlaw_chunks_bgem3_v1_full`.
- Dense vector: named vector `dense`, 1024 dimensions, cosine distance.
- Sparse indexing: not enabled for the current baseline.
- Dense baseline status: dense retrieval, evidence construction, evidence
  selection, fallback-aware Naive RAG generation, generation evaluation,
  manual review export, manual faithfulness verdicts, and offline quality gate
  are implemented under `src/retrieval/` and `scripts/retrieval/`.
- Five-case regression suite role: the current five-case suite is a regression
  and safety suite, not a held-out benchmark.
- Quality-gate status: `quality_gate_passed`, with 0 hard violations, 0
  quality violations, and 2 accepted warnings in the non-blocking
  `marriage_conditions_generation` case.
- Known limitations: the reviewed generation suite has only five cases,
  `marriage_conditions_generation` remains partial/non-blocking, complete-list
  questions require fuller evidence coverage, dense-only retrieval still falls
  back for the annual-leave control, citation-ID validity is not semantic
  faithfulness, model output may vary, and the system is not production legal
  advice.
- Current Phase 10 stage: Stage D stabilization is complete for the draft
  pilot. The pilot has completed source-grounded primary annotation,
  structured automated second-pass review, and repository-level adjudication.
  This does not constitute qualified human legal review. Qualified human legal
  review has not been completed. Schema/protocol stabilization has passed, and
  schema contract version `1.0` is frozen for full benchmark construction. No
  held-out split, benchmark freeze, baseline execution, metrics, sparse
  retrieval, fusion, or reranking has been implemented.

## Phase 10 Objective

Primary experimental question:

Does Advanced RAG improve over the frozen Naive RAG baseline on a legally
reviewed benchmark and untouched held-out test split?

Adding BM25, sparse retrieval, RRF, or reranking is not itself success. Success
requires held-out improvements in retrieval and evidence coverage without
unacceptable regressions in legal faithfulness, safety, latency, or cost.

## Safety and Experimental Invariants

- Legal answers require trusted sources and traceable citations.
- No fabricated legal claims, laws, articles, clauses, points, penalties,
  procedures, effective dates, or citations.
- Preserve Vietnamese legal hierarchy: Phần -> Chương -> Mục -> Điều -> Khoản
  -> Điểm.
- Raw corpus artifacts are immutable.
- Use the existing Qdrant collection read-only unless a separate scoped task
  authorizes indexing or migration.
- Generation may use selected evidence only.
- Auxiliary parent context is not directly citable unless selected child
  evidence explicitly supports the claim.
- Fallback must not call the LLM.
- The existing quality gate must not be weakened.
- The five-case suite remains separate from the held-out benchmark.
- Test data must not be used for tuning.
- The primary comparison changes retrieval only.
- Secrets must never be logged, printed, or serialized.

## Protected Assets

Protected corpus paths:

```text
data/raw/
data/interim/
data/reports/
data/processed/legal_chunks.jsonl
```

Baseline assets to preserve:

- Qdrant collection: `vnlaw_chunks_bgem3_v1_full`.
- Five-case retrieval input: `data/eval/manual_retrieval_queries.jsonl`.
- Five-case generation input:
  `data/eval/manual_naive_rag_generation_queries.jsonl`.
- Manual faithfulness verdicts:
  `data/eval/manual_faithfulness_verdicts.json`.
- Quality-gate policy: `configs/retrieval/quality_gate.yml`.
- Retrieval baseline config: `configs/retrieval/retrieval.yml`.
- Existing generated reports under `artifacts/reports/retrieval/` are runtime
  evidence, not canonical source of truth.

## Existing Evaluation Assets

| Asset | Current purpose | Reusable for Phase 10 | Must remain unchanged | Inspection notes |
| --- | --- | --- | --- | --- |
| `data/eval/manual_retrieval_queries.jsonl` | Five manual dense retrieval queries and expected legal targets | Yes, as regression input only | Yes | Inspected; 5 records; includes expected decisions and annual-leave fallback control. |
| `data/eval/manual_naive_rag_generation_queries.jsonl` | Five deterministic Naive RAG generation evaluation cases | Yes, as regression input only | Yes | Inspected; 5 records; includes blocking and non-blocking review flags. |
| `data/eval/manual_faithfulness_verdicts.json` | Human claim-to-citation verdict manifest | Yes, as regression review manifest only | Yes | Inspected; records supported claims and accepted non-blocking marriage warnings. |
| `configs/retrieval/quality_gate.yml` | Offline quality-gate policy for the reviewed baseline | Yes, as baseline safety gate | Yes | Inspected; hard gates require perfect decision, LLM-call, fallback, citation-ID, secret-leak, and unsupported-claim checks. |
| `configs/retrieval/retrieval.yml` | Dense retrieval baseline config | Yes, as frozen baseline metadata | Yes | Inspected; BGE-M3, `dense`, 1024 dimensions, collection `vnlaw_chunks_bgem3_v1_full`. |
| `src/retrieval/models.py` | Typed dense retrieval config, query, filter, hit, and result models | Yes | Yes | Inspected; includes `RetrievalResult`, `RetrievedChunk`, and dense config models. |
| `src/retrieval/evidence.py` | Evidence packet and bundle construction with citation-safety metadata | Yes | Yes | Inspected; includes `EvidenceBundle`, `EvidencePacket`, parent context policy, and safety levels. |
| `src/retrieval/selection.py` | Evidence selection and fallback/review decisions | Yes | Yes | Inspected; includes `EvidenceSelectionResult` and conservative fallback reasons. |
| `src/retrieval/generation.py` | Generation result models, deterministic fallback, and citation-ID guard | Yes | Yes | Inspected; fallback result sets `llm_called=false`. |
| `src/retrieval/evaluation.py` | Manual dense retrieval evaluation models and metric helpers | Yes, partly | Yes | Inspected; includes current Recall@5/10/20, MRR@20, article/exact hit metrics, risk flags, and JSONL loader. |
| `src/retrieval/generation_evaluation.py` | Deterministic generation evaluation models and loaders | Yes, partly | Yes | Inspected; covers decision policy, LLM-call policy, fallback, citation-ID, language, forbidden phrase, and secret-like leakage checks. |
| `src/retrieval/quality_gate.py` | Offline quality-gate evaluator and report models | Yes, for regression gate | Yes | Inspected; offline only, no Qdrant/OpenRouter calls. |
| `src/retrieval/manual_review.py` | Manual review Markdown export helpers | Yes, as review workflow reference | Yes | Inspected; secret-screened review worksheet export. |
| `src/retrieval/workflows/common.py` | Shared config loading, protected-path checks, JSON report writing | Yes | Yes | Inspected; includes `write_json_report` and protected output checks. |
| `scripts/retrieval/*.py` | Thin CLI wrappers for retrieval, generation evaluation, manual review, and quality gate | Yes, as CLI convention reference | Yes | Inspected; wrappers delegate to reusable `src/retrieval` workflows. |
| `tests/unit/retrieval/` | Unit coverage for retrieval, evidence, selection, generation, evaluation, quality gate, and workflows | Yes, as test convention reference | Yes | Inspected by inventory/search; no test files changed. |
| `configs/evaluation/legal_qa_benchmark.yml` | Benchmark configuration for schema, splitting, and validation defaults | Yes | Yes | Created in Stage C; non-secret, provisional defaults only. |
| `src/evaluation/benchmark/` | Broader benchmark schemas, loaders, validator, splitter, fingerprinting, and freeze support | Yes | Yes | Created in Stage C; separate from `src/retrieval/` regression logic. |
| `tests/unit/evaluation/benchmark/` | Unit tests for benchmark schemas and deterministic utilities | Yes | Yes | Created in Stage C with synthetic non-authoritative fixtures. |
| `tests/integration/evaluation/test_benchmark_workflow.py` | Synthetic benchmark workflow integration test | Yes | Yes | Created in Stage C; no external service calls. |
| `docs/legal_qa_benchmark.md` | Functional benchmark implementation documentation | Yes | Yes | Created in Stage C; documents file layout, invariants, CLIs, and limitations. |
| `data/eval/legal_qa_benchmark/pilot/` | Draft pilot annotation for independent review preparation | Yes, as pilot input only | Yes | Created in Stage D1; primary-reviewed, pre-split, not frozen, and not held-out proof. |
| `docs/naive_rag.md` | Canonical Naive RAG baseline technical reference | Yes | Yes | Inspected; confirms baseline closure and safety invariants. |
| `docs/advanced_rag.md` | Advanced retrieval design reference | Yes, as non-canonical design input | Yes | Inspected; contains future/unimplemented ideas and expected improvements not yet verified. |
| `docs/evaluation.md` | Evaluation design reference | Yes, as non-canonical design input | Yes | Inspected; describes intended future evaluation assets and commands. |

## Workstream Overview

### Benchmark Foundation

- inspect existing evaluation assets;
- define benchmark scope and taxonomy;
- define query schema;
- define legal-target schema;
- define evidence judgments;
- define evidence groups;
- define annotation workflow;
- define legal-review and adjudication workflow;
- define grouped deterministic split strategy;
- define benchmark validation rules;
- define benchmark fingerprinting and freeze rules.

### Frozen Baseline

- run the Naive RAG baseline on development;
- validate the baseline evaluation workflow on development;
- freeze the baseline configuration and run manifest;
- defer held-out baseline execution until the final held-out comparison;
- preserve development and held-out reports separately.

### Hybrid Retrieval

- implement sparse retrieval only after benchmark freeze;
- compare dense versus dense+sparse;
- implement fusion as a controlled variant;
- tune only on development;
- keep generation, selection, and fallback fixed.

### Reranking

- add reranking as a separate ablation;
- compare dense, hybrid, and hybrid+reranker;
- measure reranking latency, memory, and throughput;
- avoid combining multiple uncontrolled changes.

### Held-Out Evaluation

- freeze all candidate configurations;
- run the final held-out comparison;
- do not tune after observing held-out results;
- record wins, losses, ties, and regressions;
- report domain and question-type breakdowns.

### Closure

- evaluate whether Advanced RAG is justified;
- consolidate durable technical documentation;
- update `PROJECT_CONTEXT.md`;
- preserve the five-case regression suite;
- remove or archive this tracer after closure.

## Detailed Progress Checklist

### Stage A - Repository Inspection

- [x] canonical instruction review;
- [x] relevant skill review;
- [x] git status inspection;
- [x] evaluation asset inventory;
- [x] retrieval model inventory;
- [x] reusable utility inventory;
- [x] test and CLI convention inventory;
- [x] stale documentation or instruction conflicts.

### Stage B - Benchmark Protocol

- [x] benchmark inclusion and exclusion policy;
- [x] domain taxonomy;
- [x] question-type taxonomy;
- [x] expected-decision definitions;
- [x] direct/supporting/near-miss relevance definitions;
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
- [x] schema revision assessment - backward-compatible review-assurance
  metadata added;
- [x] protocol revision assessment - review-assurance clarification added;
- [x] schema/protocol stabilization;
- [x] schema version freeze;
- [ ] qualified human legal review, required before eligible high-risk
  held-out use.

### Stage E - Full Benchmark and Split Freeze

- [ ] minimum reviewed benchmark size;
- [ ] preferred benchmark size;
- [ ] duplicate detection;
- [ ] near-duplicate detection;
- [ ] paraphrase-family grouping;
- [ ] source-provision grouping;
- [ ] deterministic dev/test split;
- [ ] leakage validation;
- [ ] test freeze;
- [ ] checksums;
- [ ] benchmark manifest.

### Stage F - Frozen Naive RAG Baseline

- [ ] dev baseline run;
- [ ] held-out baseline execution plan;
- [ ] held-out baseline execution deferred until Stage I;
- [ ] run manifest;
- [ ] effective runtime parameter capture;
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

## Required Metrics

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
prompt tokens
completion tokens
total tokens
cost per query
peak memory
throughput
```

Latency reports should include mean, median, p95, and p99 where appropriate.

## Deliverables

| Deliverable | Planned path | Status | Dependencies | Notes |
| --- | --- | --- | --- | --- |
| Evaluation configuration | `configs/evaluation/legal_qa_benchmark.yml` | Created | Benchmark protocol | Non-secret benchmark options only; no final domain quotas or metric gains. |
| Legal QA benchmark data | `data/eval/legal_qa_benchmark/` | Draft pilot directory created; frozen benchmark not created | Approved schema, annotation workflow | Pilot data is primary-reviewed only, pre-split, and not held-out proof. |
| Pilot benchmark annotation | `data/eval/legal_qa_benchmark/pilot/` | Created | Stage B protocol and Stage C implementation | Contains 19 draft pilot queries, targets, qrels, evidence groups, review records, and README coverage summary. |
| Pilot independent review report | `data/eval/legal_qa_benchmark/pilot/independent_review_report.md` | Created | Stage D2 structured review | Records 19 second-pass reviews, 1 material disagreement, and 1 adjudication; not qualified human legal review. |
| Pilot stabilization report | `data/eval/legal_qa_benchmark/pilot/stabilization_report.md` | Created | Stage D2 review history and schema/protocol assessment | Concludes schema version `1.0` is stable for full benchmark construction; does not freeze pilot data. |
| Benchmark schema and loaders | `src/evaluation/benchmark/` | Created | Protocol and schema approval | Includes enums, schemas, exceptions, loaders, validator, splitting, and fingerprinting. |
| Evaluation metrics | `src/evaluation/metrics/` | Planned; not created | Metric definitions | Include retrieval, decision/safety, generation, and operational metrics. |
| Evaluation reporting | `src/evaluation/reporting/` | Planned; not created | Report schema and manifest design | Reports must include dataset version and fingerprints. |
| Evaluation CLIs | `scripts/evaluation/validate_benchmark.py`, `scripts/evaluation/create_benchmark_split.py`, `scripts/evaluation/freeze_benchmark.py` | Created | Reusable services under `src/evaluation/` | Thin wrappers only; no Qdrant or OpenRouter calls. |
| Unit tests | `tests/unit/evaluation/benchmark/` | Created | Implemented schemas, loaders, validator, splitting, fingerprinting | Uses synthetic non-authoritative fixtures only. |
| Integration tests | `tests/integration/evaluation/test_benchmark_workflow.py` | Created | End-to-end benchmark workflow | Uses temporary synthetic files only; no external service calls. |
| Benchmark documentation | `docs/legal_qa_benchmark.md` | Created | Protocol and schema implementation | Functional technical documentation for Stage C implementation. |
| Evaluation protocol documentation | `docs/evaluation_protocol.md` | Created | Protocol decisions | Durable Stage B protocol for benchmark rules, review, split, freeze, and comparison. |

## Decision Log

| Date | Decision | Rationale | Affected scope | Status |
| --- | --- | --- | --- | --- |
| 2026-06-19 | Benchmark-first development | Canonical instructions require broader reviewed benchmark and frozen splits before Advanced RAG comparison. | Phase 10 planning and implementation order | Verified |
| 2026-06-19 | Preserve the five-case regression suite | Current suite is useful for safety/regression but is not a held-out benchmark. | `data/eval/`, `configs/retrieval/quality_gate.yml`, regression workflows | Verified |
| 2026-06-19 | Keep current baseline logic under `src/retrieval/` and broader benchmark logic under `src/evaluation/` when implemented | Repository guidance separates existing Naive RAG regression logic from future broader evaluation layer. | Module ownership | Verified |
| 2026-06-19 | Use grouped deterministic dev/test splitting | Prevent paraphrase-family and source-provision leakage. | Benchmark construction | Verified as required direction |
| 2026-06-19 | Do not tune on held-out test data | Held-out comparison is valid only if test data remains untouched until candidate configs are frozen. | Evaluation protocol | Verified |
| 2026-06-19 | Change retrieval only in the primary comparison | Corpus, chunking, generator, prompt, selection, fallback, and evaluation code should remain fixed unless a controlled ablation explicitly changes one component. | Comparative evaluation | Verified |
| 2026-06-19 | Use binary final benchmark decisions | The broader frozen benchmark must adjudicate final ground truth to `answer_allowed` or `fallback_required`; existing Phase 9 `needs_review` records remain unchanged. | Benchmark labels and schema design | Approved in protocol |
| 2026-06-19 | Separate direct, supporting, near-miss, and irrelevant evidence | Legal support requires semantic direct evidence, not lexical similarity, parent context, or near-miss provisions. | Evidence judgments and metrics | Approved in protocol |
| 2026-06-19 | Treat evidence groups as semantic completeness requirements | Complete-list and multi-evidence cases require group-level completion rather than a flat list of chunk IDs. | Benchmark annotation and metric design | Approved in protocol |
| 2026-06-19 | Require independent review for held-out and high-risk cases | Held-out, complete-list, cross-law, temporal, fallback, ambiguous, and blocking cases need review beyond chunk-ID validation. | Review workflow | Approved in protocol |
| 2026-06-19 | Freeze held-out labels by version | Held-out labels must not be edited in place; corrections require a new benchmark version and documented reason. | Benchmark versioning | Approved in protocol |
| 2026-06-19 | Implement broader benchmark logic under `src/evaluation/benchmark/` | Stage C needs durable benchmark schemas and validation without moving or weakening existing Naive RAG regression logic. | Evaluation architecture | Implemented |
| 2026-06-19 | Use Pydantic v2 strict input schemas | Unknown fields and malformed records should fail deterministically before annotation data is frozen. | Benchmark schemas and loaders | Implemented |
| 2026-06-19 | Use connected components for grouped split constraints | `case_family_id` and `source_provision_group_id` leakage is transitive and cannot be handled by independent field grouping. | Split creation | Implemented |
| 2026-06-19 | Keep corpus-aware validation read-only | Corpus registry and processed chunks are authoritative validation inputs but protected from mutation. | Validator and freeze support | Implemented |
| 2026-06-19 | Keep regression contamination checks explicit and conservative | Declared regression overlap and exact normalized query matches are enforceable; semantic overlap still requires human review. | Split and validation policy | Implemented |
| 2026-06-19 | Treat file checksums and canonical model hashes as distinct | Raw artifact checksums preserve exact files; canonical hashes support deterministic data/model fingerprints. | Fingerprinting and freeze manifests | Implemented |
| 2026-06-19 | Treat protocol invariants as non-configurable | Held-out review, chunk-level qrels for frozen answer-allowed groups, Vietnamese diacritic preservation, and mandatory grouping fields are safety rules rather than tuning knobs. | Benchmark config and validator | Implemented |
| 2026-06-19 | Use `SplitManifest.assignments` as canonical split state | `BenchmarkQuery.split` is a denormalized summary and must match the manifest before freeze. | Split validation and freeze support | Implemented |
| 2026-06-19 | Use `ReviewRecord` as canonical review evidence | `BenchmarkQuery.review_status` is a denormalized summary and cannot bypass missing review records. | Review validation and freeze support | Implemented |
| 2026-06-19 | Store canonical frozen manifests with benchmark data | Runtime reports may live under `artifacts/reports/evaluation/`, but frozen `split_manifest.json` and `benchmark_manifest.json` belong under `data/eval/legal_qa_benchmark/`. | Benchmark documentation and CLI usage | Documented |
| 2026-06-19 | Refuse draft or overwritten freezes | Frozen benchmark releases require a release version, a new output path, complete validation, and post-write manifest verification. | Freeze support | Implemented |
| 2026-06-20 | Keep pilot records pre-split and primary-reviewed only | Stage D1 prepares cases for independent review and must not create held-out assignments or frozen manifests. | Pilot annotation | Implemented |
| 2026-06-20 | Use two deliberate regression bridge cases only | Bridge cases preserve compatibility with known regression targets while remaining permanently ineligible for held-out proof. | Pilot annotation and contamination policy | Implemented |
| 2026-06-20 | Omit temporal pilot cases until metadata is sufficient | Processed chunk inspection did not expose enough effective/expiry metadata for defensible `as_of_date` annotation. | Pilot coverage | Implemented |
| 2026-06-20 | Keep D2 review procedural, not human-legal | The second pass improves annotation discipline but must not be represented as qualified legal counsel. | Pilot review documentation | Implemented |
| 2026-06-20 | Adjudicate `pilot_0003` by narrowing query scope | The original overtime query could require Article 107 Clause 3 evidence, while the available child chunks do not directly expose the 300-hour cap header. | Pilot annotation | Implemented |
| 2026-06-21 | Record review assurance separately from review stage | Workflow completion must not be confused with qualified human legal review. | `ReviewRecord`, pilot review records, documentation | Implemented |
| 2026-06-21 | Freeze schema contract version `1.0` for full benchmark construction | The reviewed pilot exercised schemas, validation, review history, and adjudication without unresolved blocking issues after assurance metadata was added. | Benchmark schema contract | Approved |
| 2026-06-21 | Require accurate benchmark assurance claims and qualified review for high-risk held-out use | The benchmark may be described as source-grounded, schema-validated, corpus-aware validated, structured-review-completed, and repository-adjudicated when true, but not expert-reviewed, lawyer-reviewed, or legally validated without recorded qualified human legal review. High-risk held-out items require qualified human legal review or exclusion from the frozen held-out split. | Benchmark documentation and release claims | Approved |

## Risks and Open Questions

Confirmed risks:

- Benchmark annotation cost may be high.
- Qualified human legal review coverage may be insufficient without staffing
  and scheduling for full benchmark construction.
- Complete-list questions require evidence-group and completeness semantics.
- Paraphrase and source-provision leakage can invalidate dev/test splits.
- Embedding model revision is currently nullable in `configs/retrieval/retrieval.yml`.
- Generation output can be non-deterministic even with fixed prompts and inputs.
- Sparse index design is not selected.
- Held-out test contamination remains a risk if test queries are inspected for
  tuning.
- Latency and cost may regress when sparse retrieval, fusion, or reranking are
  added.
- Pilot annotations may change after qualified human legal review.
- Two pilot bridge cases intentionally overlap regression targets and must
  remain excluded from held-out proof.
- Current pilot coverage omits temporal/version-sensitive cases because chunk
  metadata is insufficient for defensible temporal labels.
- D2 review was a structured repository review and did not provide qualified
  human legal review.
- High-risk held-out items require qualified human legal review or exclusion
  from the frozen held-out split.
- Full benchmark construction may expose schema or protocol edge cases not
  represented in the 19-case pilot.

Open design questions:

- What minimum and preferred benchmark sizes will be approved?
- What final domain quotas will be approved for the registry-derived taxonomy?
- Whether secondary domains should be required for every cross-law case or only
  where needed for stratification.
- What exact relevance gain values should be used for nDCG?
- What numeric relevance gain, if any, should be assigned to supporting
  evidence after metric implementation defines contextual usefulness?
- What exact blocking-case thresholds should gate system comparison?
- What manual-review threshold should flag diacritic-sensitive near-duplicates
  without automatically merging Vietnamese legal queries.
- Who will staff qualified human legal review and any later legal-review
  adjudication for full benchmark conflicts?
- What benchmark versioning convention should be used?
- Which deterministic fingerprint fields are required for corpus, chunks,
  Qdrant collection, prompts, and model configuration?
- Whether sparse retrieval should use Qdrant sparse vectors, BM25 outside
  Qdrant, or BGE-M3 sparse output in a separately scoped implementation.
- Which reranker, if any, is acceptable after the benchmark is frozen.
- Whether frozen real benchmark files should require both explicit chunk IDs
  and legal targets for every required group, beyond the current chunk-ID
  requirement.
- Whether `pilot_0001` should include a separate same-sex marriage recognition
  case or keep Article 8 Clause 2 outside the current query scope.
- Whether `pilot_0002` evidence groups are granular enough for the cross-law
  marital-property question.
- Whether `pilot_0017` is correctly labeled `incomplete_evidence` after
  independent review confirms the current corpus lacks a direct decree-level
  motorbike red-light fine target.
- Whether `pilot_0018` should remain `unsafe_ambiguity` or be split into
  narrower leave-entitlement cases.
- Whether a qualified human legal reviewer should re-open any D2-confirmed
  pilot case before full benchmark freeze or held-out use.

## Validation Log

No repository-documented Markdown lint command was found in `pyproject.toml`,
README, docs, or common task files during inspection.

| Date | Scope | Command | Result | Notes |
| --- | --- | --- | --- | --- |
| 2026-06-19 | Worktree state | `git status --short` | Completed | Existing user changes found in `.agents/skills/SKILL_INDEX.md` and `.env.example`; not touched. |
| 2026-06-19 | Repository inventory | `find src scripts configs data/eval docs tests -maxdepth 3 -type f \| sort` | Completed | Confirmed current retrieval implementation and evaluation scaffolds. |
| 2026-06-19 | Retrieval model inventory | `rg -n "class .*Result\|class .*Report\|BaseModel\|dataclass\|EvidenceBundle\|EvidenceSelectionResult" src/retrieval` | Completed | Confirmed typed result/report/evidence models. |
| 2026-06-19 | Evaluation loader and serialization inventory | `rg -n "manual_retrieval_queries\|manual_naive_rag_generation_queries\|jsonl\|model_validate\|model_dump" src/retrieval scripts/retrieval` | Completed | Confirmed JSONL loaders and JSON report serialization patterns. |
| 2026-06-19 | Metric and safety inventory | `rg -n "Recall\|MRR\|NDCG\|hit_rate\|latency\|citation\|fallback\|quality_gate" src/retrieval scripts/retrieval tests` | Completed | Confirmed current metric, fallback, citation, and gate coverage. |
| 2026-06-19 | Evaluation asset counts | `wc -l data/eval/manual_retrieval_queries.jsonl data/eval/manual_naive_rag_generation_queries.jsonl data/processed/legal_chunks.jsonl` | Completed | Confirmed 5 retrieval queries, 5 generation queries, and 40,389 processed chunks. |
| 2026-06-19 | Diff hygiene | `git diff --check` | Passed | No whitespace errors reported after creating this tracer. |
| 2026-06-19 | Worktree state | `git status --short` | Completed | No output before Stage B edits. |
| 2026-06-19 | Corpus registry taxonomy inspection | `sed -n '1,260p' configs/laws/corpus_registry.yml` and follow-up slices | Completed | Used registry groups and domain tags to define domain taxonomy. |
| 2026-06-19 | Regression asset compatibility inspection | `sed -n` over current manual retrieval, generation, faithfulness, quality-gate, and retrieval config assets | Completed | Confirmed existing `needs_review` remains Phase 9-only and broader benchmark uses adjudicated binary decisions. |
| 2026-06-19 | Retrieval terminology inspection | `sed -n` over `src/retrieval/evaluation.py`, `src/retrieval/selection.py`, and `src/retrieval/evidence.py` | Completed | Confirmed terminology for expected targets, decisions, evidence packets, citation scope, and fallback reasons. |
| 2026-06-19 | Markdown validation discovery | `rg -n "markdown\|mdformat\|markdownlint\|pymarkdown\|prettier" README.md docs pyproject.toml` and task-file discovery | No applicable command found | No repository-documented Markdown validation command was available. |
| 2026-06-19 | Diff hygiene | `git diff --check` | Passed | No whitespace errors reported after creating the protocol and updating this tracer. |
| 2026-06-19 | Worktree state | `git status --short` | Completed | Existing Stage B docs changes present before clarification edits: `docs/phase10_tracer.md`, `docs/evaluation_protocol.md`. |
| 2026-06-19 | Protocol consistency self-review | `rg -n "supporting\|evidence group\|blocking\|hard violation\|fallback_reason\|diacritic\|acceptable_chunk_ids\|acceptable_legal_targets\|document title\|match level\|Phan\|Chuong" docs/evaluation_protocol.md docs/phase10_tracer.md` | Completed | Confirmed revised protocol terms are explicit; remaining matches are expected current terms or tracer history. |
| 2026-06-19 | Protocol ambiguity self-review | targeted `rg -n` search for disallowed ambiguity terms in `docs/evaluation_protocol.md` | Passed | No disallowed ambiguous terms remain in the protocol. |
| 2026-06-19 | Protocol invariant self-review | targeted `rg -n` search for required clarification terms in `docs/evaluation_protocol.md` | Passed | Confirmed required clarification language is present. |
| 2026-06-19 | Diff hygiene | `git diff --check` | Passed | No whitespace errors reported after protocol clarification edits. |
| 2026-06-19 | Stage C pre-edit worktree | `git status --short` | Passed | Worktree was clean before Stage C implementation. |
| 2026-06-19 | Stage C protocol preflight | `rg -n "unsupported substantive\|substantive legal claim without\|required direct citation\|acceptable_chunk_ids\|must not replace\|substantially overlaps\|held_out_test\|development.*case_family_id\|selected child evidence\|Auxiliary parent context\|parent context" docs/evaluation_protocol.md` | Passed | Confirmed required Stage B preflight rules were present before implementation. |
| 2026-06-19 | Python compile | `uv run python -m py_compile src/evaluation/benchmark/*.py scripts/evaluation/*.py` | Passed | New Stage C Python modules and scripts compile. |
| 2026-06-19 | Unit tests | `uv run pytest tests/unit/evaluation -q` | Passed | 43 passed. |
| 2026-06-19 | Integration tests | `uv run pytest tests/integration/evaluation -q` | Passed | 1 passed. |
| 2026-06-19 | Ruff lint | `uv run ruff check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | No lint errors after scoped formatting/import fixes. |
| 2026-06-19 | Ruff format check | `uv run ruff format --check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | 18 files already formatted. |
| 2026-06-19 | Lockfile check | `uv lock --check` | Passed | Lockfile resolved without update. |
| 2026-06-19 | CLI help smoke | `uv run python scripts/evaluation/validate_benchmark.py --help` | Passed | Help text displayed; no benchmark files loaded. |
| 2026-06-19 | CLI help smoke | `uv run python scripts/evaluation/create_benchmark_split.py --help` | Passed | Help text displayed; no benchmark files loaded. |
| 2026-06-19 | CLI help smoke | `uv run python scripts/evaluation/freeze_benchmark.py --help` | Passed | Help text displayed; no benchmark files loaded. |
| 2026-06-19 | Diff hygiene | `git diff --check` | Passed | No whitespace errors after Stage C implementation. |
| 2026-06-19 | Stage C hardening pre-edit worktree | `git status --short` | Completed | Existing uncommitted Stage C implementation files were present; no unrelated files were modified. |
| 2026-06-19 | Stage C hardening audit | targeted `rg -n` over config, benchmark modules, scripts, tests, and docs | Completed | Classified protocol invariants, split/review source-of-truth, manifest placement, fingerprints, qrel consistency, and freeze immutability. |
| 2026-06-19 | Unit tests after hardening | `uv run pytest tests/unit/evaluation -q` | Passed | 67 passed after hardening changes. |
| 2026-06-19 | Integration tests after hardening | `uv run pytest tests/integration/evaluation -q` | Passed | 1 passed after hardening changes. |
| 2026-06-19 | Ruff fix after hardening | `uv run ruff check --fix src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | Fixed scoped lint issue in new Stage C tests. |
| 2026-06-19 | Ruff format after hardening | `uv run ruff format src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | Reformatted scoped Stage C files only. |
| 2026-06-19 | Python compile after hardening | `uv run python -m py_compile src/evaluation/benchmark/*.py scripts/evaluation/*.py` | Passed | Stage C benchmark modules and CLI wrappers compile. |
| 2026-06-19 | Unit tests after hardening final | `uv run pytest tests/unit/evaluation -q` | Passed | 67 passed. |
| 2026-06-19 | Integration tests after hardening final | `uv run pytest tests/integration/evaluation -q` | Passed | 1 passed. |
| 2026-06-19 | Ruff lint after hardening final | `uv run ruff check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | All checks passed. |
| 2026-06-19 | Ruff format check after hardening final | `uv run ruff format --check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | 19 files already formatted. |
| 2026-06-19 | Lockfile check after hardening | `uv lock --check` | Passed | Resolved 130 packages; lockfile unchanged. |
| 2026-06-19 | CLI help smoke after hardening | `uv run python scripts/evaluation/validate_benchmark.py --help` | Passed | Help text displayed; no benchmark files loaded. |
| 2026-06-19 | CLI help smoke after hardening | `uv run python scripts/evaluation/create_benchmark_split.py --help` | Passed | Help text displayed; no benchmark files loaded. |
| 2026-06-19 | CLI help smoke after hardening | `uv run python scripts/evaluation/freeze_benchmark.py --help` | Passed | Help text displayed; no benchmark files loaded. |
| 2026-06-19 | Diff hygiene after hardening | `git diff --check` | Passed | No whitespace errors after Stage C hardening. |
| 2026-06-20 | Stage D1 pre-edit worktree | `git status --short` | Passed | No output; worktree was clean before pilot annotation. |
| 2026-06-20 | Corpus registry inventory | `uv run python - <<'PY' ... yaml.safe_load(configs/laws/corpus_registry.yml) ... PY` | Completed | Read-only inventory confirmed 52 registered law IDs and domain tags. |
| 2026-06-20 | Processed chunk inventory | `uv run python - <<'PY' ... data/processed/legal_chunks.jsonl ... PY` | Completed | Read-only inventory confirmed chunk schema, law/article/clause/point coverage, and candidate provisions. |
| 2026-06-20 | Regression overlap inspection | `head -n 5 data/eval/manual_retrieval_queries.jsonl` and `head -n 5 data/eval/manual_naive_rag_generation_queries.jsonl` | Completed | Used to identify deliberate bridge cases and avoid copying all five regression cases. |
| 2026-06-20 | Validator help smoke | `uv run python scripts/evaluation/validate_benchmark.py --help` | Passed | Confirmed supported CLI arguments before pilot validation. |
| 2026-06-20 | Pilot record counts | `wc -l data/eval/legal_qa_benchmark/pilot/benchmark_queries.jsonl data/eval/legal_qa_benchmark/pilot/benchmark_targets.jsonl data/eval/legal_qa_benchmark/pilot/benchmark_qrels.jsonl data/eval/legal_qa_benchmark/pilot/evidence_groups.jsonl data/eval/legal_qa_benchmark/pilot/review_records.jsonl` | Passed | 19 queries, 47 targets, 47 qrels, 39 evidence groups, 19 review records. |
| 2026-06-20 | Corpus-aware pilot validation | `uv run python scripts/evaluation/validate_benchmark.py --queries data/eval/legal_qa_benchmark/pilot/benchmark_queries.jsonl --legal-targets data/eval/legal_qa_benchmark/pilot/benchmark_targets.jsonl --evidence-judgments data/eval/legal_qa_benchmark/pilot/benchmark_qrels.jsonl --evidence-groups data/eval/legal_qa_benchmark/pilot/evidence_groups.jsonl --review-records data/eval/legal_qa_benchmark/pilot/review_records.jsonl --config configs/evaluation/legal_qa_benchmark.yml --corpus-registry configs/laws/corpus_registry.yml --processed-chunks data/processed/legal_chunks.jsonl --output /tmp/vnlaw_pilot_validation_report.json` | Passed | 0 errors, 2 expected warnings for unsplit regression-overlap bridge cases. |
| 2026-06-20 | Python compile | `uv run python -m py_compile src/evaluation/benchmark/*.py scripts/evaluation/*.py` | Passed | Stage C benchmark modules and CLI wrappers still compile after pilot annotation. |
| 2026-06-20 | Evaluation unit tests | `uv run pytest tests/unit/evaluation -q` | Passed | 67 passed. |
| 2026-06-20 | Evaluation integration tests | `uv run pytest tests/integration/evaluation -q` | Passed | 1 passed. |
| 2026-06-20 | Retrieval unit regression tests | `uv run pytest tests/unit/retrieval -q` | Passed | 173 passed; no Qdrant or OpenRouter calls. |
| 2026-06-20 | Ruff lint | `uv run ruff check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | All checks passed. |
| 2026-06-20 | Ruff format check | `uv run ruff format --check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | 19 files already formatted. |
| 2026-06-20 | Lockfile check | `uv lock --check` | Passed | Resolved 130 packages; lockfile unchanged. |
| 2026-06-20 | Diff hygiene | `git diff --check` | Passed | No whitespace errors after Stage D1 pilot annotation. |
| 2026-06-20 | Pilot git visibility | `git check-ignore -v data/eval/legal_qa_benchmark/pilot/benchmark_queries.jsonl data/eval/legal_qa_benchmark/pilot/README.md` | Completed | Confirmed `.gitignore` needed narrow exceptions for pilot files. |
| 2026-06-20 | Stage D1 hardening pre-edit worktree | `git status --short` | Completed | Existing uncommitted Stage D1 changes were present in `.gitignore`, `docs/phase10_tracer.md`, and `data/eval/legal_qa_benchmark/`. |
| 2026-06-20 | Pilot semantic hardening inspection | `uv run python - <<'PY' ... inspect pilot_0013, pilot_0016, pilot_0017, pilot_0018 ... PY` | Completed | Confirmed corrected temporal wording, multi-evidence tags, ambiguity scope, and primary review notes. |
| 2026-06-20 | Pilot git visibility after hardening | `git check-ignore -v data/eval/legal_qa_benchmark/pilot/benchmark_queries.jsonl` and equivalent commands for the other four pilot JSONL files | Completed | Each pilot data file matched a narrow negated `.gitignore` rule and remains visible to Git. |
| 2026-06-20 | Future artifact ignore check | `git check-ignore -v --no-index data/eval/legal_qa_benchmark/split_manifest.json`, `git check-ignore -v --no-index data/eval/legal_qa_benchmark/benchmark_manifest.json`, and `git check-ignore -v --no-index artifacts/reports/evaluation/smoke.json` | Completed | Future manifest paths and runtime JSON reports remain ignored unless a later scoped task adds explicit policy exceptions. |
| 2026-06-20 | Validator help smoke after pilot hardening | `uv run python scripts/evaluation/validate_benchmark.py --help` | Passed | Help text displayed; no benchmark files loaded. |
| 2026-06-20 | Corpus-aware pilot validation after hardening | `uv run python scripts/evaluation/validate_benchmark.py --queries data/eval/legal_qa_benchmark/pilot/benchmark_queries.jsonl --legal-targets data/eval/legal_qa_benchmark/pilot/benchmark_targets.jsonl --evidence-judgments data/eval/legal_qa_benchmark/pilot/benchmark_qrels.jsonl --evidence-groups data/eval/legal_qa_benchmark/pilot/evidence_groups.jsonl --review-records data/eval/legal_qa_benchmark/pilot/review_records.jsonl --config configs/evaluation/legal_qa_benchmark.yml --corpus-registry configs/laws/corpus_registry.yml --processed-chunks data/processed/legal_chunks.jsonl --output /tmp/vnlaw_pilot_validation_report.json` | Passed | 0 errors, 2 expected warnings for unsplit regression-overlap bridge cases. |
| 2026-06-20 | Pilot coverage recomputation | `uv run python - <<'PY' ... recompute coverage from benchmark_queries.jsonl ... PY` | Completed | Confirmed 19 queries, 17 answer-allowed, 2 fallback-required, 7 complete-evidence cases, 14 blocking cases, 2 regression bridges, and 0 temporal cases. |
| 2026-06-20 | Python compile after pilot hardening | `uv run python -m py_compile src/evaluation/benchmark/*.py scripts/evaluation/*.py` | Passed | Stage C benchmark modules and CLI wrappers still compile. |
| 2026-06-20 | Evaluation unit tests after pilot hardening | `uv run pytest tests/unit/evaluation -q` | Passed | 67 passed. |
| 2026-06-20 | Evaluation integration tests after pilot hardening | `uv run pytest tests/integration/evaluation -q` | Passed | 1 passed. |
| 2026-06-20 | Retrieval unit regression tests after pilot hardening | `uv run pytest tests/unit/retrieval -q` | Passed | 173 passed; no Qdrant or OpenRouter calls. |
| 2026-06-20 | Ruff lint after pilot hardening | `uv run ruff check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | All checks passed. |
| 2026-06-20 | Ruff format check after pilot hardening | `uv run ruff format --check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | 19 files already formatted. |
| 2026-06-20 | Lockfile check after pilot hardening | `uv lock --check` | Passed | Resolved 130 packages; lockfile unchanged. |
| 2026-06-20 | Pilot record counts after hardening | `wc -l data/eval/legal_qa_benchmark/pilot/benchmark_queries.jsonl data/eval/legal_qa_benchmark/pilot/benchmark_targets.jsonl data/eval/legal_qa_benchmark/pilot/benchmark_qrels.jsonl data/eval/legal_qa_benchmark/pilot/evidence_groups.jsonl data/eval/legal_qa_benchmark/pilot/review_records.jsonl` | Passed | 19 queries, 47 targets, 47 qrels, 39 evidence groups, 19 review records. |
| 2026-06-20 | Diff hygiene after pilot hardening | `git diff --check` | Passed | No whitespace errors after Stage D1 hardening. |
| 2026-06-20 | D2 pre-edit worktree | `git status --short` | Passed | No output; worktree was clean before structured independent review. |
| 2026-06-20 | D2 evidence-first review inventory | `uv run python - <<'PY' ... print query, targets, groups, qrels, and chunk text ... PY` | Completed | Read-only review of all pilot records and exact child chunks. |
| 2026-06-20 | D2 focus-case sibling inspection | `uv run python - <<'PY' ... inspect same-article sibling chunks for focus cases ... PY` | Completed | Found `pilot_0003` scope issue around Article 107 Clause 3 parent-header evidence. |
| 2026-06-20 | Validator help smoke after D2 | `uv run python scripts/evaluation/validate_benchmark.py --help` | Passed | Help text displayed; no benchmark files loaded. |
| 2026-06-20 | Corpus-aware pilot validation after D2 | `uv run python scripts/evaluation/validate_benchmark.py --queries data/eval/legal_qa_benchmark/pilot/benchmark_queries.jsonl --legal-targets data/eval/legal_qa_benchmark/pilot/benchmark_targets.jsonl --evidence-judgments data/eval/legal_qa_benchmark/pilot/benchmark_qrels.jsonl --evidence-groups data/eval/legal_qa_benchmark/pilot/evidence_groups.jsonl --review-records data/eval/legal_qa_benchmark/pilot/review_records.jsonl --config configs/evaluation/legal_qa_benchmark.yml --corpus-registry configs/laws/corpus_registry.yml --processed-chunks data/processed/legal_chunks.jsonl --output /tmp/vnlaw_pilot_d2_validation_report.json` | Passed | 0 errors, 2 expected warnings for unsplit regression-overlap bridge cases. |
| 2026-06-20 | D2 review audit | `uv run python - <<'PY' ... audit query review stages, conflicts, adjudications, frozen and assigned queries ... PY` | Passed | 19 primary records, 19 independent records, 1 adjudication record, 0 conflicts, 0 frozen queries, 0 assigned queries. |
| 2026-06-20 | D2 record counts | `wc -l data/eval/legal_qa_benchmark/pilot/benchmark_queries.jsonl data/eval/legal_qa_benchmark/pilot/benchmark_targets.jsonl data/eval/legal_qa_benchmark/pilot/benchmark_qrels.jsonl data/eval/legal_qa_benchmark/pilot/evidence_groups.jsonl data/eval/legal_qa_benchmark/pilot/review_records.jsonl` | Passed | 19 queries, 47 targets, 47 qrels, 39 evidence groups, 39 review records. |
| 2026-06-20 | Python compile after D2 | `uv run python -m py_compile src/evaluation/benchmark/*.py scripts/evaluation/*.py` | Passed | Stage C benchmark modules and CLI wrappers still compile. |
| 2026-06-20 | Evaluation unit tests after D2 | `uv run pytest tests/unit/evaluation -q` | Passed | 67 passed. |
| 2026-06-20 | Evaluation integration tests after D2 | `uv run pytest tests/integration/evaluation -q` | Passed | 1 passed. |
| 2026-06-20 | Retrieval unit regression tests after D2 | `uv run pytest tests/unit/retrieval -q` | Passed | 173 passed; no Qdrant or OpenRouter calls. |
| 2026-06-20 | Ruff lint after D2 | `uv run ruff check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | All checks passed. |
| 2026-06-20 | Ruff format check after D2 | `uv run ruff format --check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | 19 files already formatted. |
| 2026-06-20 | Lockfile check after D2 | `uv lock --check` | Passed | Resolved 130 packages; lockfile unchanged. |
| 2026-06-20 | Diff hygiene after D2 | `git diff --check` | Passed | No whitespace errors after structured independent review and adjudication. |
| 2026-06-21 | Stage D stabilization pre-edit worktree | `git status --short` | Completed | Existing uncommitted D2 changes were present in pilot docs/data and benchmark docs/tracer. |
| 2026-06-21 | D2 review-history audit before stabilization | `uv run python - <<'PY' ... audit pilot review records and pilot_0003 history ... PY` | Passed | 19 queries, 19 primary records, 19 independent records, 1 adjudication record, 0 conflicts, 0 frozen queries, 0 assigned queries. |
| 2026-06-21 | Validator help smoke during stabilization | `uv run python scripts/evaluation/validate_benchmark.py --help` | Passed | Help text displayed; no benchmark files loaded. |
| 2026-06-21 | Corpus-aware pilot validation after stabilization | `uv run python scripts/evaluation/validate_benchmark.py --queries data/eval/legal_qa_benchmark/pilot/benchmark_queries.jsonl --legal-targets data/eval/legal_qa_benchmark/pilot/benchmark_targets.jsonl --evidence-judgments data/eval/legal_qa_benchmark/pilot/benchmark_qrels.jsonl --evidence-groups data/eval/legal_qa_benchmark/pilot/evidence_groups.jsonl --review-records data/eval/legal_qa_benchmark/pilot/review_records.jsonl --config configs/evaluation/legal_qa_benchmark.yml --corpus-registry configs/laws/corpus_registry.yml --processed-chunks data/processed/legal_chunks.jsonl --output /tmp/vnlaw_pilot_stabilization_validation_report.json` | Passed | 0 errors, 2 expected warnings for unsplit regression-overlap bridge cases. |
| 2026-06-21 | Stabilization review audit | `uv run python - <<'PY' ... audit review stages, statuses, reviewer_kind, and review_assurance ... PY` | Passed | 19 primary records, 19 independent records, 1 adjudication record, 18 independent-reviewed queries, 1 adjudicated query, 0 frozen and 0 assigned queries. |
| 2026-06-21 | Python compile after stabilization | `uv run python -m py_compile src/evaluation/benchmark/*.py scripts/evaluation/*.py` | Passed | Stage C benchmark modules and CLI wrappers compile. |
| 2026-06-21 | Evaluation unit tests after stabilization | `uv run pytest tests/unit/evaluation -q` | Passed | 68 passed. |
| 2026-06-21 | Evaluation integration tests after stabilization | `uv run pytest tests/integration/evaluation -q` | Passed | 1 passed. |
| 2026-06-21 | Retrieval unit regression tests after stabilization | `uv run pytest tests/unit/retrieval -q` | Passed | 173 passed; no Qdrant or OpenRouter calls. |
| 2026-06-21 | Ruff lint before import-order fix | `uv run ruff check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Failed then corrected | Reported import-order issues in `src/evaluation/benchmark/__init__.py`, `src/evaluation/benchmark/schemas.py`, and `tests/unit/evaluation/benchmark/test_schemas.py`. |
| 2026-06-21 | Ruff import-order fix | `uv run ruff check src/evaluation/benchmark/__init__.py src/evaluation/benchmark/schemas.py tests/unit/evaluation/benchmark/test_schemas.py --fix` | Passed | Fixed 3 import-order issues only. |
| 2026-06-21 | Ruff lint after stabilization | `uv run ruff check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | All checks passed. |
| 2026-06-21 | Ruff format check after stabilization | `uv run ruff format --check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | 19 files already formatted. |
| 2026-06-21 | Lockfile check after stabilization | `uv lock --check` | Passed | Resolved 130 packages; lockfile unchanged. |
| 2026-06-21 | Pilot record counts after stabilization | `wc -l data/eval/legal_qa_benchmark/pilot/benchmark_queries.jsonl data/eval/legal_qa_benchmark/pilot/benchmark_targets.jsonl data/eval/legal_qa_benchmark/pilot/benchmark_qrels.jsonl data/eval/legal_qa_benchmark/pilot/evidence_groups.jsonl data/eval/legal_qa_benchmark/pilot/review_records.jsonl` | Passed | 19 queries, 47 targets, 47 qrels, 39 evidence groups, 39 review records. |
| 2026-06-21 | Manifest absence check | `find data/eval/legal_qa_benchmark -maxdepth 2 \( -name split_manifest.json -o -name benchmark_manifest.json \) -print` | Passed | No split or benchmark manifest was found. |
| 2026-06-21 | Protected-path status check | `git status --short data/raw data/interim data/reports data/processed/legal_chunks.jsonl data/eval/manual_retrieval_queries.jsonl data/eval/manual_naive_rag_generation_queries.jsonl data/eval/manual_faithfulness_verdicts.json configs/retrieval/quality_gate.yml` | Passed | No protected corpus path, regression asset, or quality-gate config changes. |
| 2026-06-21 | Diff hygiene after stabilization | `git diff --check` | Passed | No whitespace errors after Stage D stabilization. |
| 2026-06-21 | D2 review-assurance wording audit | `rg -n "independent legal review\|qualified human\|human legal review\|expert-reviewed\|lawyer-reviewed\|legally validated\|needs_human_legal_review\|independent_reviewed\|adjudicated\|review assurance\|held-out\|high-risk" docs data/eval/legal_qa_benchmark/pilot` | Completed | Found soft high-risk held-out wording and review metadata that could imply human review was unnecessary. |
| 2026-06-21 | Pilot non-frozen audit after D2 hardening | `uv run python - <<'PY' ... audit split, frozen status, and manifest absence ... PY` | Passed | 19 queries, 0 assigned queries, 0 frozen queries, no split manifest, no benchmark manifest. |
| 2026-06-21 | Corpus-aware pilot validation after D2 hardening | `uv run python scripts/evaluation/validate_benchmark.py --queries data/eval/legal_qa_benchmark/pilot/benchmark_queries.jsonl --legal-targets data/eval/legal_qa_benchmark/pilot/benchmark_targets.jsonl --evidence-judgments data/eval/legal_qa_benchmark/pilot/benchmark_qrels.jsonl --evidence-groups data/eval/legal_qa_benchmark/pilot/evidence_groups.jsonl --review-records data/eval/legal_qa_benchmark/pilot/review_records.jsonl --config configs/evaluation/legal_qa_benchmark.yml --corpus-registry configs/laws/corpus_registry.yml --processed-chunks data/processed/legal_chunks.jsonl --output /tmp/vnlaw_pilot_d2_hardening_validation_report.json` | Passed | 0 errors, 2 expected warnings for unsplit regression-overlap bridge cases. |
| 2026-06-21 | Python compile after D2 hardening | `uv run python -m py_compile src/evaluation/benchmark/*.py scripts/evaluation/*.py` | Passed | Stage C benchmark modules and CLI wrappers compile. |
| 2026-06-21 | Evaluation unit tests after D2 hardening | `uv run pytest tests/unit/evaluation -q` | Passed | 68 passed. |
| 2026-06-21 | Evaluation integration tests after D2 hardening | `uv run pytest tests/integration/evaluation -q` | Passed | 1 passed. |
| 2026-06-21 | Retrieval unit regression tests after D2 hardening | `uv run pytest tests/unit/retrieval -q` | Passed | 173 passed; no Qdrant or OpenRouter calls. |
| 2026-06-21 | Ruff lint after D2 hardening | `uv run ruff check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | All checks passed. |
| 2026-06-21 | Ruff format check after D2 hardening | `uv run ruff format --check src/evaluation scripts/evaluation tests/unit/evaluation tests/integration/evaluation` | Passed | 19 files already formatted. |
| 2026-06-21 | Lockfile check after D2 hardening | `uv lock --check` | Passed | Resolved 130 packages; lockfile unchanged. |
| 2026-06-21 | Pilot record counts after D2 hardening | `wc -l data/eval/legal_qa_benchmark/pilot/benchmark_queries.jsonl data/eval/legal_qa_benchmark/pilot/benchmark_targets.jsonl data/eval/legal_qa_benchmark/pilot/benchmark_qrels.jsonl data/eval/legal_qa_benchmark/pilot/evidence_groups.jsonl data/eval/legal_qa_benchmark/pilot/review_records.jsonl` | Passed | 19 queries, 47 targets, 47 qrels, 39 evidence groups, 39 review records. |
| 2026-06-21 | Manifest absence check after D2 hardening | `find data/eval/legal_qa_benchmark -maxdepth 2 \( -name split_manifest.json -o -name benchmark_manifest.json \) -print` | Passed | No split or benchmark manifest was found. |
| 2026-06-21 | Protected-path status check after D2 hardening | `git status --short data/raw data/interim data/reports data/processed/legal_chunks.jsonl data/eval/manual_retrieval_queries.jsonl data/eval/manual_naive_rag_generation_queries.jsonl data/eval/manual_faithfulness_verdicts.json configs/retrieval/quality_gate.yml` | Passed | No protected corpus path, regression asset, or quality-gate config changes. |
| 2026-06-21 | Diff hygiene after D2 hardening | `git diff --check` | Passed | No whitespace errors after D2 review-assurance hardening. |

## Change Log

| Date | Change | Files | Author or tool |
| --- | --- | --- | --- |
| 2026-06-19 | Created temporary Phase 10 progress tracer after read-only repository inspection. | `docs/phase10_tracer.md` | Codex |
| 2026-06-19 | Created durable legal QA evaluation protocol and marked Stage B progress. | `docs/evaluation_protocol.md`, `docs/phase10_tracer.md` | Codex |
| 2026-06-19 | Clarified Stage B protocol semantics for direct evidence, hard violations, fallback consistency, field names, duplicate normalization, and evidence-group references. | `docs/evaluation_protocol.md`, `docs/phase10_tracer.md` | Codex |
| 2026-06-19 | Implemented Stage C benchmark schemas, loaders, validator, grouped splitting, fingerprinting, CLI wrappers, tests, config, and technical docs. | `src/evaluation/benchmark/`, `scripts/evaluation/`, `configs/evaluation/legal_qa_benchmark.yml`, `tests/unit/evaluation/benchmark/`, `tests/integration/evaluation/test_benchmark_workflow.py`, `docs/legal_qa_benchmark.md`, `docs/phase10_tracer.md` | Codex |
| 2026-06-19 | Hardened Stage C protocol invariants, split/review source-of-truth checks, raw and canonical fingerprints, qrel/group consistency, and freeze immutability. | `src/evaluation/benchmark/`, `tests/unit/evaluation/benchmark/`, `docs/legal_qa_benchmark.md`, `docs/phase10_tracer.md`, `configs/evaluation/legal_qa_benchmark.yml` | Codex |
| 2026-06-20 | Created Stage D1 draft pilot annotation and coverage summary for independent review preparation. | `data/eval/legal_qa_benchmark/pilot/`, `.gitignore`, `docs/phase10_tracer.md` | Codex |
| 2026-06-20 | Hardened Stage D1 pilot semantics for temporal wording, multi-evidence tags, ambiguous fallback scope, review questions, and tracer freshness. | `data/eval/legal_qa_benchmark/pilot/`, `docs/phase10_tracer.md` | Codex |
| 2026-06-20 | Completed structured D2 independent review, adjudicated the `pilot_0003` scope conflict, and documented review limitations. | `data/eval/legal_qa_benchmark/pilot/`, `docs/legal_qa_benchmark.md`, `docs/phase10_tracer.md` | Codex |
| 2026-06-21 | Completed Stage D stabilization, added review-assurance metadata, froze schema contract version `1.0`, and documented stabilization limits. | `src/evaluation/benchmark/`, `tests/unit/evaluation/benchmark/`, `docs/evaluation_protocol.md`, `docs/legal_qa_benchmark.md`, `docs/phase10_tracer.md`, `data/eval/legal_qa_benchmark/pilot/` | Codex |
| 2026-06-21 | Hardened D2 review-assurance wording and made high-risk held-out qualified-review policy mandatory. | `docs/evaluation_protocol.md`, `docs/legal_qa_benchmark.md`, `docs/phase10_tracer.md`, `data/eval/legal_qa_benchmark/pilot/` | Codex |

## Exit Criteria

Phase 10 can close only after:

- broader legally reviewed benchmark completed;
- deterministic dev/test split frozen;
- held-out test protected from tuning;
- benchmark and baseline manifests fingerprinted;
- frozen Naive RAG baseline recorded;
- dense, hybrid, and reranking variants evaluated as controlled comparisons;
- retrieval, safety, generation, and operational metrics reported;
- unsupported claims do not increase beyond accepted policy;
- blocking cases meet the approved gate;
- wins, losses, regressions, latency, and cost are documented;
- a justified adoption or rejection decision is recorded;
- durable documentation is consolidated;
- this tracer is removed or archived.

## Next Immediate Action

```text
documentation consolidation
-> full benchmark construction planning
-> annotation workload and qualified-review allocation
-> full benchmark construction
```

Sparse retrieval, RRF, and reranking must not begin yet.
