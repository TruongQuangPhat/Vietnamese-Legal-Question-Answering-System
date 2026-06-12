# Phase 9 Retrieval / Naive RAG Tracker

## Status

```text
Phase 9A — Dense Retrieval Baseline: implemented
Phase 9A.1 — Retrieval Sanity Evaluation & Evidence Risk Audit: implemented
Phase 9A.2 — Evidence Safety and Context Assembly Rules: implemented
Phase 9A.3 — Evidence Selection and Fallback Rules: implemented
Phase 9A.4 — Selection Integration Smoke Test: implemented
Phase 9A.5 — Workflow Boundary Cleanup: implemented
Phase 9B — Naive RAG Answer Generation: implemented
Phase 9C — Naive RAG Generation Evaluation & Safety Hardening: validated
```

Phase 9 starts from the validated Phase 8 Qdrant collection:

```text
Collection: vnlaw_chunks_bgem3_v1_full
Vector: dense
Dimension: 1024
Distance: Cosine
Model: BAAI/bge-m3
Sparse indexing: disabled
```

## Phase 9A Implemented

- Typed retrieval contracts in `src/retrieval/models.py`.
- Safe exact-match filters in `src/retrieval/filters.py`.
- Read-only dense Qdrant retriever in `src/retrieval/dense_retriever.py`.
- Thin service orchestration in `src/services/retrieval_service.py`.
- Runtime defaults in `configs/retrieval/retrieval.yml`.
- Manual single-query CLI in `scripts/run_dense_retrieval.py`.
- Unit tests under `tests/unit/retrieval/`.

The retriever embeds the user query with the existing BGE-M3 wrapper, validates
the 1024-dimensional query vector, searches Qdrant with named vector `dense`,
requests `with_payload=True` and `with_vectors=False`, and returns typed
payload-backed legal evidence.

## Phase 9A Guardrails

- No LLM call.
- No answer generation.
- No prompt templates.
- No generated-citation validation.
- No sparse retrieval, BM25, hybrid search, RRF, or reranking.
- No FastAPI endpoint.
- No corpus mutation.
- No Qdrant mutation.
- No effective-date filtering claim.

## Phase 9A.1 Implemented

Live smoke tests against the real Qdrant collection passed technically:

```text
query_vector_dimension = 1024
result_count = requested top_k
issues = []
metadata/citation/source fields are preserved
```

The same smoke tests exposed dense-only quality limitations:

- annual leave queries can retrieve the correct Article 113 parent context while
  ranking sibling child provisions ahead of the expected Clause 1 evidence;
- marriage-condition queries can retrieve related marriage provisions before
  Article 8;
- parent Article context can contain answer-like text while the retrieved child
  chunk citation points to a different Clause/Point.

Phase 9A.1 adds a small read-only evaluation/audit layer:

```text
data/eval/manual_retrieval_queries.jsonl
src/retrieval/evaluation.py
scripts/evaluate_dense_retrieval.py
tests/unit/retrieval/test_evaluation.py
```

The evaluator reports expected-target hits separately from Article-level hits,
computes recall/MRR metrics, summarizes retrieved evidence, and flags
structural citation risks. Expected targets now declare an explicit
`match_level`:

```text
article -> law_id + article_number
clause  -> law_id + article_number + clause_number
point   -> law_id + article_number + clause_number + point_label
```

Null fields below the declared `match_level` are not exact-null constraints.
For example, an Article-level expected target can be satisfied by a Clause or
Point chunk under that Article. Clause-level targets can be satisfied by child
Point chunks under the same Clause. This avoids undercounting valid child chunks
while preserving separate Article-hit and exact-depth metrics.

The JSON report exposes `article_match_rank`, `clause_match_rank`,
`point_match_rank`, `best_rank_by_match_level`, `best_exact_rank`, and
`exact_match_depth` for each query. Risk flags include the expected target,
declared match level, best ranks, top result, and lower matching result when
available. It does not modify retrieval ranking or call an LLM.

## Phase 9A.2 Implemented

Phase 9A.2 adds a retrieval-side evidence safety layer:

```text
src/retrieval/evidence.py
tests/unit/retrieval/test_evidence.py
```

The evidence layer converts a typed `RetrievalResult` into an `EvidenceBundle`
of ordered `EvidencePacket` objects. It preserves citation metadata,
hierarchy, source URL/domain, child text, parent Article context, metadata,
warnings, and safety issues.

