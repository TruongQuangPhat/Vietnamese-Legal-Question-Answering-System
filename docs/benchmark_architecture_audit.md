# Benchmark Architecture Audit

## Scope

This audit maps the repository benchmark and evaluation architecture after the
direct-evidence quality work on
`feature/retrieval-evidence-quality-direct-article-priority`. It was produced
from static repository inspection only. No benchmark runner was executed, no
BGE-M3 model was loaded, no Qdrant service was queried, no production endpoint
was called, and no protected dataset or official evaluation artifact was
modified.

The main risk reviewed here is whether the branch additions created a second
benchmark framework that conflicts with the existing Naive RAG and Advanced RAG
benchmark infrastructure.

## Canonical Architecture

The pre-existing canonical benchmark architecture remains:

```text
Frozen benchmark case registry
  data/eval/legal_qa_benchmark/*
        |
Shared schemas, loader, validators, metrics, and pipeline evaluators
  src/evaluation/benchmark/*
        |
Pipeline-specific thin runners
  scripts/evaluation/*
        |
Official generated reports
  artifacts/reports/evaluation/*
```

The branch direct-evidence benchmark is now located in
`src/evaluation/benchmark/direct_evidence.py`. The old
`src/evaluation/retrieval_quality_generalization.py` path is a compatibility
shim only. This keeps reusable metric and runner logic inside the canonical
benchmark package instead of maintaining a parallel `src/evaluation/*` module
with separate concepts.

The direct-evidence suite is a deterministic diagnostic and regression suite for
strict primary-evidence and citation-alignment behavior. It is not the frozen
v0.1.0 benchmark and must not be used as a replacement for the official
Naive/Advanced RAG reports under `artifacts/reports/evaluation/`.

## Canonical Evaluation Core Map

| Concept | Canonical implementation | Legacy or alternate implementation | Still called | Disposition |
| --- | --- | --- | --- | --- |
| Frozen benchmark case schema | `src/evaluation/benchmark/schemas.py::BenchmarkQuery` | Direct-evidence diagnostic `BenchmarkCase` | Yes, by separate suites | Keep separate until direct-evidence cases are promoted through the protected freeze workflow. |
| Direct-evidence diagnostic case schema | `src/evaluation/benchmark/direct_evidence.py::BenchmarkCase` | Test-local case dataclasses | Yes, tests only | Keep as fixtures only; target locators use canonical `EvidenceTarget` where metric semantics matter. |
| Frozen expected legal target schema | `src/evaluation/benchmark/schemas.py::LegalTarget` and `LegalTargetReference` | `src/retrieval/evaluation.py::ExpectedTarget` strict-generation adapter | Yes | Keep; these serve frozen benchmark and generation-evaluation contracts. |
| Direct-evidence expected target schema | `src/evaluation/benchmark/direct_evidence.py::EvidenceTarget` | Local-hybrid dict targets and hybrid-fixture `Target` dataclass | Local-hybrid dict targets and hybrid-fixture `Target` removed | Canonical for direct-evidence diagnostics and local hybrid validation. |
| Frozen retrieval metric contracts | `src/evaluation/benchmark/retrieval_baseline.py` | Direct-evidence metric functions | Yes | Keep namespaced. Frozen metrics are qrels/evidence-group retrieval metrics. |
| Direct-evidence metric contracts | `src/evaluation/benchmark/direct_evidence.py::metric_definitions` and `compute_aggregate_metrics` | Local-hybrid local aggregation | Local-hybrid now converts cases into canonical metric rows | Canonical for direct-evidence diagnostics and local hybrid validation. |
| Frozen per-case retrieval result | `src/evaluation/benchmark/retrieval_baseline.py::evaluate_case_retrieval` | Direct-evidence `CaseEvaluation` | Yes | Keep separate because the oracles differ. |
| Direct-evidence per-case result | `src/evaluation/benchmark/direct_evidence.py::CaseEvaluation` plus canonical target summary helpers | Local-hybrid independently parsed ranks and matching | Local-hybrid now reuses canonical parsing, matching, summaries, and metrics | Canonical for branch diagnostics. |
| Frozen aggregate benchmark result | `aggregate_case_metrics`, `aggregate_generation_metrics`, and strict-generation aggregators | Direct-evidence aggregate metrics | Yes | Keep separate and namespaced because denominators differ. |
| Direct-evidence aggregate result | `src/evaluation/benchmark/direct_evidence.py::compute_aggregate_metrics` | Local-hybrid aggregate pass fields | Local-hybrid now calls canonical aggregate metrics | Canonical for direct-evidence diagnostics. |
| Benchmark metadata | Frozen manifests and artifact writers | Branch diagnostic JSON metadata | Yes | Direct-evidence now uses `DirectEvidenceReportMetadata`; official artifacts keep existing manifest schema. |
| Direct-evidence compatibility checking | `src/evaluation/benchmark/direct_evidence.py::validate_report_compatibility` | Previous loose same-shape comparison | Yes, via `compare_reports` | Canonical; comparisons reject incompatible schema, contract, corpus, case set, granularity, stage, mode, and cutoffs. |
| Result comparison | Official frozen comparison helpers and direct-evidence `compare_reports` | Previous direct-evidence loose comparison | Yes | Keep separate because official comparisons use frozen metrics and direct-evidence compares selected-primary/citation regressions. |

