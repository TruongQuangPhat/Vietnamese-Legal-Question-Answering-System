# Retrieval Quality Generalization Audit

This audit covers the legal QA path from user question through sparse/dense
retrieval, fusion, evidence packet construction, evidence selection, prompt
evidence mapping, citation guarding, API metadata mapping, and benchmark
diagnostics. It was created while reviewing commits `b27793d` and `6642112`.
The benchmark framework boundaries and direct-evidence diagnostic disposition
are documented in `docs/benchmark_architecture_audit.md`.

## Summary

The repository-wide search found that the main adaptive runtime logic affecting
primary evidence quality was concentrated in:

- `src/retrieval/sparse_retriever.py`
- `src/retrieval/selection.py`
- benchmark assertions in `tests/integration/retrieval/test_direct_article_priority_workflow.py`

Fusion, coverage-aware quota selection, dense retrieval metadata handling,
evidence safety, prompt evidence mapping, citation ID validation, fallback
contracts, and API response metadata were reviewed and remain generic.

## Rule Inventory

The inventory now separates original classification from final disposition.
Unique reviewed rules reconcile exactly with the total: 24.

Original classification totals:

- A. Generic and justified: 7
- B. Legal-domain-specific but justified: 13
- C. Topic-specific and insufficiently justified: 3
- D. Question-specific or article-specific: 1
- E. Obsolete, duplicated, or dead logic: 0

Final disposition totals:

- KEEP: 8
- GENERALIZE: 12
- REPLACE: 2
- REMOVE: 2
- ISOLATE: 0

Runtime status totals:

- Active generic/domain rule: 21
- Removed runtime rule: 2
- Replaced test oracle: 1
- Unresolved category C runtime rule: 0
- Unresolved category D runtime rule: 0