Evidence packets classify citation scope:

```text
child_exact           -> child text is citable with the retrieved child citation
article_context       -> article-level chunk can cite article context
unsafe_parent_context -> parent_text is broader than the child citation
missing_citation      -> citation metadata is missing
```

Parent Article context is conservative by default. Child `text` remains the
primary citable evidence. For Clause/Point chunks, broader `parent_text` is
included only as auxiliary context and is explicitly rendered as not directly
citable under the child citation. This prevents a future generator from using
Article-level `parent_text` content while citing a sibling child chunk.

Safety levels are structural:

```text
safe    -> complete citation/source metadata and directly citable child/article text
caution -> child text is citable, but broader parent context or truncation needs care
unsafe  -> missing citation/law/source/child text or empty/repealed flags
```

`ContextAssemblyConfig` controls `max_packets`, parent inclusion,
child/parent truncation limits, parent-text deduplication, score display, and
minimum safety level. Rendered context keeps citable text adjacent to its
citation and separates auxiliary parent context under an explicit warning.

This slice still does not generate answers, create prompts, validate generated
citations, rerank, perform hybrid retrieval, or mutate Qdrant/corpus data.

## Phase 9A.3 Implemented

Phase 9A.3 adds a retrieval-side evidence gate:

```text
src/retrieval/selection.py
tests/unit/retrieval/test_selection.py
```

The selection layer consumes an `EvidenceBundle` and returns an
`EvidenceSelectionResult` with:

```text
decision: answer_allowed | fallback_required | needs_review
selected_evidence
rejected_evidence
fallback_reasons
selection warnings
rendered selected context
```

Rules are conservative:

- unsafe evidence is never selected;
- safe evidence is preferred before caution evidence;
- caution evidence can be selected only when it still has citation, law ID,
  source URL, and citable child text;
- parent Article context for child chunks remains auxiliary only and is never
  treated as directly citable under the child citation;
- selected context excludes unsafe evidence and keeps citation adjacent to
  citable child text;
- all-caution parent-context evidence defaults to fallback unless configured for
  review;
- optional evaluation-assisted mode can require selected packets to match
  expected targets from Phase 9A.1.

This means the `annual_leave_days` failure mode remains blocked in
evaluation-assisted mode: sibling Article 113 chunks do not satisfy expected
Clause 1 / Point a-b-c targets, so the result is fallback/review rather than a
clean generation-allowed decision.

This slice still does not generate legal answers, create final prompts, validate
generated citations, perform hybrid retrieval, rerank, or mutate Qdrant/corpus
data.

## Phase 9A.4 Implemented

Phase 9A.4 adds a retrieval-side integration smoke test:

```text
manual query
-> dense retrieval
-> EvidenceBundle assembly
-> EvidenceSelectionResult gate
-> JSON smoke report
```

Implemented files:

```text
src/retrieval/integration.py
scripts/run_selection_smoke.py
tests/unit/retrieval/test_integration.py
```

The smoke layer reuses the Phase 9A.1 manual dataset. Each query can declare
`expected_decision` and `allowed_decisions`, so the smoke report can check
whether the current retrieval-side gate behaves as expected for known cases.
For example:

- `annual_leave_days` must not pass as clean `answer_allowed` because dense
  retrieval currently misses the expected Clause 1 / Point a-b-c target;
- `health_insurance_children_under_6` is expected to pass as `answer_allowed`
  when exact point evidence is selected;
- `civil_code_scope` is expected to pass as `answer_allowed` when Article 1
  evidence is selected;
- `marriage_conditions` remains permissive in the manual expectation because
  Article 8 may rank lower and strictness is configurable;
- `civil_rights_protection` may be `answer_allowed` or `needs_review` depending
  on selected evidence safety.

The smoke report includes run metadata, decision counts, pass/fail counts,
selection/evidence config, per-query retrieval latency, evidence counts,
selected/rejected evidence summaries, fallback reasons, selection warnings,
risk flags, top-result summary, and a rendered selected-context preview.

When expected targets are provided, the selection gate now prefers selectable
packets that match those targets before unrelated packets. This is only an
evaluation/smoke selection behavior; it does not change dense retrieval ranking.
It validates cases such as `civil_rights_protection`, where Article 2 can be
retrieved below an unrelated top result but still needs to be selected for the
manual expectation to pass. Match semantics stay aligned with Phase 9A.1:
Article targets match child chunks under the same Article, Clause targets match
child chunks under the same Clause, and Point targets require the exact Point.