The repository therefore has one canonical implementation for each concept
within its owning evaluation family. Where frozen benchmark and direct-evidence
diagnostics intentionally differ, metric names and metadata contracts are
namespaced and comparison is rejected across incompatible envelopes.

## Path Status

| Path | Status | Notes |
| --- | --- | --- |
| `configs/evaluation/legal_qa_benchmark.yml` | Active configuration | Canonical frozen benchmark file locations and default output roots. |
| `data/eval/legal_qa_benchmark/*` | Active protected case registry | Frozen v0.1.0 queries, targets, qrels, evidence groups, review records, split and benchmark manifests. |
| `src/evaluation/benchmark/*` | Active shared library | Canonical schemas, loaders, validators, retrieval metrics, generation metrics, ablations, diagnostics, and direct-evidence diagnostics. |
| `scripts/evaluation/*` | Active thin runners and analysis CLIs | Pipeline-specific wrappers over `src/evaluation/benchmark/*`. |
| `scripts/retrieval/*` | Historical/manual retrieval CLIs | Useful for manual Naive RAG diagnostics and dense/sparse retrieval checks; not the frozen benchmark framework. |
| `src/retrieval/generation_evaluation.py` and `src/retrieval/quality_gate.py` | Historical/manual evaluation helpers | Support Naive RAG generation checks and quality gates outside the frozen benchmark package. |
| `artifacts/reports/evaluation/*` | Generated artifacts | Official historical report outputs; read-only for this task. |
| `docs/evaluation.md`, `docs/advanced_rag.md`, `docs/naive_rag.md` | Documentation | Durable evaluation references for frozen, Advanced RAG, and historical Naive RAG results. |

## Component Inventory

