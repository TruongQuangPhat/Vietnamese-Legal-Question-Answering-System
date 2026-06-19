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

Verified repository state as of 2026-06-19:

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
- Current Phase 10 stage: repository inspection and progress tracing only.
  Benchmark protocol, benchmark schemas, validators, sparse retrieval, fusion,
  and reranking are not implemented in this task.

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
| `src/evaluation/.gitkeep` | Future broader evaluation scaffold | Yes, for future benchmark layer | Yes | Inspected; no implementation exists yet. |
| `configs/evaluation/.gitkeep` | Future evaluation config scaffold | Yes, for future benchmark configs | Yes | Inspected; no implementation exists yet. |
| `tests/unit/evaluation/.gitkeep` | Future evaluation test scaffold | Yes, for future benchmark tests | Yes | Inspected; no implementation exists yet. |
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

- [ ] Pydantic schema models;
- [ ] loaders;
- [ ] validators;
- [ ] grouped split implementation;
- [ ] fingerprinting;
- [ ] CLI wrappers;
- [ ] unit tests;
- [ ] integration tests;
- [ ] configuration;
- [ ] technical documentation.

### Stage D - Pilot Annotation

- [ ] 15-20 pilot queries;
- [ ] coverage of difficult question types;
- [ ] primary annotation;
- [ ] independent review;
- [ ] adjudication;
- [ ] schema revision;
- [ ] protocol revision;
- [ ] schema version freeze.

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
| Evaluation configuration | `configs/evaluation/` | Scaffold exists; no new files created | Benchmark protocol | Use functional config names only. |
| Legal QA benchmark data | `data/eval/legal_qa_benchmark/` | Planned; not created | Approved schema, annotation workflow | Must not invent legal expectations. |
| Benchmark schema and loaders | `src/evaluation/benchmark/` | Planned; not created | Protocol and schema approval | Keep broader evaluation separate from current baseline logic. |
| Evaluation metrics | `src/evaluation/metrics/` | Planned; not created | Metric definitions | Include retrieval, decision/safety, generation, and operational metrics. |
| Evaluation reporting | `src/evaluation/reporting/` | Planned; not created | Report schema and manifest design | Reports must include dataset version and fingerprints. |
| Evaluation CLIs | `scripts/evaluation/` | Planned; directory not present | Reusable services under `src/evaluation/` | CLI wrappers must stay thin. |
| Unit tests | `tests/unit/evaluation/` | Scaffold exists; no new files created | Implemented schemas/loaders/metrics | Mirror source modules. |
| Integration tests | `tests/integration/evaluation/` | Planned; not present | End-to-end benchmark workflow | Avoid external service calls unless explicitly scoped. |
| Benchmark documentation | `docs/legal_qa_benchmark.md` | Planned; not created | Protocol and schema freeze | Functional durable documentation after tracer work. |
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

## Risks and Open Questions

Confirmed risks:

- Benchmark annotation cost may be high.
- Legal review coverage may be insufficient without a clear review workflow.
- Complete-list questions require evidence-group and completeness semantics.
- Paraphrase and source-provision leakage can invalidate dev/test splits.
- Embedding model revision is currently nullable in `configs/retrieval/retrieval.yml`.
- Generation output can be non-deterministic even with fixed prompts and inputs.
- Sparse index design is not selected.
- Held-out test contamination remains a risk if test queries are inspected for
  tuning.
- Latency and cost may regress when sparse retrieval, fusion, or reranking are
  added.

Open design questions:

- What minimum and preferred benchmark sizes will be approved?
- What final domain quotas will be approved for the registry-derived taxonomy?
- Whether secondary domains should be required for every cross-law case or only
  where needed for stratification.
- How should complete-evidence groups be encoded and adjudicated?
- What exact relevance gain values should be used for nDCG?
- What numeric relevance gain, if any, should be assigned to supporting
  evidence after metric implementation defines contextual usefulness?
- What exact blocking-case thresholds should gate system comparison?
- Whether `fallback_reason` categories fully cover pilot cases before Stage C
  freezes an enum.
- What manual-review threshold should flag diacritic-sensitive near-duplicates
  without automatically merging Vietnamese legal queries.
- What reviewer identifier format should be used without exposing unnecessary
  personal information?
- Who will staff adjudication for legal-review conflicts?
- What benchmark versioning convention should be used?
- Which deterministic fingerprint fields are required for corpus, chunks,
  Qdrant collection, prompts, and model configuration?
- Whether sparse retrieval should use Qdrant sparse vectors, BM25 outside
  Qdrant, or BGE-M3 sparse output in a separately scoped implementation.
- Which reranker, if any, is acceptable after the benchmark is frozen.

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

## Change Log

| Date | Change | Files | Author or tool |
| --- | --- | --- | --- |
| 2026-06-19 | Created temporary Phase 10 progress tracer after read-only repository inspection. | `docs/phase10_tracer.md` | Codex |
| 2026-06-19 | Created durable legal QA evaluation protocol and marked Stage B progress. | `docs/evaluation_protocol.md`, `docs/phase10_tracer.md` | Codex |
| 2026-06-19 | Clarified Stage B protocol semantics for direct evidence, hard violations, fallback consistency, field names, duplicate normalization, and evidence-group references. | `docs/evaluation_protocol.md`, `docs/phase10_tracer.md` | Codex |

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
benchmark schema design
-> benchmark validator design
-> Stage C implementation
-> pilot annotation
```

Sparse retrieval, RRF, and reranking must not begin yet.