`--strict` also passes Phase 9A.1 risk flags into the Phase 9A.3 selector. In
non-strict mode the flags are still reported, but only exact-target gating and
structural evidence rules drive the selection decision.

This slice still does not call an LLM, generate answers, create final prompts,
improve retrieval ranking, perform hybrid retrieval, rerank, or mutate
Qdrant/corpus data.

## Phase 9A.5 Implemented

Phase 9A.5 moves executable retrieval workflow logic out of top-level
`scripts/` and into reusable modules:

```text
src/retrieval/workflows/
  __init__.py
  common.py
  dense_retrieval.py
  dense_evaluation.py
  selection_smoke.py
```

The top-level scripts remain backward-compatible wrappers:

```text
scripts/run_dense_retrieval.py
scripts/evaluate_dense_retrieval.py
scripts/run_selection_smoke.py
```

These wrappers only bootstrap repository imports and call the corresponding
workflow `main()` function. Argument parsing, dependency construction, report
writing, path safety checks, and console summaries now live under
`src/retrieval/workflows/`.

No retrieval, evaluation, evidence, selection, ranking, scoring, risk flag, or
output schema behavior was intentionally changed. Future Phase 9B executable
entrypoints should follow the same rule: reusable workflow logic belongs under
`src/`, while `scripts/` remains a compatibility layer for commands.

## Selection Smoke Command

```bash
uv run --extra qdrant --extra embedding python scripts/run_selection_smoke.py \
  --queries data/eval/manual_retrieval_queries.jsonl \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --output artifacts/reports/retrieval/selection_smoke_report.json
```

## Phase 9B Implemented

Phase 9B adds fallback-aware Naive RAG generation while preserving the Phase 9A
evidence gate:

```text
query
-> dense retrieval
-> EvidenceBundle assembly
-> EvidenceSelectionResult gate
-> if decision == answer_allowed: selected-evidence prompt + LLM
-> otherwise: deterministic fallback without LLM call
```

Implemented files:

```text
src/retrieval/llm_client.py
src/retrieval/prompting.py
src/retrieval/generation.py
src/retrieval/rag_pipeline.py
src/retrieval/workflows/naive_rag.py
scripts/run_naive_rag.py
tests/unit/retrieval/test_llm_client.py
tests/unit/retrieval/test_prompting.py
tests/unit/retrieval/test_generation.py
tests/unit/retrieval/test_rag_pipeline.py
```

OpenRouter is the first concrete LLM provider. The default model is
`google/gemini-2.5-flash`; `google/gemini-2.5-flash-lite` is documented as a
cheap smoke/dev option. Non-secret defaults live in
`configs/llm/openrouter.yml`. The CLI loads the project `.env` automatically
without overriding exported environment variables.

Resolution order is:

```text
model: --model > OPENROUTER_MODEL > config default_model > emergency fallback
base URL: OPENROUTER_BASE_URL > config base_url > emergency fallback
API key: OPENROUTER_API_KEY from environment/.env only
```

Never commit `.env`. API keys are not stored in YAML, printed, logged, or
serialized into reports.

Generation is allowed only when the selector returns `answer_allowed`.
`fallback_required` and `needs_review` produce a deterministic Vietnamese
fallback result and do not call the LLM for legal answer generation. This keeps
the known `annual_leave_days` failure mode blocked: sibling Article 113 chunks
and unsafe parent context cannot be used to generate a confident answer.

The prompt builder uses only `EvidenceSelectionResult.selected_evidence`.
Rejected evidence, unsafe evidence, and unselected retrieval results are not
included. Each selected packet receives an internal citation ID such as `[E1]`.
Citable child text is separated from auxiliary parent context, and auxiliary
context is explicitly marked as not directly citable.

The lightweight citation guard extracts generated `[E#]` IDs, verifies that
each ID exists in selected prompt evidence, maps valid IDs back to real citation
metadata, reports unknown IDs, and warns when a non-empty generated answer has
no citation IDs. This is not a full generated-citation validator.

Phase 9B intentionally does not add hybrid retrieval, sparse retrieval, BM25,
RRF, reranking, query rewriting, GraphRAG, agents, FastAPI endpoints, reindexing,
or production legal-advice claims.

## Naive RAG Command