| ID | File/path | Type | Active entry point | Pipeline | Dataset/cases | Metrics | Output schema | External dependencies | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B01 | `configs/evaluation/legal_qa_benchmark.yml` | configuration | No | Frozen benchmark config | `data/eval/legal_qa_benchmark` | References shared metrics | YAML config | None | Active |
| B02 | `data/eval/legal_qa_benchmark/*` | case registry | No | Naive and Advanced RAG | Frozen v0.1.0 | Ground-truth targets, qrels, evidence groups | JSONL/JSON manifests | None | Active protected |
| B03 | `src/evaluation/benchmark/schemas.py` | shared library | No | Naive and Advanced RAG | Frozen benchmark | Typed benchmark, target, evidence, and review schemas | Pydantic models | None | Active |
| B04 | `src/evaluation/benchmark/loader.py` | shared library | No | Naive and Advanced RAG | Frozen benchmark | None | Typed loaded dataset | File I/O | Active |
| B05 | `src/evaluation/benchmark/validator.py` | shared library | Via `scripts/evaluation/validate_benchmark.py` | Benchmark validation | Frozen benchmark | Manifest and data consistency | JSON summary | None | Active |
| B06 | `src/evaluation/benchmark/splitting.py` | shared library | Via split/freeze scripts | Benchmark maintenance | Frozen benchmark | Split assignment metadata | JSON manifest | None | Active |
| B07 | `src/evaluation/benchmark/retrieval_baseline.py` | metric implementation | Indirect | Dense, sparse, hybrid, coverage-aware | Frozen benchmark | Recall@k, required direct coverage, evidence group coverage, MRR@10, NDCG@10 | Case metrics dicts | None | Active canonical retrieval metrics |
| B08 | `src/evaluation/benchmark/generation_baseline.py` | metric implementation | Indirect | Generation | Frozen benchmark | Decision accuracy, citation validity, fallback behavior, evidence coverage, error counts | Case metrics dicts | LLM result inputs | Active canonical generation metrics |
| B09 | `src/evaluation/benchmark/sparse_retrieval_baseline.py` | shared runner core and artifact writer | Via sparse runner | Advanced sparse retrieval | Frozen benchmark | Uses B07 | `case_results.jsonl`, `metrics_*.json`, `breakdowns.json`, `baseline_manifest.json`, `summary.md` | Local processed chunks | Active |
| B10 | `src/evaluation/benchmark/hybrid_retrieval_baseline.py` | shared runner core and artifact writer | Via hybrid runner | Advanced dense+sparse RRF | Frozen benchmark | Uses B07 | Same frozen retrieval artifact layout plus comparison | BGE-M3 and read-only Qdrant through injected retriever | Active |
| B11 | `src/evaluation/benchmark/fusion_ablation.py` | shared runner core | Via fusion and coverage-aware runners | Advanced hybrid and coverage-aware ablations | Frozen benchmark | Uses B07 | Ablation case metrics, manifests, summaries | May use BGE-M3 and read-only Qdrant | Active |
| B12 | `src/evaluation/benchmark/reranking_ablation.py` | shared runner core | Via reranking runner | Advanced reranking ablation | Frozen benchmark | Uses B07 | Ablation report artifacts | Dense/sparse candidates and local reranker when executed | Active historical ablation |
| B13 | `src/evaluation/benchmark/strict_generation_evaluation.py` | shared runner core and artifact writer | Via strict generation runner | Coverage-aware retrieval plus strict generation | Frozen benchmark | Uses B08 and retrieval error accounting | Strict generation report artifacts | LLM client injected by runner; retrieval result inputs | Active |
| B14 | `src/evaluation/benchmark/evidence_selection_diagnostics.py` | analysis library | Via diagnostics analyzer | Evidence selection diagnostics | Advanced report artifacts | Selection and fallback diagnostics | JSON/Markdown analysis | Existing report files | Active analysis |
| B15 | `src/evaluation/benchmark/strict_generation_error_analysis.py` | analysis library | Via error analyzer | Strict generation error analysis | Advanced strict generation artifacts | Error grouping and summaries | JSON/Markdown analysis | Existing report files | Active analysis |
| B16 | `scripts/evaluation/validate_benchmark.py` | runner | Yes | Benchmark validation | Frozen benchmark | Validation counts and errors | Console/JSON validation output | None | Active thin CLI |
| B17 | `scripts/evaluation/create_benchmark_split.py` | runner | Yes | Benchmark maintenance | Frozen benchmark source files | Split statistics | Split manifest | None | Active maintenance CLI |
| B18 | `scripts/evaluation/freeze_benchmark.py` | runner | Yes | Benchmark maintenance | Benchmark source files | Manifest validation | Frozen benchmark files | None | Active maintenance CLI |
| B19 | `scripts/evaluation/run_frozen_retrieval_baseline.py` | runner | Yes | Naive dense retrieval baseline | Frozen benchmark | Uses B07 | Official retrieval baseline artifacts | BGE-M3 and read-only Qdrant when executed | Active historical Naive RAG baseline |
| B20 | `scripts/evaluation/run_frozen_generation_baseline.py` | runner | Yes | Naive generation baseline | Frozen benchmark | Uses B08 | Official generation baseline artifacts | External LLM when executed | Active historical Naive RAG baseline |
| B21 | `scripts/evaluation/run_frozen_sparse_retrieval_baseline.py` | runner | Yes | Advanced sparse retrieval | Frozen benchmark | Uses B07 | Official sparse retrieval artifacts | Local processed chunks | Active |
| B22 | `scripts/evaluation/run_frozen_hybrid_retrieval_baseline.py` | runner | Yes | Advanced dense+sparse RRF | Frozen benchmark | Uses B07 | Official hybrid retrieval artifacts | BGE-M3 and read-only Qdrant when executed | Active |
| B23 | `scripts/evaluation/run_fusion_ablation.py` | runner | Yes | Advanced fusion ablation | Frozen benchmark | Uses B07 | Official ablation artifacts | May use BGE-M3 and read-only Qdrant | Active historical ablation |
| B24 | `scripts/evaluation/run_coverage_aware_hybrid_retrieval.py` | runner | Yes | Adopted coverage-aware hybrid retrieval | Frozen benchmark | Uses B07 | Official coverage-aware retrieval artifacts | BGE-M3 and read-only Qdrant when executed | Active adopted retrieval evaluation |
| B25 | `scripts/evaluation/run_reranking_ablation.py` | runner | Yes | Reranking ablation | Frozen benchmark | Uses B07 | Official ablation artifacts | Dense/sparse retrieval and local reranker when executed | Active historical ablation; reranking not adopted |
| B26 | `scripts/evaluation/run_reranked_retrieval.py` | runner | Yes | Reranked retrieval | Frozen benchmark | Uses B07 | Reranked retrieval artifacts | Dense/sparse retrieval and local reranker when executed | Active historical ablation |
| B27 | `scripts/evaluation/run_strict_generation_evaluation.py` | runner | Yes | Coverage-aware retrieval plus strict generation | Frozen benchmark | Uses B08 | Official strict generation artifacts | External LLM when executed | Active adopted generation evaluation |
| B28 | `scripts/evaluation/analyze_evidence_selection_diagnostics.py` | runner | Yes | Evidence diagnostics | Advanced report artifacts | Diagnostic summaries | JSON/Markdown report | Existing report files | Active analysis |
| B29 | `scripts/evaluation/analyze_strict_generation_errors.py` | runner | Yes | Strict generation error analysis | Advanced strict generation artifacts | Error summaries | JSON/Markdown report | Existing report files | Active analysis |
| B30 | `scripts/retrieval/evaluate_dense_retrieval.py` and related retrieval CLIs | runner | Yes, manual | Naive/manual dense and retrieval diagnostics | Manual cases or processed chunks | Local diagnostic metrics | CLI/JSON outputs | May use BGE-M3 and read-only Qdrant | Historical/manual, not frozen framework |
| B31 | `src/retrieval/generation_evaluation.py` | shared library | Indirect | Naive/manual generation evaluation | Manual results | Citation ID, fallback, secret leakage, answer policy checks | Python dicts | None | Historical/manual helper |
| B32 | `src/retrieval/quality_gate.py` | shared library | Indirect | Naive/manual quality gate | Manual/evaluation artifacts | Quality gate status | Python dicts | Existing artifacts | Historical/manual helper |
| B33 | `artifacts/reports/evaluation/naive_rag_baseline/*` | generated artifact | No | Naive RAG baseline | Frozen/manual historical runs | Historical reported metrics | JSON/Markdown artifacts | None at read time | Generated read-only |
| B34 | `artifacts/reports/evaluation/advanced_rag/*` | generated artifact | No | Advanced RAG evaluations and ablations | Frozen benchmark | Historical reported metrics | JSON/Markdown artifacts | None at read time | Generated read-only |
| B35 | `src/evaluation/benchmark/direct_evidence.py` | shared library | Indirect | Deterministic direct-evidence diagnostics | Branch in-code 30-case suite plus processed corpus | Direct primary evidence, citation alignment, selection cutoff, error-rate metrics | Single JSON report plus comparison JSON | Local processed chunks only for sparse diagnostic run | Active branch diagnostic; canonical package location |
| B36 | `src/evaluation/retrieval_quality_generalization.py` | compatibility shim | No | Direct-evidence diagnostics | Same as B35 | Re-exports B35 | Import compatibility only | None | Thin wrapper; no independent framework |
| B37 | `scripts/evaluation/run_retrieval_quality_generalization_benchmark.py` | runner | Yes | Deterministic sparse plus selection direct-evidence diagnostics | Branch in-code cases, `data/processed/legal_chunks.jsonl` | Uses B35 | JSON to explicit output path, usually `/tmp` | Local processed chunks | Active diagnostic CLI; not official frozen benchmark |
| B38 | `scripts/evaluation/run_local_hybrid_retrieval_validation.py` | runner/tooling | Yes, manual only | Local BGE-M3, read-only Qdrant, sparse, fusion, coverage-aware selection, prompt mapping | One question or JSON/JSONL cases | Per-case target rank, selected evidence, citation mapping pass/fail | JSON to explicit output path, usually `/tmp` | BGE-M3 and read-only local Qdrant when manually executed | Manual validation tool; not a benchmark runner |
| B39 | `tests/unit/evaluation/test_retrieval_quality_generalization.py` | test | Yes via pytest | Direct-evidence metric contracts | Synthetic cases | Metric contract assertions | Pytest result | None | Active regression tests |
| B40 | `tests/integration/retrieval/test_direct_article_priority_workflow.py` | test | Yes via pytest | Sparse-only evidence selection workflow | Synthetic/direct Article 35 cases | Primary and citation behavior | Pytest result | Local chunks or fixtures only | Active regression tests |
| B41 | `tests/integration/retrieval/test_hybrid_generalization_fixture_workflow.py` | test | Yes via pytest | Deterministic hybrid fixture | Synthetic sparse+dense candidates | Fusion cutoff and selection behavior | Pytest result | None | Active fixture tests |
| B42 | `docs/evaluation.md`, `docs/advanced_rag.md`, `docs/naive_rag.md` | documentation | No | Evaluation architecture and historical results | Frozen and historical benchmarks | Descriptive | Markdown | None | Active documentation |
| B43 | `docs/retrieval_quality_generalization_audit.md` | documentation | No | Direct-evidence quality audit | Branch diagnostic cases | Descriptive metrics and limitations | Markdown | None | Active branch documentation |