| ID | File and function | Original classification | Trigger | Pipeline stage | False-positive risk | False-negative risk | Final disposition | Replacement or generalized abstraction | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R01 | `src/retrieval/sparse_retriever.py::tokenize_sparse_text` | A | Any sparse query/index text. | Query/index normalization | Low: generic Unicode tokens can match common words. | Low: no Vietnamese word segmentation. | KEEP | NFC/casefold Unicode tokenization preserving legal numbers. | `tests/unit/retrieval/test_sparse_retriever.py`, `tests/integration/retrieval/test_sparse_bm25_workflow.py` |
| R02 | `src/retrieval/sparse_retriever.py::expand_legal_query_tokens` | C | Labor termination phrases. | Query expansion | High: pulled termination articles into unrelated labor/civil queries. | Medium: helped colloquial termination wording. | REMOVE | Rely on original query tokens, dense retrieval, parent context, and generic selection alignment. | `tests/unit/retrieval/test_sparse_retriever.py`, direct benchmark runner |
| R03 | `src/retrieval/sparse_retriever.py` duplicated expansion tokens | C | Labor termination phrases. | Sparse weighting | High: silently changed BM25 term frequency for one topic. | Medium: removing it can lower Article 35 sparse ranks. | REMOVE | No duplicated-token weighting; rank losses are measured explicitly. | `tests/unit/evaluation/test_retrieval_quality_generalization.py`, `/tmp` comparison reports |
| R04 | `src/retrieval/sparse_retriever.py::_indexable_text` | A | Sparse index build. | Sparse indexing | Medium: metadata can increase lexical overlap. | Low: omitting metadata hurts exact locator search. | KEEP | Bounded metadata, article title, local parent context, child text. | `tests/unit/retrieval/test_sparse_retriever.py` |
| R05 | `src/retrieval/evidence.py::_packet_metadata` | A | Evidence packet build. | Evidence construction | Low: propagated metadata can be over-trusted downstream. | Medium: missing metadata breaks citation alignment. | KEEP | Structured metadata propagation. | `tests/unit/retrieval/test_evidence.py` |
| R06 | `src/retrieval/evidence.py::_local_parent_context` | A | Child appears in parent. | Parent context | Medium: parent lead-in may add nearby unrelated terms. | Medium: point chunks lack subject/action without it. | KEEP | Bounded local parent context, auxiliary only. | `tests/unit/retrieval/test_evidence.py`, direct benchmark |
| R07 | `src/retrieval/selection.py::_selection_sort_key` | B | Evidence selection. | Selection | Medium: score components may reorder close candidates. | Medium: direct evidence can stay below lexical distractors. | GENERALIZE | Bounded composable alignment score plus stable rank/id tie-break. | `tests/unit/retrieval/test_selection.py` |
| R08 | `src/retrieval/selection.py` eval exact target gate | A | Explicit evaluator targets. | Evaluation gate | Low: only active with evaluator-supplied targets. | Low: broad article targets may hide clause defects if configured too loosely. | KEEP | Evaluation-only exact target gate. | `tests/unit/retrieval/test_selection.py` |
| R09 | `src/retrieval/selection.py` removed termination constants | C | Labor termination text. | Selection | High: selected Article 35/36/39 based on topic keywords. | Medium: removal lowers some candidate ranks. | REPLACE | Generic role, modality, time/quantity, consequence, and domain alignment. | `tests/unit/retrieval/test_selection.py`, direct benchmark |
| R10 | `src/retrieval/selection.py::_explicit_locator_alignment` | B | `Điều`, `Khoản`, `Điểm`. | Selection | Low: explicit locators are strong legal signals. | Low: implicit questions get no locator bonus. | KEEP | Exact Article/Clause/Point locator alignment. | `tests/unit/retrieval/test_selection.py` |
| R11 | `src/retrieval/selection.py` title/content/local overlap | B | Meaningful query tokens. | Selection | Medium: keyword overlap can favor related but indirect text. | Medium: semantic matches with few shared tokens may be underweighted. | GENERALIZE | Bounded title/content/local-context overlap components. | `tests/unit/retrieval/test_selection.py` |
| R12 | `src/retrieval/selection.py` law-title alignment | B | Law markers in query. | Selection | Low: law title names can be ambiguous. | Medium: unnamed-law queries cannot use this signal. | GENERALIZE | Named-law consistency and mismatch penalty. | direct benchmark cross-domain cases |
| R13 | `src/retrieval/selection.py::_role_alignment` | B | Generic Vietnamese legal role phrases. | Selection | Medium: role phrase overlap can be superficial. | Medium: role omitted from short point chunks. | GENERALIZE | Generic subject/role alignment. | `tests/unit/retrieval/test_selection.py` |
| R14 | `src/retrieval/selection.py::_governing_role_alignment` | B | Generic Vietnamese legal role phrases. | Selection | Medium: may penalize adjacent actor context. | Medium: actor not explicit in candidate child text. | GENERALIZE | Generic governing-actor contradiction penalty. | `tests/unit/retrieval/test_selection.py` |
| R15 | `src/retrieval/selection.py::_modality_negation_alignment` | B | Generic modality and negation terms. | Selection | Medium: common words like `được` are broad. | Medium: implicit permission/prohibition may be missed. | GENERALIZE | Permission, obligation, prohibition, negation alignment. | `tests/unit/retrieval/test_selection.py` |
| R16 | `src/retrieval/selection.py` notice-term alignment | B | Generic notice terms. | Selection | Medium: `báo trước` appears outside termination. | Medium: synonym gaps remain without topic expansion. | GENERALIZE | Generic notice-term component without Article 35/36 branching. | `tests/unit/retrieval/test_selection.py` |
| R17 | `src/retrieval/selection.py::_time_quantity_alignment` | B | Numeric + unit or time/quantity question terms. | Selection | Medium: wrong numbers in related provisions can overlap. | Medium: textual numbers may be missed. | GENERALIZE | Deadline/quantity alignment and contradiction penalty. | `tests/unit/retrieval/test_selection.py` |
| R18 | `src/retrieval/selection.py::_reference_only_adjustment` | B | Generic cross-reference phrases. | Selection | Medium: mixed substantive/reference text can be over-demoted. | Medium: unusual cross-reference wording may be missed. | GENERALIZE | Reference-only demotion disabled for explicit targets. | `tests/unit/retrieval/test_selection.py`, hybrid fixture |
| R19 | `src/retrieval/selection.py::_domain_mismatch_adjustment` | B | Law markers in query. | Selection | Low: named-law mismatch is usually meaningful. | Medium: domain not named in many questions. | GENERALIZE | Generic law/domain consistency penalty. | cross-domain benchmark |
| R20 | `src/retrieval/selection.py::_procedural_drift_adjustment` | B | Generic procedural terms. | Selection | Medium: substantive questions can need procedure support. | Medium: procedural hard negatives without keywords may remain. | GENERALIZE | Generic procedural drift penalty. | direct benchmark, adversarial selection tests |
| R21 | `src/retrieval/selection.py::_legal_consequence_drift_adjustment` | B | Generic consequence terms. | Selection | Medium: consequence articles can be direct for consequence questions. | Medium: indirect consequence text without keywords may remain. | GENERALIZE | Generic consequence/prohibition drift penalty. | direct benchmark, adversarial selection tests |
| R22 | `src/retrieval/fusion.py` and `src/retrieval/coverage_aware.py` quota fusion | A | Hybrid retrieval. | Fusion/retrieval orchestration | Medium: quota can retain lower sparse/dense candidates. | Medium: final top 10 can discard target if neither source ranks it well. | KEEP | Fixed weighted RRF plus source quotas. | `tests/integration/retrieval/test_coverage_aware_retrieval_workflow.py`, hybrid fixture |
| R23 | `src/retrieval/prompting.py` and `src/retrieval/generation.py` prompt/citation guard | A | Prompt/generation validation. | Citation alignment | Low: prompt order follows selected order even if selection is wrong. | Low: generated semantic unsupported claims need separate review. | KEEP | Selected-evidence `[E#]` mapping and unknown-citation rejection. | `tests/unit/retrieval/test_generation.py`, direct benchmark |
| R24 | `tests/integration/retrieval/test_direct_article_priority_workflow.py` original holdout oracle | D | Holdout tests. | Evaluation oracle | High: expected article could pass as non-primary support. | High: semantic primary failures hidden. | REPLACE | Strict benchmark runner separates candidate, primary, selected, cited, forbidden evidence. | `tests/unit/evaluation/test_retrieval_quality_generalization.py`, direct benchmark |