```bash
uv run --extra qdrant --extra embedding python scripts/run_naive_rag.py \
  --query "Trẻ em dưới 6 tuổi được hưởng bảo hiểm y tế như thế nào?" \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --provider openrouter \
  --model google/gemini-2.5-flash \
  --output artifacts/reports/retrieval/naive_rag_single_query.json
```

If the evidence gate returns fallback/review, the command writes a fallback
JSON result without using `OPENROUTER_API_KEY`. If the gate allows generation,
OpenRouter is called only when `OPENROUTER_API_KEY` is set.

## Phase 9C Implemented

Phase 9C turns the Phase 9B single-query smoke into a small repeatable
generation evaluation baseline:

```text
manual generation queries
-> existing run_naive_rag(...)
-> deterministic validators
-> comparable JSON report
```

The initial dataset contains three cases with unambiguous existing policy:

- health insurance for children under six: `answer_allowed`, LLM required;
- annual leave days: fallback/review, LLM forbidden while the exact target is
  missing under dense-only retrieval;
- Civil Code scope: `answer_allowed`, LLM required.

Phase 9C.1 expands the dataset from three to five cases by adding the two
remaining queries already defined in the Phase 9A manual retrieval dataset:

- marriage conditions;
- civil-rights recognition and protection.

Their retrieval decisions are intentionally variable, so both are marked
`manual_review_required=true` and `blocking=false`. They still enforce the
decision/LLM safety invariant, citation-ID integrity whenever generation is
allowed, Vietnamese output, forbidden-phrase checks, and secret screening.
The dataset stops at five because the current reviewed retrieval source has
only five unique cases; no legal expectations were invented or duplicated to
reach an arbitrary case count.

Checks cover decision policy, LLM call policy, fallback behavior, valid `[E#]`
citation IDs, likely Vietnamese output, forbidden phrases, and secret-like
content. The safety invariant remains:

```text
decision != answer_allowed -> llm_called=false
```

`citation_id_coverage_rate` measures only whether generated citation IDs map to
selected evidence. It does not establish semantic faithfulness, unsupported
claim absence, or legal correctness. Phase 9C does not use an LLM judge.
Phase 9C.1 also reports manual-review counts, selected caution-evidence counts,
all-caution case counts, and selection-warning counts as review signals only.

Run the lower-cost smoke/dev evaluation:

```bash
uv run --extra qdrant --extra embedding python scripts/evaluate_naive_rag_generation.py \
  --queries data/eval/manual_naive_rag_generation_queries.jsonl \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --provider openrouter \
  --model google/gemini-2.5-flash-lite \
  --output artifacts/reports/retrieval/naive_rag_generation_eval.json
```

`OPENROUTER_API_KEY` is loaded only from the environment or uncommitted `.env`.
It is never written to the report. The report includes aggregate rates and
case-level redacted answer previews. The annual-leave case may continue to
fallback until retrieval quality is improved in a separately scoped phase.

Initial live result using `google/gemini-2.5-flash-lite`:

```text
status = validated_generation_eval_passed
passed_cases = 3 / 3
decision_pass_rate = 1.0
llm_call_policy_pass_rate = 1.0
citation_id_coverage_rate = 1.0
fallback_policy_pass_rate = 1.0
vietnamese_language_pass_rate = 1.0
unknown_citation_id_count = 0
missing_citation_id_count = 0
forbidden_phrase_failures = 0
secret_leak_failures = 0
```

The expanded Phase 9C.1 command writes
`artifacts/reports/retrieval/naive_rag_generation_eval_expanded.json`. Manual
legal review remains required even when all deterministic checks pass.

Expanded live result using `google/gemini-2.5-flash-lite`:

```text
status = expanded_generation_eval_passed
passed_cases = 5 / 5
blocking_cases = 3
manual_review_required_cases = 2
decision_pass_rate = 1.0
llm_call_policy_pass_rate = 1.0
citation_id_coverage_rate = 1.0
fallback_policy_pass_rate = 1.0
vietnamese_language_pass_rate = 1.0
unknown_citation_id_count = 0
missing_citation_id_count = 0
forbidden_phrase_failures = 0
secret_leak_failures = 0
total_caution_selected_count = 16
cases_with_all_caution_evidence = 2
selection_warning_count = 31
```

The caution and warning totals require human inspection; they are not
automated legal-correctness failures.

## Phase 9C.2 Manual Faithfulness Review

Phase 9C.2 adds an offline manual-review export layer. It reads the existing
expanded JSON report and produces:

```text
artifacts/reports/retrieval/
naive_rag_generation_eval_expanded_manual_review.md
```