## Runnable Benchmark and Validation Entry Points

| Entry point | Supported modes | Pipeline | Retrieval/generation scope | Uses BGE-M3 | Queries Qdrant | Calls LLM | Input data | Candidate and evidence cutoffs | Output |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `uv run python scripts/evaluation/validate_benchmark.py ...` | Validation only | Frozen benchmark validation | Data integrity | No | No | No | `data/eval/legal_qa_benchmark/*` | Not applicable | Console/JSON validation output |
| `uv run python scripts/evaluation/run_frozen_retrieval_baseline.py ...` | Dense baseline | Naive dense retrieval | Retrieval only | Yes | Yes, read-only | No | Frozen benchmark plus Qdrant collection | Runner default top-k follows frozen retrieval baseline settings | Official `naive_rag_baseline/retrieval` artifacts |
| `uv run python scripts/evaluation/run_frozen_generation_baseline.py ...` | Generation baseline | Naive generation | Generation over retrieved evidence | No during generation-only evaluation when using retrieval artifacts | No during generation-only evaluation when using retrieval artifacts | Yes | Frozen benchmark plus retrieval artifacts | Evidence selection budget comes from generation/evidence-selection config | Official `naive_rag_baseline/generation` artifacts |
| `uv run python scripts/evaluation/run_frozen_sparse_retrieval_baseline.py ...` | Sparse baseline | Advanced sparse BM25 | Retrieval only | No | No | No | Frozen benchmark plus `data/processed/legal_chunks.jsonl` | Sparse top-k default 10 for official metrics | Official `advanced_rag/sparse_retrieval` artifacts |
| `uv run python scripts/evaluation/run_frozen_hybrid_retrieval_baseline.py ...` | Hybrid RRF | Advanced dense+sparse RRF | Retrieval only | Yes | Yes, read-only | No | Frozen benchmark, processed chunks, Qdrant collection | Dense 50, sparse 50, fused final 10 | Official `advanced_rag/hybrid_retrieval` artifacts and comparison |
| `uv run python scripts/evaluation/run_fusion_ablation.py ...` | Fusion variants | Advanced fusion ablation | Retrieval only | Usually yes for dense variants | Yes for dense variants, read-only | No | Frozen benchmark and retrieval config | Variant-specific, commonly dense 50, sparse 50, final 10 | Official `advanced_rag/fusion_ablation` artifacts |
| `uv run python scripts/evaluation/run_coverage_aware_hybrid_retrieval.py ...` | Coverage-aware variants | Adopted Advanced RAG retrieval | Retrieval only | Yes | Yes, read-only | No | Frozen benchmark and retrieval config | Production-aligned coverage-aware settings, final top 10 | Official `advanced_rag/coverage_aware_retrieval` artifacts |
| `uv run python scripts/evaluation/run_reranking_ablation.py ...` | Reranking variants | Advanced reranking ablation | Retrieval only | Yes for upstream retrieval | Yes for upstream retrieval, read-only | No | Frozen benchmark and retrieval config | Variant-specific top-k and rerank budgets | Official `advanced_rag/reranking_ablation` artifacts |
| `uv run python scripts/evaluation/run_reranked_retrieval.py ...` | Reranked retrieval | Advanced reranked retrieval | Retrieval only | Yes | Yes, read-only | No | Frozen benchmark and retrieval config | Variant-specific top-k and rerank budgets | Reranked retrieval artifacts |
| `uv run python scripts/evaluation/run_strict_generation_evaluation.py ...` | Strict generation | Coverage-aware retrieval plus strict generation | Generation with fallback and citation guards | No when using frozen coverage retrieval artifacts | No when using frozen coverage retrieval artifacts | Yes | Frozen benchmark plus coverage retrieval artifacts | Uses retrieval final top-k from manifest and configured selected-evidence budget | Official `advanced_rag/strict_generation_evaluation*` artifacts |
| `uv run python scripts/evaluation/run_retrieval_quality_generalization_benchmark.py run ...` | `runtime_aligned`, `deep_diagnostic` | Deterministic direct-evidence sparse plus selector diagnostics | Retrieval, evidence selection, prompt citation mapping; no answer generation | No | No | No | Branch in-code cases plus processed chunks | Runtime aligned: diagnostic pool 50, selection input 10, selected evidence 5. Deep diagnostic: diagnostic pool 50, selection input 50, selected evidence 5 | Explicit JSON output path, normally under `/tmp`; not official artifacts |
| `uv run python scripts/evaluation/run_local_hybrid_retrieval_validation.py ...` | Manual read-only validation | Local BGE-M3, Qdrant dense, sparse, fusion, coverage-aware selection, prompt mapping | Retrieval, evidence selection, prompt citation mapping; no answer generation | Yes | Yes, read-only | No | One question or JSON/JSONL case file plus processed chunks and local collection | Defaults: sparse 50, dense 50, fused 10, selected evidence 5 | Explicit JSON output path, normally under `/tmp`; not official artifacts |