Runtime status and remaining risk by rule:

| ID | Runtime status | Remaining risk |
| --- | --- | --- |
| R01 | Active generic runtime rule | Tokenization remains lexical and may miss Vietnamese word-boundary semantics. |
| R02 | Removed runtime rule | Colloquial termination recall relies on dense/hybrid retrieval and generic selection instead of expansion. |
| R03 | Removed runtime rule | Article 35 sparse ranks may remain lower, but top-10 cutoff tests guard primary/citation behavior. |
| R04 | Active generic runtime rule | Metadata text can still increase lexical overlap; runtime-aligned top-10 tests guard selection behavior. |
| R05 | Active generic runtime rule | Incorrect upstream metadata would still propagate; processed JSONL validation remains the upstream guard. |
| R06 | Active generic runtime rule | Parent context may add nearby terms; prompt and selection tests keep it auxiliary-only. |
| R07 | Active domain-generic runtime rule | Generic scoring still contains tuned bounded components; no known topic-specific branch remains. |
| R08 | Active evaluation-only rule | Broad article-level expected targets can hide clause specificity if an evaluator defines them too loosely. |
| R09 | Replaced runtime rule | Generic role/modality/consequence alignment can miss implicit semantics without dense evidence. |
| R10 | Active legal-domain runtime rule | Explicit locator alignment is strong; malformed locators may not be parsed. |
| R11 | Active generic runtime rule | Lexical overlap can still prefer related text in close cases; adversarial tests guard known failure modes. |
| R12 | Active legal-domain runtime rule | Named-law consistency helps only when the query names a law or domain. |
| R13 | Active legal-domain runtime rule | Role phrase extraction is shallow and can miss paraphrased actors. |
| R14 | Active legal-domain runtime rule | Governing-role contradiction can be under-applied when the role appears only in parent context. |
| R15 | Active legal-domain runtime rule | Modality and negation terms are generic but linguistically shallow. |
| R16 | Active generic runtime rule | Notice-term matching is no longer labor-specific but still lexical. |
| R17 | Active generic runtime rule | Numeric/time contradiction handling may miss textual numbers or implicit deadlines. |
| R18 | Active generic runtime rule | Mixed substantive/reference provisions can still be hard to classify perfectly. |
| R19 | Active legal-domain runtime rule | Domain mismatch only applies when law/domain markers are visible. |
| R20 | Active generic runtime rule | Procedural terms may be substantive for procedural questions; tests include procedural hard negatives. |
| R21 | Active generic runtime rule | Consequence/prohibition drift is generic but may underweight direct consequence questions. |
| R22 | Active generic runtime rule | Fusion top 10 can discard a target if both dense and sparse rank it below cutoff; benchmark cutoffs expose this. |
| R23 | Active generic runtime rule | Citation-ID validity still does not prove generated semantic faithfulness. |
| R24 | Replaced test oracle, not runtime | Direct-evidence diagnostic cases remain branch diagnostics until promoted into the frozen benchmark. |