Run:

```bash
uv run python scripts/export_naive_rag_manual_review.py \
  --input artifacts/reports/retrieval/naive_rag_generation_eval_expanded.json \
  --output artifacts/reports/retrieval/naive_rag_generation_eval_expanded_manual_review.md
```

The worksheet includes case metadata, answer previews, citation IDs,
selection warnings, fallback checks, and unchecked claim-to-citation tables.
It prioritizes `health_insurance_children_under_6_generation` and
`marriage_conditions_generation` because all selected evidence is caution
marked. `civil_rights_protection_generation` is also prioritized because it is
explicitly a manual-review case.

Phase 9C.2 status is `manual_review_partial`. The Phase 9C.1 report does not
contain selected evidence text or citation summaries, and one answer preview
is truncated. A human reviewer must inspect the underlying selected evidence
before assigning `pass`, `partial`, `fail`, or `needs_more_evidence`.
`annual_leave_days_generation` remains a separately reviewed dense-only
fallback with no LLM call.

The exporter is offline: it does not call OpenRouter, Qdrant, retrieval, or
generation. It does not change retrieval or generation behavior and does not
introduce Phase 10 features.

## Phase 9C.3 Evidence Preview Support

Phase 9C.3 adds opt-in evidence previews to the existing generation evaluation:

```bash
uv run --extra qdrant --extra embedding python scripts/evaluate_naive_rag_generation.py \
  --queries data/eval/manual_naive_rag_generation_queries.jsonl \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --provider openrouter \
  --model google/gemini-2.5-flash-lite \
  --output artifacts/reports/retrieval/naive_rag_generation_eval_expanded_with_evidence.json \
  --include-evidence-preview \
  --evidence-preview-chars 500
```

Each preview preserves the evidence ID, packet/chunk metadata, legal
hierarchy, citation, source URL, citation scope, safety level, and a bounded
redacted preview of the safe-citable child text. Full parent text is never
written. Auxiliary context is represented only by boolean indicators and is
not treated as directly citable evidence.

The report adds evidence-preview coverage totals and maps generated `[E#]`
IDs to cited preview records. Missing previews remain manual-review readiness
signals rather than generation failures. `citation_id_coverage_rate` remains
unchanged and does not measure semantic faithfulness.

Export the evidence-backed worksheet:

```bash
uv run python scripts/export_naive_rag_manual_review.py \
  --input artifacts/reports/retrieval/naive_rag_generation_eval_expanded_with_evidence.json \
  --output artifacts/reports/retrieval/naive_rag_generation_eval_expanded_manual_review_with_evidence.md
```

The worksheet includes an evidence table and keeps all claim-level reviewer
verdicts unchecked. No retrieval ranking, selection, fallback, prompt,
generation, citation guard, OpenRouter, Qdrant, indexing, or corpus behavior
changes in Phase 9C.3. Phase 10 remains out of scope.

Live Phase 9C.3 result:

```text
status = expanded_generation_eval_passed
passed_cases = 5 / 5
evidence_preview_case_count = 4
evidence_preview_total_count = 20
cited_evidence_preview_total_count = 14
evidence_preview_missing_count = 0
all_cited_ids_have_preview_rate = 1.0
cases_missing_evidence_preview = []
manual review status = evidence_preview_review_ready
```

All four generated-answer cases now contain selected evidence previews. The
annual-leave fallback has no prompt evidence preview because generation was
not allowed and the LLM was not called. The two all-caution cases remain
priority manual-review cases.

## Evaluation Command

```bash
uv run --extra qdrant --extra embedding python scripts/evaluate_dense_retrieval.py \
  --queries data/eval/manual_retrieval_queries.jsonl \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --output artifacts/reports/retrieval/dense_retrieval_eval.json
```

## Manual Command

```bash
uv run --extra qdrant --extra embedding python scripts/run_dense_retrieval.py \
  --query "Quyền sử dụng đất của hộ gia đình là gì?" \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 10 \
  --device cpu \
  --output artifacts/reports/retrieval/manual_query_result.json
```

## Next Work

1. Review Phase 9C failed cases and aggregate safety metrics.
2. Manually inspect semantic faithfulness; citation ID coverage is not enough.
3. Decide operational thresholds for when `needs_review` should become fallback.
4. Expand the generation dataset only with reviewed legal expectations.
5. Keep hybrid retrieval, RRF, and reranking for Phase 10.