## Branch Addition Disposition

| Component | Duplicated area reviewed | Decision | Rationale and follow-up |
| --- | --- | --- | --- |
| `src/evaluation/benchmark/direct_evidence.py` | Case schema, expected-target representation, retrieval metrics, selected-primary and citation metrics, JSON report writer | KEEP_AS_CANONICAL in benchmark package | The oracle is stricter than frozen retrieval metrics because it evaluates primary selected evidence and prompt citation alignment. It remains named `direct_evidence` to avoid conflicting with frozen benchmark metrics. Future promotion of its cases should use the protected benchmark freeze process. |
| `src/evaluation/retrieval_quality_generalization.py` | Parallel module path outside `src/evaluation/benchmark` | CONVERT_TO_THIN_WRAPPER | This file now explicitly re-exports the stable direct-evidence surface from the canonical package module for branch-era import compatibility. It must not grow independent logic or wildcard exports. |
| `scripts/evaluation/run_retrieval_quality_generalization_benchmark.py` | Argument parsing, JSON serialization, before/after comparison | CONVERT_TO_THIN_WRAPPER | The script delegates reusable logic to `src.evaluation.benchmark.direct_evidence`. It should write to explicit temporary paths and must not create official artifacts. A future CLI consolidation can make this a subcommand of a shared evaluation CLI. |
| Direct-evidence in-code `BenchmarkCase` registry | Frozen benchmark case registry and `LegalTarget` schemas | MERGE_INTO_EXISTING pending protected benchmark process | The diagnostic cases should not be copied into `data/eval` during this task. If accepted as durable benchmark cases, they need review records, split assignment, qrels/evidence groups, and manifest updates through the official freeze workflow. |
| `EvidenceTarget` in direct-evidence diagnostics | `LegalTarget` in `src/evaluation/benchmark/schemas.py` | MERGE_INTO_EXISTING pending schema extension | Direct-evidence matching needs article, clause, and point locator exactness plus primary/supporting/forbidden semantics. The current frozen schemas can represent much of this, but citation-alignment and selected-primary oracle fields need a deliberate schema extension before unification. |
| Direct-evidence aggregate metrics | `retrieval_baseline.py` metrics | MOVE_TO_SHARED_CORE completed at package level | The metric definitions are not duplicates of Recall@k/MRR only. They add selection and citation denominators after runtime cutoff truncation. They must remain explicitly documented to avoid conflicting metric names. |
| Direct-evidence compare reports | Existing artifact comparison conventions | MOVE_TO_SHARED_CORE for diagnostic use; DEPRECATE for official artifacts | It is useful for same-runner before/after branch comparison under `/tmp`. Official reports should continue using frozen benchmark artifact writers and manifests. |
| `scripts/evaluation/run_local_hybrid_retrieval_validation.py` | Dense retrieval setup, sparse retrieval setup, coverage-aware fusion setup, service preflight, JSON output | MERGE_INTO_EXISTING pending shared local hybrid factory | It fills a manual safety gap: read-only local hybrid validation without LLM calls. It now reuses canonical direct-evidence target parsing, matching, cutoff config, aggregate metrics, and result metadata. It is not a benchmark framework. Future refactor should move reusable local hybrid factory code into `src/retrieval/workflows` or `src/evaluation/benchmark` and keep this script thin. |
| `tests/unit/evaluation/test_retrieval_quality_generalization.py` | Metric contract tests | KEEP_AS_CANONICAL tests for direct-evidence diagnostics | These tests protect cutoff, denominator, and compatibility-shim behavior without running a benchmark. |
| `tests/integration/retrieval/test_direct_article_priority_workflow.py` | Retrieval benchmark cases | KEEP_AS_CANONICAL regression tests | These are deterministic workflow regressions, not benchmark artifacts. |
| `tests/integration/retrieval/test_hybrid_generalization_fixture_workflow.py` | Hybrid benchmark runner behavior | KEEP_AS_CANONICAL fixture tests | These tests model 50 sparse plus 50 dense candidates through the real fusion implementation, fused top 10, selection top 5. They do not query Qdrant or load BGE-M3. |
| `docs/retrieval_quality_generalization_audit.md` | Evaluation documentation | KEEP_AS_CANONICAL branch audit | It documents direct-evidence heuristic and metric decisions. It should reference this architecture audit for framework boundaries. |

