# Retrieval Quality Generalization Audit

This audit covers the legal QA path from user question through sparse/dense
retrieval, fusion, evidence packet construction, evidence selection, prompt
evidence mapping, citation guarding, API metadata mapping, and benchmark
diagnostics. It was created while reviewing commits `b27793d` and `6642112`.

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

| ID | File | Function/Class | Behavior | Trigger | Stage | Original classification | Final disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R01 | `src/retrieval/sparse_retriever.py` | `tokenize_sparse_text` | NFC/casefold Unicode tokenization preserving Vietnamese diacritics and numbers. | Any sparse query/index text. | Query/index normalization | A | KEEP |
| R02 | `src/retrieval/sparse_retriever.py` | removed `expand_legal_query_tokens` | Added termination/notice/unlawful tokens. | Labor termination phrases. | Query expansion | C | REMOVE |
| R03 | `src/retrieval/sparse_retriever.py` | removed duplicated query tokens | Repeated expansion tokens to alter BM25 term frequency. | Labor termination phrases. | Sparse weighting | C | REMOVE |
| R04 | `src/retrieval/sparse_retriever.py` | `_indexable_text` | Indexes law metadata, article title, bounded local parent context, and child text. | Sparse index build. | Sparse indexing | A | KEEP |
| R05 | `src/retrieval/evidence.py` | `_packet_metadata` | Propagates article title, hierarchy path, and local parent context. | Evidence packet build. | Evidence construction | A | KEEP |
| R06 | `src/retrieval/evidence.py` | `_local_parent_context` | Adds bounded text before child within parent text. | Child appears in parent. | Parent context | A | KEEP |
| R07 | `src/retrieval/selection.py` | `_selection_sort_key` | Sorts selected evidence by bounded adjusted relevance, rank, and stable ID. | Evidence selection. | Selection | B | GENERALIZE |
| R08 | `src/retrieval/selection.py` | eval exact target gate | Offline evaluation can require exact selected target presence. | Explicit evaluator targets. | Evaluation gate | A | KEEP |
| R09 | `src/retrieval/selection.py` | removed termination constants | Employee/employer, notice, and unlawful termination scoring. | Labor termination text. | Selection | C | REPLACE |
| R10 | `src/retrieval/selection.py` | `_explicit_locator_alignment` | Rewards exact Article/Clause/Point locator matches from the query. | `Điều`, `Khoản`, `Điểm`. | Selection | B | KEEP |
| R11 | `src/retrieval/selection.py` | title/content/local context overlap | Bounded overlap across article title, citable text, and local parent lead-in. | Meaningful query tokens. | Selection | B | GENERALIZE |
| R12 | `src/retrieval/selection.py` | law-title alignment | Rewards named-law consistency and penalizes law-title mismatch. | Law markers in query. | Selection | B | GENERALIZE |
| R13 | `src/retrieval/selection.py` | `_role_alignment` | Rewards exact legal role alignment. | Generic Vietnamese legal role phrases. | Selection | B | GENERALIZE |
| R14 | `src/retrieval/selection.py` | `_governing_role_alignment` | Penalizes wrong governing actor. | Generic Vietnamese legal role phrases. | Selection | B | GENERALIZE |
| R15 | `src/retrieval/selection.py` | `_modality_negation_alignment` | Aligns permission/obligation/prohibition and negation. | Generic modality and negation terms. | Selection | B | GENERALIZE |
| R16 | `src/retrieval/selection.py` | notice-term alignment | Aligns notice-period concepts without Article 35/36 branching. | Generic notice terms. | Selection | B | GENERALIZE |
| R17 | `src/retrieval/selection.py` | `_time_quantity_alignment` | Rewards matching deadlines/quantities and penalizes missing/wrong time evidence. | Numeric + unit or time/quantity question terms. | Selection | B | GENERALIZE |
| R18 | `src/retrieval/selection.py` | `_reference_only_adjustment` | Demotes reference-only chunks unless query explicitly targets that locator. | Generic cross-reference phrases. | Selection | B | GENERALIZE |
| R19 | `src/retrieval/selection.py` | `_domain_mismatch_adjustment` | Penalizes law-title mismatch when query names a law domain. | Law markers in query. | Selection | B | GENERALIZE |
| R20 | `src/retrieval/selection.py` | `_procedural_drift_adjustment` | Penalizes procedural provisions when query lacks procedural intent. | Generic procedural terms. | Selection | B | GENERALIZE |
| R21 | `src/retrieval/selection.py` | `_legal_consequence_drift_adjustment` | Penalizes consequence/cancellation/prohibition articles when not asked. | Generic consequence terms. | Selection | B | GENERALIZE |
| R22 | `src/retrieval/fusion.py` and `src/retrieval/coverage_aware.py` | weighted RRF and fixed quota | Combines dense/sparse ranks with configured weights and preserves hybrid metadata. | Hybrid retrieval. | Fusion/retrieval orchestration | A | KEEP |
| R23 | `src/retrieval/prompting.py` and `src/retrieval/generation.py` | prompt order and citation guard | Maps selected evidence to `[E#]` and rejects unknown citation IDs. | Prompt/generation validation. | Citation alignment | A | KEEP |
| R24 | `tests/integration/retrieval/test_direct_article_priority_workflow.py` | original holdout oracle | Expected articles could pass as non-primary supporting evidence. | Holdout tests. | Evaluation oracle | D | REPLACE |

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
  --repo-root <checkout> \
  --corpus /home/phat/AI_Project/VnLaw-QA/data/processed/legal_chunks.jsonl \
  --candidate-top-k 50 \
  --evidence-budget 5 \
  --output /tmp/<report>.json
