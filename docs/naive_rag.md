# Naive RAG Baseline

This document is the canonical technical reference for the completed dense
retrieval and fallback-aware Naive RAG baseline.

## Architecture

The baseline flow is:

```text
Vietnamese legal query
-> BGE-M3 dense query embedding
-> read-only Qdrant dense retrieval
-> typed retrieval results
-> EvidenceBundle assembly
-> EvidenceSelectionResult gate
-> fallback if decision != answer_allowed
-> selected-evidence-only prompt if decision == answer_allowed
-> OpenRouter generation
-> citation-ID guard
-> answer or deterministic fallback
```

Implemented retrieval/RAG entrypoints are thin wrappers under
`scripts/retrieval/`; reusable logic lives under `src/retrieval/`.

## Safety Invariants

- Rejected, unsafe, or unselected evidence is never included in the generation
  prompt.
- Only `EvidenceSelectionResult.selected_evidence` can be used for generation.
- Auxiliary parent context is marked as not directly citable and must not be
  cited as direct legal support.
- `decision != answer_allowed` implies `llm_called=false`.
- Fallback answers do not contain substantive unsupported legal claims.
- Generated `[E#]` citation IDs must map to selected prompt evidence.
- Citation-ID integrity is not semantic faithfulness.
- The system supports legal research and is not production legal advice.

## Configuration

Non-secret OpenRouter defaults live in `configs/llm/openrouter.yml`.
Provider secrets belong only in the real environment or an uncommitted `.env`.
They are not stored in YAML, printed, logged, or serialized into reports.

Resolution order:

```text
model: --model > OPENROUTER_MODEL > config default_model > emergency fallback
base URL: OPENROUTER_BASE_URL > config base_url > emergency fallback
API key: environment/.env only
```

The CLI loads `.env` automatically without overriding already exported
environment variables.

## Running the Baseline

Run a single Naive RAG query:

```bash
uv run --extra qdrant --extra embedding python scripts/retrieval/run_naive_rag.py \
  --query "Trẻ em dưới 6 tuổi được hưởng bảo hiểm y tế như thế nào?" \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --provider openrouter \
  --model google/gemini-2.5-flash \
  --output artifacts/reports/retrieval/naive_rag_single_query.json
```

Run the dense retrieval evaluation:

```bash
uv run --extra qdrant --extra embedding python scripts/retrieval/evaluate_dense_retrieval.py \
  --queries data/eval/manual_retrieval_queries.jsonl \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --output artifacts/reports/retrieval/dense_retrieval_eval.json
```

Run the selection smoke test:

```bash
uv run --extra qdrant --extra embedding python scripts/retrieval/run_selection_smoke.py \
  --queries data/eval/manual_retrieval_queries.jsonl \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --output artifacts/reports/retrieval/selection_smoke_report.json
```

## Generation Evaluation

The repeatable generation evaluation uses five reviewed cases:

```text
health_insurance_children_under_6_generation
annual_leave_days_generation
civil_code_scope_generation
marriage_conditions_generation
civil_rights_protection_generation
```

Run the evaluation with evidence previews:

```bash
uv run --extra qdrant --extra embedding python scripts/retrieval/evaluate_naive_rag_generation.py \
  --queries data/eval/manual_naive_rag_generation_queries.jsonl \
  --collection-name vnlaw_chunks_bgem3_v1_full \
  --url http://localhost:6333 \
  --top-k 20 \
  --device cpu \
  --provider openrouter \
  --model google/gemini-2.5-flash-lite \
  --output artifacts/reports/retrieval/naive_rag_generation_eval_hardened.json \
  --include-evidence-preview \
  --evidence-preview-chars 500
```

Deterministic checks cover decision policy, LLM-call policy, fallback policy,
citation-ID coverage, likely Vietnamese output, forbidden phrases, and
secret-like leakage. The latest hardened run passed all five deterministic
cases with zero unknown citation IDs, zero missing citation IDs, and zero
secret-leak failures.

## Manual Faithfulness Review

Manual review checks:

```text
generated claim -> cited evidence ID -> safe child evidence preview -> verdict
```

The latest reviewed verdicts are stored in
`data/eval/manual_faithfulness_verdicts.json`.

Current case verdicts:

```text
health_insurance_children_under_6_generation -> pass
annual_leave_days_generation -> not_applicable_for_fallback
civil_code_scope_generation -> pass
marriage_conditions_generation -> partial
civil_rights_protection_generation -> pass
```

Claim/finding counts after prompt hardening:

```text
supported claims: 9
too-broad claims: 1
missing-key-condition findings: 1
unsupported claims: 0
irrelevant-citation findings: 0
needs-more-evidence findings: 0
```

`annual_leave_days_generation` remains the fallback control case:

```text
decision=fallback_required
llm_called=false
substantive legal claims generated=false
```

## Offline Quality Gate

The offline quality gate combines the generation report, the reviewed manual
verdict manifest, and `configs/retrieval/quality_gate.yml`.

Run:

```bash
uv run python scripts/retrieval/evaluate_quality_gate.py \
  --generation-report artifacts/reports/retrieval/naive_rag_generation_eval_hardened.json \
  --faithfulness-verdicts data/eval/manual_faithfulness_verdicts.json \
  --policy configs/retrieval/quality_gate.yml \
  --output artifacts/reports/retrieval/quality_gate.json
```

Latest result:

```text
status: quality_gate_passed
hard_gate_passed: true
quality_gate_passed: true
hard_violations: 0
quality_violations: 0
warnings: 2
```

Both warnings are from the non-blocking
`marriage_conditions_generation` case: one too-broad foreign-element finding
and one missing-key-condition finding caused by incomplete selected evidence
coverage for the general condition-list question.

The gate is offline. It does not call OpenRouter, Qdrant, retrieval,
generation, indexing, or corpus processing.

## Final Baseline Status

Closure status: completed with known limitations.

Quality gate: passed.

Proceed to next planned stage: yes.

Prompt hardening reduced too-broad findings from six to one.
`civil_code_scope_generation` and `civil_rights_protection_generation`
improved from partial to pass. `marriage_conditions_generation` remains
partial and non-blocking.

## Known Limitations

1. The generation evaluation dataset contains only five reviewed cases.
2. The dataset is a regression baseline, not broad proof of Vietnamese legal
   QA quality.
3. `marriage_conditions_generation` remains partial and non-blocking.
4. Complete-list questions require fuller selected evidence coverage.
5. Dense-only retrieval still falls back for the annual-leave control case.
6. Citation-ID validity does not guarantee semantic faithfulness.
7. Model output may vary across runs.
8. The system is not production legal advice.

## Next-Stage Boundary

The completed baseline intentionally does not implement hybrid retrieval,
sparse/BM25 retrieval, RRF, reranking, query rewriting, GraphRAG, agents,
FastAPI endpoints, an LLM judge, corpus mutation, re-indexing, or production
legal-advice claims.

Future retrieval improvements must remain separately scoped and preserve the
safety invariants above.