## Metric Boundary Decisions

The official frozen retrieval metrics remain implemented in
`src/evaluation/benchmark/retrieval_baseline.py`:

- retrieval Recall@k;
- required direct coverage@k;
- evidence group coverage@k;
- MRR@10;
- NDCG@10;
- split, domain, and question-type breakdowns.

The direct-evidence diagnostic metrics remain implemented in
`src/evaluation/benchmark/direct_evidence.py` and must keep distinct names and
contracts:

- expected evidence Recall@5 and Recall@10 from the diagnostic retrieval pool;
- expected article MRR from diagnostic ranks;
- primary evidence accuracy after runtime-aligned selection input truncation;
- citation alignment accuracy after prompt evidence mapping;
- cross-reference-only, wrong-actor, and wrong-domain primary error rates;
- multi-article selected/cited coverage accuracy;
- before/after regression counting, including rank losses that still pass.

These metrics are intentionally not aliases for the frozen benchmark metrics.
They evaluate a different oracle: whether the direct legal provision becomes
primary selected evidence and aligned prompt citation under production-like
candidate budgets.

## Output Schema Decisions

Official benchmark runners must continue to write the frozen artifact layout:

```text
case_results.jsonl
metrics_all.json
metrics_development.json
metrics_held_out_test.json
breakdowns.json
baseline_manifest.json
summary.md
```

