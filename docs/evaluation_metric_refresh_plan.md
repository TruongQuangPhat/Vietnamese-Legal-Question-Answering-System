# Evaluation Metric Refresh Plan

This document prepares a controlled metric refresh after recent QA behavior
changes. It is an audit and runbook only. No benchmark, OpenRouter call,
production endpoint, Qdrant mutation, indexing, crawling, snapshot operation, or
new evaluation artifact was run or written while creating it.

## Existing Official Artifacts

Frozen benchmark inputs live under `data/eval/legal_qa_benchmark/` and remain
the benchmark target for the refresh:

- benchmark version: `v0.1.0`
- query count: 128
- development split: 85
- held-out reporting split: 43
- benchmark manifest SHA256 recorded in existing reports:
  `1f26e4e39ee2edab31a5951a4e252d4c5434511e6447c24af3e907fbab720c68`
- split manifest SHA256 recorded in existing reports:
  `94ceaccefa8e335054e9e28f194011e2beb254b5b991c1503ca2e53cbe33c217`
- processed chunk SHA256:
  `95ff0129915ad4e77306fbdaa2c6eb8c7a7c58730cd21050aec429541416b30c`

Current report groups under `artifacts/reports/evaluation/`:

| Group | Subdirectory | Purpose |
| --- | --- | --- |
| `naive_rag_baseline` | `retrieval` | Frozen dense BGE-M3/Qdrant retrieval baseline. |
| `naive_rag_baseline` | `generation` | Frozen Naive RAG generation baseline using dense retrieval artifacts. |
| `advanced_rag` | `sparse_retrieval` | BM25 sparse retrieval baseline. |
| `advanced_rag` | `hybrid_retrieval` | Fixed RRF dense+sparse hybrid baseline. |
| `advanced_rag` | `fusion_ablation` | Development-only fusion/quota ablation. |
| `advanced_rag` | `coverage_aware_retrieval` | Final adopted coverage-aware quota retrieval report. |
| `advanced_rag` | `reranking_ablation` | Development-only reranking ablation; not adopted. |
| `advanced_rag` | `retrieval_comparison` | Retrieval comparison report. |
| `advanced_rag` | `evidence_selection_diagnostics` | Evidence selection diagnostics. |
| `advanced_rag` | `strict_generation_evaluation` | Earlier strict generation run. |
| `advanced_rag` | `strict_generation_evaluation_selection_policy_improvement` | Rejected trial; held-out/fallback behavior regressed. |
| `advanced_rag` | `strict_generation_evaluation_answerability_fallback_guard` | Latest official adopted strict generation baseline. |
| `advanced_rag` | `strict_generation_error_analysis` | Error analysis over strict generation outputs. |

Manual review support files also exist under `data/eval/`, including
`manual_faithfulness_verdicts.json`, `manual_naive_rag_generation_queries.jsonl`,
and `manual_retrieval_queries.jsonl`. These support the older Naive RAG manual
review/quality-gate workflow and are not a substitute for the frozen
`v0.1.0` benchmark.

## Latest Official Baseline

Treat
`artifacts/reports/evaluation/advanced_rag/strict_generation_evaluation_answerability_fallback_guard`
as the latest official baseline for current QA quality reporting.

All-split headline metrics from that report:

| Metric | Value |
| --- | ---: |
| `query_count` | 128 |
| `decision_accuracy` | 0.875 |
| `answer_allowed_answer_rate` | 0.8545454545 |
| `fallback_required_fallback_rate` | 1.0 |
| `selected_evidence_group_coverage` | 0.7861616162 |
| `case_pass_rate` | 0.7578125 |
| `case_partial_rate` | 0.1171875 |
| `case_fail_rate` | 0.125 |
| `citation_id_validity_rate` | 1.0 |
| `retrieval_error_count` | 0 |
| `generation_error_count` | 0 |

The older `naive_rag_baseline` reports should be treated as fixed historical
comparators unless the Naive RAG implementation or frozen dense retrieval
baseline is intentionally changed. Recent work changed the current advanced QA
answer policy, score propagation, follow-up handling, API/session behavior, and
deployment safety; it did not redefine Naive RAG as the product target.