## Commit Review Decisions

| Change from commits | Decision | Notes |
| --- | --- | --- |
| Termination-specific sparse expansion | REMOVE | Removed from runtime sparse retrieval. |
| Duplicated BM25 token weighting | REMOVE | Query tokens are no longer duplicated to alter BM25 term frequency. |
| Bounded local parent context | KEEP | Useful for point/clause chunks across domains. |
| Metadata propagation | KEEP | Article title and hierarchy metadata are necessary for generic alignment. |
| Employee/employer scoring | GENERALIZE | Replaced by generic role/governing-role alignment. |
| Unlawful-intent scoring | GENERALIZE | Replaced by generic consequence/prohibition drift and negation alignment. |
| Notice/no-notice scoring | GENERALIZE | Replaced by generic notice-term and modality/negation alignment. |
| Cross-reference handling | GENERALIZE | Reference-only demotion is generic and disabled for explicit targets. |
| Golden assertions | REPLACE | Kept as regression subset, but not the whole quality proof. |
| Holdout assertions from `6642112` | FIX | Annual leave and marriage-age now require strict primary evidence. |

## Oracle Defects Found

- `worker_annual_leave` required only Article 113 presence and allowed Article
  114 or sibling evidence to replace Clause 1 as primary.
- `marriage_age_condition` required Article 8.1.a presence but did not require
  it as primary, allowing Article 5.2.b to replace the direct condition.
- `weekly_and_annual_leave_multi_article` allowed article-level annual leave
  presence instead of requiring Clause 1 coverage.
- Diagnostics reported presence but did not distinguish candidate rank,
  selected primary, prompt primary, selected set, and citation set.

## Current Deterministic Benchmark

The integration benchmark now covers 30+ questions:

- 5 development/regression labor termination questions.
- 11 cross-topic holdouts from `6642112`, with corrected strict targets.
- 14 broad cross-domain holdouts across constitutional, criminal, civil
  procedure, criminal procedure, food safety, environment, enterprise,
  commerce, intellectual property, housing, tax, traffic, employment, and
  identity-card law.

The reproducible runner is:

```bash
uv run python scripts/evaluation/run_retrieval_quality_generalization_benchmark.py run \
  --mode runtime_aligned \
  --repo-root <checkout> \
  --corpus /home/phat/AI_Project/VnLaw-QA/data/processed/legal_chunks.jsonl \
  --sparse-retrieval-top-k 50 \
  --dense-retrieval-top-k 50 \
  --diagnostic-candidate-top-k 50 \
  --fusion-output-top-k 10 \
  --selection-input-top-k 10 \
  --selected-evidence-budget 5 \
  --output /tmp/<report>.json
```

The runner has two explicit modes:

- `runtime_aligned`: default and PR-gating mode. It retains a top-50 sparse
  diagnostic pool for rank, Recall@k, and MRR diagnostics, then truncates to
  the top 10 candidates before evidence packet construction, evidence
  selection, primary-evidence evaluation, citation mapping, and multi-article
  selected/cited coverage. It selects at most 5 evidence packets.
- `deep_diagnostic`: debugging-only mode. It retains a top-50 diagnostic pool
  and may pass up to 50 candidates into evidence selection. This mode can help
  explain missed top-10 cases, but must not be used to claim production
  readiness.

Every JSON report includes the benchmark mode, retrieval candidate limit,
selection input limit, selected evidence limit, production-alignment flag,
corpus path, runner/evaluator version, and evaluated git revision.

Metric contracts are emitted in each JSON report. Matching is exact at the
target's specified granularity: law ID and Article are always required; Clause
and Point are required when present. Article-level expectations are represented
with `clause_number = null` and `point_label = null`; this intentionally accepts
any clause or point from the same Article. Multiple acceptable clauses in the
same Article are represented as an article-level target when the benchmark
intent accepts any of them; otherwise each required clause is listed as a
separate expected target.

Retrieval metrics are calculated from the full diagnostic candidate pool:

- Recall@5;
- Recall@10;
- Expected Article MRR;
- expected target rank;
- rank regression.

Selection and citation metrics are calculated only after runtime-aligned
truncation to the top-10 selection input:

- Primary Evidence Accuracy;
- Citation Alignment Accuracy;
- Cross-reference-only Primary Error Rate;
- Wrong-actor Primary Error Rate;
- Wrong-domain Primary Error Rate;
- Multi-article Coverage Accuracy;
- semantic regression count.

Recall@5 and Recall@10 are micro-averaged over expected targets, so a
multi-article question contributes one denominator item per expected provision.
Expected Article MRR is macro-averaged per question using the best-ranked
expected target for that question. Primary evidence accuracy is macro-averaged
per question and requires `selected_evidence[0]` to match the primary target
after selection-input truncation. Citation alignment is macro-averaged per
question and requires all expected targets in prompt evidence plus
`prompt.evidence[0]` matching the primary target when one is defined.
Multi-article coverage is macro-averaged over multi-target cases only and
requires every expected target selected and cited from the runtime-aligned
selection pool. Regression counting includes semantic regressions and
candidate-rank losses. A semantic regression is a pass-to-fail,
primary/citation/multi-target loss, wrong-domain increase, wrong-actor
increase, or cross-reference-only primary error. A rank regression is an
expected target whose diagnostic-pool candidate rank moves lower or disappears,
even when the case still passes.

## Reproducible Before/After Metrics

Previous before/after metrics were produced before the benchmark was aligned
with the production top-10 selection input. They are superseded. Because the
oracle changed again, final before/after metrics must be regenerated manually
with the current evaluator against both `6642112` and the new branch HEAD. The
current Codex session intentionally did not execute the full benchmark runner.

Rank regressions that remain semantically passing:

- `employee_unilateral_termination`: `BLLD_VBHN / Điều 35`, rank 5 -> rank 7.
- `employee_notice_period`: `BLLD_VBHN / Điều 35 / Khoản 1`, rank 2 -> rank 4.
- `employee_no_notice`: `BLLD_VBHN / Điều 35 / Khoản 2`, rank 1 -> rank 6.

These are development/regression labor cases affected by removal of
termination-specific sparse expansion and duplicated BM25 token weighting.
They do not cause primary-evidence or citation failures in deterministic
sparse-only runtime-aligned tests using selection input 10, but they are still
reported as candidate-rank regressions and require actual local hybrid
validation before any final PASS claim.

The after-run Recall@5 value changed from an earlier manually reported 0.9333
to 0.9355 because the benchmark oracle now uses target-level micro-averaging
over 31 expected targets instead of a case-level or older 30-item denominator.
The corrected Q1 Article 35 expectation is article-level because either Clause
1 or Clause 2 can be primary for the broad unilateral-termination question, and
the multi-article weekly/annual leave case contributes two expected targets.
The older and newer values are therefore not directly comparable unless they
come from the same runner version.

## Runtime Cutoffs