Direct-evidence diagnostic runs must write only to explicit caller-provided
paths, normally under `/tmp`, and their JSON must include:

- schema version;
- runner/evaluator version;
- git revision;
- corpus path;
- benchmark mode;
- diagnostic candidate limit;
- selection input limit;
- selected evidence limit;
- production-alignment flag;
- per-case diagnostics;
- aggregate metrics.

They must not write to `artifacts/reports/evaluation` unless a future task
promotes the suite into the official benchmark process.

## Direct-Evidence Result Compatibility

Direct-evidence reports use this required envelope:

- `schema_version`;
- `metric_contract_version`;
- `evaluator_version`;
- `git_revision`;
- `corpus_identity`;
- `case_set_identity`;
- `pipeline_family`;
- `evaluation_stage`;
- `retrieval_mode`;
- `benchmark_mode`;
- `matching_granularity`;
- `cutoff_configuration`;
- `cases`;
- `aggregate_metrics`;
- `warnings`;
- `limitations`.

`compare_reports` calls `validate_report_compatibility` before computing any
delta. Comparison fails with `ValueError` when any of these differ:

- schema version;
- metric contract version;
- corpus identity;
- case-set identity;
- matching granularity;
- pipeline family;
- retrieval mode;
- evaluation stage;
- benchmark mode, unless a future explicit diagnostic-only mode is added;
- diagnostic candidate limit;
- fusion output limit;
- selection input limit;
- selected evidence budget.

This prevents comparing runtime-aligned and deep-diagnostic reports, or
comparing direct-evidence diagnostics against official Naive/Advanced artifacts,
as if they shared one oracle.

## Local Environment Readiness

Static inspection found the supported local real-hybrid configuration:

- BGE-M3 model path override: `EMBEDDING_MODEL_PATH` or
  `LEGAL_QA_EMBEDDING_MODEL_PATH`.
- Default model name when no local path is provided: `BAAI/bge-m3`.
- Retrieval config: `configs/retrieval/retrieval.yml`.
- Qdrant URL default: `http://localhost:6333`.
- Expected collection for retrieval/runtime validation:
  `vnlaw_chunks_bgem3_v1_full`.
- Dense vector name: `dense`.
- Expected dense dimension: `1024`.
- Distance in indexing config: `Cosine`.
- Local fake-mode `docker-compose.yml` does not start Qdrant and does not
  mount a Qdrant volume.
- `.env.example` documents Qdrant and model variables but does not provide a
  local model artifact path.

Blocker: this repository does not contain a committed BGE-M3 model artifact,
Qdrant volume, collection snapshot, or safe local collection restoration
procedure for `vnlaw_chunks_bgem3_v1_full`. Actual local hybrid validation
therefore requires the user to provide an existing local BGE-M3 directory and a
read-only local Qdrant instance containing the expected collection. Do not use
production Qdrant as a substitute and do not rebuild the collection during this
branch-validation task.

## Final Benchmark Run Policy

These commands are required only after the repository is marked ready for
benchmark; they were not executed during this audit.

| Run | Mandatory | Reason | Required services | Calls external LLM | Existing artifacts reusable | Compatibility requirements |
| --- | --- | --- | --- | --- | --- | --- |
| Direct-evidence runtime-aligned diagnostic | Yes | Branch gate for selected-primary and citation alignment under production cutoffs | None; local processed chunks only | No | No, regenerate current same-runner before/after JSON under `/tmp` | Same direct-evidence schema, metric contract, corpus, case set, mode, granularity, and cutoffs. |
| Direct-evidence deep diagnostic | Optional | Root-cause analysis for targets outside top-10 selection input | None; local processed chunks only | No | No | Must not be compared to runtime-aligned mode except through future explicit diagnostic-only comparison. |
| Official Advanced retrieval benchmark | Yes for final quality claim | Confirms adopted coverage-aware retrieval on frozen v0.1.0 | BGE-M3 and read-only Qdrant for dense/hybrid runs | No | Historical artifacts are reference only; final branch validation should write a unique new output directory when explicitly approved | Frozen benchmark manifests, corpus, split, and config fixed. |
| Official Naive retrieval benchmark | Optional unless comparing against refreshed Advanced results | Historical baseline comparison | BGE-M3 and read-only Qdrant | No | Historical baseline may be reused only when evaluator/corpus/config compatibility is unchanged | Same frozen benchmark version and retrieval artifact contract. |
| Naive/Advanced comparison | Optional reporting | Places branch result against historical baseline | Existing compatible retrieval artifacts | No | Existing artifacts may be reused if compatibility is verified | Reject incompatible benchmark versions, config hashes, corpus hashes, or metric schemas. |
| Local real hybrid validation | Yes before PASS | Validates actual local BGE-M3 + Qdrant + sparse + fusion + selection + prompt mapping path | Local BGE-M3 model and read-only local Qdrant collection | No | No | Must use direct-evidence schema, runtime cutoffs 50/50 -> 10 -> 5, and report local-service limitations. |
| Generation benchmark | Optional for this retrieval-quality branch unless final scope expands to answers | Validates strict generation and fallback behavior | LLM provider and compatible retrieval artifacts | Yes | Existing official artifacts are reference only | Requires explicit approval, fixed retrieval artifact inputs, and no overwritten official reports. |

