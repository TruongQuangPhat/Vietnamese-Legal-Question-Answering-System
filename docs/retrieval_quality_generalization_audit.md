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

| File | Function/Class | Behavior | Trigger | Stage | Classification | Action |
| --- | --- | --- | --- | --- | --- | --- |
| `src/retrieval/sparse_retriever.py` | `tokenize_sparse_text` | NFC/casefold Unicode tokenization preserving Vietnamese diacritics and numbers. | Any sparse query/index text. | Query/index normalization | A | Keep |
| `src/retrieval/sparse_retriever.py` | removed `expand_legal_query_tokens` | Added termination/notice/unlawful tokens, including duplicated tokens. | Labor termination phrases. | Query expansion | C | Removed |
| `src/retrieval/sparse_retriever.py` | `_indexable_text` | Indexes law metadata, article title, bounded local parent context, and child text. | Sparse index build. | Sparse indexing | A/B | Keep |
| `src/retrieval/evidence.py` | `_packet_metadata` | Propagates article title, hierarchy path, and local parent context. | Evidence packet build. | Evidence construction | A/B | Keep |
| `src/retrieval/evidence.py` | `_local_parent_context` | Adds bounded text before child within parent text. | Child appears in parent. | Parent context | A | Keep |
| `src/retrieval/selection.py` | `_selection_sort_key` | Sorts selected evidence by eval target, bounded adjusted relevance, rank, stable ID. | Evidence selection. | Selection | B | Generalized |
| `src/retrieval/selection.py` | removed termination constants | Employee/employer, notice, and unlawful termination scoring. | Labor termination text. | Selection | C | Replaced |
| `src/retrieval/selection.py` | `_explicit_locator_alignment` | Rewards exact Article/Clause/Point locator matches from the query. | `Điều`, `Khoản`, `Điểm`. | Selection | B | Keep |
| `src/retrieval/selection.py` | title/content/local context overlap | Bounded overlap across article title, citable text, and local parent lead-in. | Meaningful query tokens. | Selection | B | Generalized |
| `src/retrieval/selection.py` | `_role_alignment`, `_governing_role_alignment` | Rewards exact legal role alignment and penalizes wrong governing actor. | Generic Vietnamese legal role phrases. | Selection | B | Generalized |
| `src/retrieval/selection.py` | `_modality_negation_alignment` | Aligns permission/obligation/prohibition and negation. | Generic modality and negation terms. | Selection | B | Generalized |
| `src/retrieval/selection.py` | `_time_quantity_alignment` | Rewards matching deadlines/quantities and penalizes missing/wrong time evidence. | Numeric + unit or `bao lâu/bao nhiêu/thời hạn`. | Selection | B | Added |
| `src/retrieval/selection.py` | `_reference_only_adjustment` | Demotes reference-only chunks unless query explicitly targets that locator. | Generic cross-reference phrases. | Selection | B | Generalized |
| `src/retrieval/selection.py` | `_domain_mismatch_adjustment` | Penalizes law-title mismatch when query names a law domain. | Law markers in query. | Selection | B | Added |
| `src/retrieval/selection.py` | `_procedural_drift_adjustment` | Penalizes procedural provisions when query lacks procedural intent. | Generic procedural terms. | Selection | B | Added |
| `src/retrieval/selection.py` | `_legal_consequence_drift_adjustment` | Penalizes consequence/cancellation/prohibition articles when not asked. | Generic consequence terms. | Selection | B | Added |
| `src/retrieval/fusion.py` | weighted RRF and quota selection | Combines dense/sparse ranks with configured weights and quotas. | Hybrid retrieval. | Fusion | A | Keep |
| `src/retrieval/coverage_aware.py` | `CoverageAwareQuotaRetriever` | Preserves fixed `selected_coverage_aware_quota` and runtime metadata. | Runtime hybrid retrieval. | Retrieval orchestration | A | Keep |
| `src/retrieval/prompting.py` | prompt evidence order | Maps selected evidence to `[E#]` in selection order. | Prompt build. | Citation alignment | A/B | Keep |
| `src/retrieval/generation.py` | citation guard | Rejects unknown citation IDs and fallback decisions. | Generated answer. | Citation guard | A | Keep |
| `src/services/legal_qa_context.py` | follow-up question preparation | Uses generic follow-up prefixes and recent context. | Conversation context. | Query preparation | B | Keep |
| `src/evaluation/benchmark/*` | benchmark schemas/validators | Validates qrels, targets, splits, fallback labels. | Evaluation. | Benchmark | A | Keep |
| `tests/integration/retrieval/test_direct_article_priority_workflow.py` | original holdout oracle | Expected articles could pass as non-primary supporting evidence. | Holdout tests. | Evaluation oracle | D | Replaced |

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
- Before/after aggregate metrics still need a reproducible runner before this
  phase can be called PASS.
- The current validation is sparse/evidence-selection focused. Full hybrid
  dense validation was not run in this audit because it would require the
  real embedding/Qdrant environment.