## Recommended Refresh Target

Run a new advanced RAG strict generation evaluation only, compared against the
existing fixed Naive RAG generation baseline. Do not rerun Naive RAG by default.

Rationale:

- The product target is the adopted advanced RAG strict generation workflow.
- Recent answer-policy and grounding changes should be measured in the strict
  generation workflow, not by overwriting historical Naive RAG artifacts.
- The strict generation runner already compares its output against
  `artifacts/reports/evaluation/naive_rag_baseline/generation`.
- Follow-up intent, durable conversations, session ownership, and API rate
  limiting are product/API behavior changes and should not change frozen
  single-turn benchmark labels.

Optionally rerun coverage-aware retrieval into a separate new directory first
only if retrieval code, Qdrant contents, or processed chunks changed. If
retrieval is unchanged, use the existing
`advanced_rag/coverage_aware_retrieval` report as the fixed retrieval-policy
manifest for strict generation.

## Requirements

The real strict generation refresh requires:

- `data/eval/legal_qa_benchmark/*` frozen benchmark files.
- `data/processed/legal_chunks.jsonl` matching SHA256
  `95ff0129915ad4e77306fbdaa2c6eb8c7a7c58730cd21050aec429541416b30c`.
- `configs/retrieval/retrieval.yml`.
- `configs/llm/openrouter.yml`.
- Optional extras installed for real retrieval:
  `uv sync --extra qdrant --extra embedding`.
- BGE-M3 model availability locally or downloadable from Hugging Face.
- Enough RAM/CPU for BGE-M3, Torch, Transformers, local BM25, and 128-query
  evaluation. Render Free is not suitable.
- A read-only Qdrant collection containing `vnlaw_chunks_bgem3_v1_full` with
  40,389 points and dense vector name `dense`.
- `OPENROUTER_API_KEY` in the local private environment for real generation.

Current runner caveat: `scripts/evaluation/run_strict_generation_evaluation.py`
and `scripts/evaluation/run_coverage_aware_hybrid_retrieval.py` accept `--url`
and `--collection-name`, but the inspected code does not pass `QDRANT_API_KEY`
into `build_qdrant_client()`. Therefore authenticated Qdrant Cloud should not
be assumed to work for this refresh until that path is tested or patched. The
safe current options are:

1. run against an unauthenticated local Qdrant instance restored with the
   existing collection; or
2. first add a small evaluation-CLI credential fix so read-only Qdrant Cloud can
   use `QDRANT_API_KEY`.

Do not use the deployed Render `/api/v1/legal-qa/ask` endpoint for benchmark
evaluation.

## Preflight Checklist

Before a real run:

- Worktree is clean and all intended behavior branches are merged into the
  branch being evaluated.
- No secrets are printed, echoed, committed, or written to reports.
- `.env` remains untracked and contains only local/private values.
- Benchmark files are unchanged.
- Existing official report directories are not selected as output directories.
- The output directory does not exist before the run.
- The selected Qdrant endpoint is read-only for evaluation purposes.
- Qdrant point count and vector schema match the manifest.
- `OPENROUTER_API_KEY` is present in the private shell.
- Real LLM spend and latency are expected and approved.
- Held-out metrics are reported only after policy is fixed; do not tune on
  held-out results.

Safe metadata validation before the real benchmark:

```bash
uv run python scripts/evaluation/validate_benchmark.py \
  --queries data/eval/legal_qa_benchmark/benchmark_queries.jsonl \
  --legal-targets data/eval/legal_qa_benchmark/benchmark_targets.jsonl \
  --evidence-judgments data/eval/legal_qa_benchmark/benchmark_qrels.jsonl \
  --evidence-groups data/eval/legal_qa_benchmark/evidence_groups.jsonl \
  --review-records data/eval/legal_qa_benchmark/review_records.jsonl \
  --config configs/evaluation/legal_qa_benchmark.yml
```