Manual command templates for the final benchmark phase:

```bash
# Direct-evidence runtime-aligned diagnostic, after explicit approval.
uv run python scripts/evaluation/run_retrieval_quality_generalization_benchmark.py run \
  --mode runtime_aligned \
  --repo-root /path/to/checkout \
  --corpus /home/phat/AI_Project/VnLaw-QA/data/processed/legal_chunks.jsonl \
  --sparse-retrieval-top-k 50 \
  --dense-retrieval-top-k 50 \
  --diagnostic-candidate-top-k 50 \
  --fusion-output-top-k 10 \
  --selection-input-top-k 10 \
  --selected-evidence-budget 5 \
  --output /tmp/vnlaw-benchmarks/runtime-aligned-after.json

# Optional direct-evidence deep diagnostic.
uv run python scripts/evaluation/run_retrieval_quality_generalization_benchmark.py run \
  --mode deep_diagnostic \
  --repo-root /path/to/checkout \
  --corpus /home/phat/AI_Project/VnLaw-QA/data/processed/legal_chunks.jsonl \
  --output /tmp/vnlaw-benchmarks/deep-diagnostic-after.json

# Compare same-contract direct-evidence reports.
uv run python scripts/evaluation/run_retrieval_quality_generalization_benchmark.py compare \
  --before /tmp/vnlaw-benchmarks/runtime-aligned-before.json \
  --after /tmp/vnlaw-benchmarks/runtime-aligned-after.json \
  --output /tmp/vnlaw-benchmarks/runtime-aligned-comparison.json

# Local real hybrid validation; loads BGE-M3 and queries local Qdrant read-only.
uv run python scripts/evaluation/run_local_hybrid_retrieval_validation.py \
  --confirm-local-read-only \
  --config configs/retrieval/retrieval.yml \
  --chunks data/processed/legal_chunks.jsonl \
  --cases /tmp/vnlaw-benchmarks/direct-evidence-cases.json \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --sparse-top-k 50 \
  --dense-top-k 50 \
  --fusion-top-k 10 \
  --selected-evidence-budget 5 \
  --output /tmp/vnlaw-benchmarks/local-hybrid-validation.json
```

## Canonical Future Direction

The target architecture is one framework with these layers:

```text
Benchmark case registry
        |
Shared pipeline adapters
        |
Naive and Advanced pipeline configurations
        |
Shared evaluator and metric contracts
        |
Shared machine-readable result schema
        |
Comparison/report renderer
        |
Thin CLI entry points
```

The practical migration path is:

1. Keep frozen v0.1.0 as the official comparative benchmark until a formally
   reviewed v0.2.0 benchmark is created.
2. Keep direct-evidence cases as diagnostic branch-regression cases until they
   are promoted through the protected benchmark freeze process.
3. Extend `LegalTarget`, `EvidenceJudgment`, or a new benchmark oracle schema
   before moving selected-primary and citation-alignment assertions into
   `data/eval/legal_qa_benchmark`.
4. Reuse `src/evaluation/benchmark` artifact writer conventions if
   direct-evidence diagnostics become official artifacts.
5. Refactor local hybrid validation setup into a shared factory before adding
   any additional local-service validation entry points.
6. Keep all new scripts as thin wrappers and avoid adding more benchmark CLI
   files until a single command surface is selected.

## Safety Boundaries

This architecture audit does not authorize any of the following:

- rewriting or refreshing `data/eval/legal_qa_benchmark`;
- modifying historical reports under `artifacts/reports/evaluation`;
- comparing official Naive and Advanced results against direct-evidence
  diagnostics as if they shared the same oracle;
- presenting deterministic sparse diagnostics as real local Qdrant hybrid
  validation;
- adding topic-specific retrieval scoring to improve direct-evidence cases;
- writing to Qdrant, re-indexing, re-embedding, loading external LLMs, or
  calling production services.