```

Metric contracts are emitted in each JSON report. Matching is exact at the
target's specified granularity: law ID and Article are always required; Clause
and Point are required when present. Recall@5 and Recall@10 are micro-averaged
over expected targets. Primary evidence accuracy requires
`selected_evidence[0]` to match the primary target. Citation alignment requires
all expected targets in prompt evidence and, when a primary target is present,
`prompt.evidence[0]` to match that primary target. Multi-article coverage
requires every expected target selected and cited. Regression counting includes
pass-to-fail, primary/citation/multi-target losses, and candidate-rank losses
even when the case still passes.

## Reproducible Before/After Metrics

The same runner, corpus, top-k values, evidence budget, and evaluator were run
against detached worktrees for `6642112` and `a62b0cc`. Reports were written to
`/tmp` and no protected data path was modified.

| Metric | `6642112` before | `a62b0cc` after |
| --- | ---: | ---: |
| Expected Evidence Recall@5 | 1.0000 | 0.9355 |
| Expected Evidence Recall@10 | 1.0000 | 1.0000 |
| Expected Article MRR | 0.9400 | 0.9020 |
| Primary Evidence Accuracy | 0.6000 | 1.0000 |
| Citation Alignment Accuracy | 0.5667 | 1.0000 |
| Cross-reference-only Primary Error Rate | 0.0000 | 0.0000 |
| Wrong-actor Primary Error Rate | 0.0667 | 0.0000 |
| Wrong-domain Primary Error Rate | 0.1333 | 0.0000 |
| Multi-article Coverage Accuracy | 0.0000 | 1.0000 |
| Passing cases | 16 / 30 | 30 / 30 |
| Regression count | n/a | 3 candidate-rank losses |

Improved cases: 14. Unchanged cases: 13. Regressed case-target ranks: 3.
Largest positive rank change: 0. Largest negative rank change: -5.

Rank regressions that remain semantically passing:

- `employee_unilateral_termination`: `BLLD_VBHN / Điều 35`, rank 5 -> rank 7.
- `employee_notice_period`: `BLLD_VBHN / Điều 35 / Khoản 1`, rank 2 -> rank 4.
- `employee_no_notice`: `BLLD_VBHN / Điều 35 / Khoản 2`, rank 1 -> rank 6.

These are development/regression labor cases affected by removal of
termination-specific sparse expansion and duplicated BM25 token weighting.
They do not cause primary-evidence or citation failures after selection, but
they are still reported as candidate-rank regressions and prevent a final PASS
claim without an accepted materiality decision or further generic retrieval
work.

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
- Local Qdrant was unavailable on `localhost:6333`, and local BGE-M3 model
  paths checked in this session were absent. Actual local dense/Qdrant hybrid
  validation was therefore not run.
- Deterministic dense-candidate plus hybrid-fusion integration fixtures cover
  semantic dense evidence versus lexical overlap, multi-article coverage, and
  explicit cross-reference target behavior. Fixture validation is not a
  substitute for real Qdrant/BGE-M3 validation, so the current status remains
  PARTIAL.