No-overwrite output preflight:

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_DIR="artifacts/reports/evaluation/advanced_rag/strict_generation_evaluation_answer_policy_refresh_${RUN_ID}"
test ! -e "$OUTPUT_DIR"
```

## Proposed Real Run Command

Run this only after explicit approval to spend real LLM calls and use real
retrieval services:

```bash
env UV_CACHE_DIR=/tmp/vnlaw-uv-cache \
  uv run --extra qdrant --extra embedding \
  python scripts/evaluation/run_strict_generation_evaluation.py \
    --coverage-retrieval-dir artifacts/reports/evaluation/advanced_rag/coverage_aware_retrieval \
    --generation-baseline-dir artifacts/reports/evaluation/naive_rag_baseline/generation \
    --output-dir "$OUTPUT_DIR" \
    --collection-name vnlaw_chunks_bgem3_v1_full \
    --url http://localhost:6333 \
    --device cpu \
    --provider openrouter
```

Use `--url http://localhost:6333` only when a compatible local read-only Qdrant
instance is available. For Qdrant Cloud, first ensure evaluation CLIs pass
`QDRANT_API_KEY` or run a separately approved credential-support patch.

If retrieval must be refreshed as well, use a separate unique output directory
and comparison directory before the strict generation run:

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RETRIEVAL_OUTPUT_DIR="artifacts/reports/evaluation/advanced_rag/coverage_aware_retrieval_refresh_${RUN_ID}"
RETRIEVAL_COMPARISON_DIR="artifacts/reports/evaluation/advanced_rag/retrieval_comparison_refresh_${RUN_ID}"
test ! -e "$RETRIEVAL_OUTPUT_DIR"
test ! -e "$RETRIEVAL_COMPARISON_DIR"

env UV_CACHE_DIR=/tmp/vnlaw-uv-cache \
  uv run --extra qdrant --extra embedding \
  python scripts/evaluation/run_coverage_aware_hybrid_retrieval.py \
    --output-dir "$RETRIEVAL_OUTPUT_DIR" \
    --comparison-dir "$RETRIEVAL_COMPARISON_DIR" \
    --collection-name vnlaw_chunks_bgem3_v1_full \
    --url http://localhost:6333 \
    --device cpu
```

Then pass `--coverage-retrieval-dir "$RETRIEVAL_OUTPUT_DIR"` into the strict
generation command.

## Metric Comparison Plan

Compare the new strict generation report against:

1. latest official advanced baseline:
   `advanced_rag/strict_generation_evaluation_answerability_fallback_guard`
2. fixed historical Naive RAG baseline:
   `naive_rag_baseline/generation`

Primary metrics:

- `decision_accuracy`
- `answer_allowed_answer_rate`
- `fallback_required_fallback_rate`
- `selected_evidence_group_coverage`
- `case_pass_rate`
- `case_partial_rate`
- `case_fail_rate`
- `citation_id_validity_rate`
- `retrieval_error_count`
- `generation_error_count`

Secondary review dimensions:

- development vs held-out split deltas
- fallback-required cases that no longer fallback
- answer-allowed cases newly falling back
- any `answered_with_caution` mapping or status-reporting effects, if the
  evaluation output exposes them
- citation ID validity and invalid-citation fallbacks
- top failure cases from any regenerated error analysis

Do not update `PROJECT_CONTEXT.md`, `README.md`, official metric tables, or
baseline claims until the real run has completed and the output artifacts have
been reviewed.

## Risks and Limitations

- The frozen benchmark has only 128 queries and is not broad proof of Vietnamese
  legal QA quality.
- Held-out cases are reporting-only and must not drive tuning.
- No qualified human legal review of final generated claims is complete.
- LLM output may vary despite temperature `0.0`.
- The current evaluation runner may need Qdrant credential support before
  authenticated Qdrant Cloud can be used directly.
- API rate limiting, durable conversations, and session ownership are not
  benchmarked by this single-turn offline strict generation flow.
- Do not claim refreshed official metrics until the real benchmark command has
  actually run and artifacts are inspected.