The real runtime constructs `coverage_aware_quota` with:

- dense retrieval top-k: 50;
- sparse retrieval top-k: 50;
- candidates retained before fusion: 50 dense and 50 sparse;
- hybrid fusion output top-k: 10;
- evidence-selection input budget: 10 evidence packets from fused retrieval in
  the runtime path;
- final selected-evidence budget: 5.

The deterministic sparse benchmark after-refactor target ranks remain inside
the sparse retrieval cutoff of 50:

- `employee_unilateral_termination`: Article 35 rank 7;
- `employee_notice_period`: Article 35 Clause 1 rank 4;
- `employee_no_notice`: Article 35 Clause 2 rank 6.

These ranks are inside the sparse source cutoff but do not prove real hybrid
survival through the final fused top 10. Actual dense/Qdrant hybrid validation
is required to confirm fused rank, selected primary evidence, and prompt
citations under runtime cutoffs.

Selection input must be 10 because the production `coverage_aware_quota` path
passes only the fused top 10 to evidence construction and selection. Keeping the
diagnostic retrieval pool at 50 remains useful because sparse and dense source
rank movements, Recall@5/10, MRR, and missed-target root causes need visibility
beyond the final selected packets. The benchmark therefore distinguishes:

```text
retrieval candidate pool
→ runtime-aligned selection input
→ final selected evidence
```

The removed termination-specific query expansion and duplicated BM25 weighting
must not be restored just to recover Article 35 ranks. Those rules were
topic-specific and produced false positives in unrelated labor and cross-domain
queries. Generic dense retrieval, sparse original-query matching, bounded
parent context, RRF fusion, and generic selection alignment are the maintained
path.

## Actual Hybrid Validation

The safe manual entry point is:

```bash
uv run python scripts/evaluation/run_local_hybrid_retrieval_validation.py \
  --confirm-local-read-only \
  --question "<question>" \
  --expected-target "BLLD_VBHN:35" \
  --output /tmp/vnlaw-local-hybrid-validation.json
```

The script is read-only and fails before execution unless
`--confirm-local-read-only` is present. It uses local BGE-M3, read-only Qdrant
dense retrieval, local sparse retrieval, the existing coverage-aware quota
fusion implementation, evidence selection, and prompt citation mapping. It does
not create, recreate, delete, upload, or modify Qdrant collections; it does not
index or re-embed documents; it does not call a production endpoint; and it
does not call an external LLM.

Static configuration reviewed for manual validation:

- BGE-M3 model path environment variables: `EMBEDDING_MODEL_PATH` or
  `LEGAL_QA_EMBEDDING_MODEL_PATH`;
- Qdrant URL default: `http://localhost:6333`;
- Qdrant API-key environment variables: `LEGAL_QA_QDRANT_API_KEY` or
  `QDRANT_API_KEY` without printing the secret;
- collection: `vnlaw_chunks_bgem3_v1_full`;
- vector name: `dense`;
- expected dense dimension: 1024;
- sparse corpus path: `data/processed/legal_chunks.jsonl`;
- production-aligned defaults: sparse 50, dense 50, fused 10, selected 5.

Adversarial unit tests cover:

- semantic relevance versus keyword overlap;
- actor contradiction;
- negation contradiction;
- time contradiction;
- explicit cross-reference target;
- multi-article coverage.

## Remaining Limitations

- The broad benchmark is deterministic and useful for regression, but it is not
  a lawyer-reviewed benchmark and must not be used to claim broad legal QA
  quality.
- Actual local dense/Qdrant hybrid validation must be run manually with local
  BGE-M3 and the existing read-only Qdrant collection
  `vnlaw_chunks_bgem3_v1_full`. This Codex session did not load BGE-M3 or query
  Qdrant.
- Deterministic dense-candidate plus hybrid-fusion integration fixtures now
  model 50 sparse candidates plus 50 dense candidates, real coverage-aware
  fusion to fused top 10, selected evidence top 5, and prompt citation mapping.
  Fixture validation is not a substitute for real Qdrant/BGE-M3 validation, so
  the current status remains PARTIAL.
