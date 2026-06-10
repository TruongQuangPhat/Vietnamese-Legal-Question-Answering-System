# Phase 7 Warning Resolution Policy Audit

## Purpose

This audit defines how to interpret the 8,206 Phase 7 warnings before
production-quality indexing. It does not resolve warnings, change validator
rules, or modify legal chunks.

The governing principle is:

> Warnings are quality signals, not blockers. Hard failures are zero. Legal
> data must not be changed without evidence that a warning represents actual
> contamination or loss of legal meaning.

The analysis uses the report generated read-only by:

```bash
uv run python scripts/validate_processed_jsonl.py \
  --input data/processed/legal_chunks.jsonl \
  --config configs/processing/processed_jsonl_validation.yml \
  --output /tmp/processed_jsonl_validation_report.json \
  --pretty
```

## Current Phase 7 Readiness Snapshot

| Metric | Result |
| --- | ---: |
| Report status | `pass_with_warnings` |
| Embedding readiness | `ready_with_warnings` |
| Embedding ready | `true` |
| Total chunks | 40,389 |
| Valid chunks | 40,389 |
| Invalid chunks | 0 |
| Hard errors | 0 |
| Warnings | 8,206 |
| Payload-ready chunks | 40,389 |
| Payload ready rate | 1.0 |

No warning currently indicates a broken schema, invalid citation, bad hash,
missing hierarchy node, payload gap, or hard contamination marker.

## Warning Summary

### Warning Counts by Issue Code

| Issue code | Count | Share |
| --- | ---: | ---: |
| `TEXT_LENGTH_WARNING` | 4,645 | 56.6% |
| `WARNING_CONTAMINATION_FOUND` | 3,561 | 43.4% |
| **Total** | **8,206** | **100%** |

### Warning Counts by Chunk Kind

| Chunk kind | Warning events | Share |
| --- | ---: | ---: |
| `point_level` | 5,533 | 67.4% |
| `clause_level` | 2,663 | 32.5% |
| `article_level` | 10 | 0.1% |

The distribution is consistent with a corpus whose primary child units are
Points and Clauses. A warning count is not a count of defective chunks.

### Warning Counts by Law

| Law ID | Warnings | Main source |
| --- | ---: | --- |
| `BLHS_VBHN` | 1,096 | 1,080 short-text warnings |
| `LBVMT_VBHN` | 512 | 382 contamination-marker warnings |
| `LTATGT_VBHN` | 406 | 337 contamination-marker warnings |
| `LKBCB_VBHN` | 386 | Mixed |
| `LQLT_VBHN` | 350 | Mixed |
| `LDD_VBHN` | 314 | Mixed |
| `BLHH_VBHN` | 292 | 184 contamination-marker warnings |
| `BLTTHS_VBHN` | 287 | 249 short-text warnings |
| `LBHXH_VBHN` | 237 | Mixed |
| `LXD_VBHN` | 212 | Mixed |

High law-level counts should be interpreted relative to document size and
drafting style. They do not establish that a law has lower source quality.

### Warning Counts by Field

| Field | Warning incidences |
| --- | ---: |
| `text` | 5,187 |
| `parent_text` | 3,561 |
| `unknown` | 0 |

These are field incidences, not unique warning events:

- all 4,645 short-text warnings affect `text`;
- 3,019 contamination warnings are `parent_text`-only;
- 542 contamination warnings affect both `text` and `parent_text`;
- no contamination warning is `text`-only.

This placement strongly suggests that most contamination warnings are caused
by valid Article context shared by child chunks rather than by contamination
of the selected embedding unit.

### Top Contamination Markers

| Marker | Field incidences | `text` | `parent_text` |
| --- | ---: | ---: | ---: |
| `BỘ TRƯỞNG` | 3,935 | 502 | 3,433 |
| `CHỦ NHIỆM` | 178 | 28 | 150 |
| `CHỦ TỊCH QUỐC HỘI` | 123 | 24 | 99 |

Marker incidences can exceed contamination warning events because one chunk
can contain a marker in both fields or contain more than one configured
marker.

`BỘ TRƯỞNG` is primarily an authority/title phrase in substantive provisions.
Examples include rules assigning a Minister responsibility to issue detailed
regulations, authorize an organization, or define technical requirements.
It is therefore ambiguous by design and must remain warning-only.

### Short-Text Warning Summary

| Chunk kind | Short-text warnings | Share of short warnings |
| --- | ---: | ---: |
| `point_level` | 3,605 | 77.6% |
| `clause_level` | 1,039 | 22.4% |
| `article_level` | 1 | less than 0.1% |

Top short-text laws are `BLHS_VBHN` (1,080), `BLTTHS_VBHN` (249),
`BLDS_2015` (204), `LDD_VBHN` (194), and `LDN_VBHN` (164).

The reviewed examples are valid legal units, including concise list items such
as a ground for changing a surname, a condition ending guardianship, or a
required item in a legal entity's charter. Their meaning depends on the
surrounding Clause or Article, but their brevity does not make them invalid.

## Interpretation

### Contamination Warnings

The current authority markers are not reliable contamination classifiers:

- `BỘ TRƯỞNG` frequently appears inside operative legal provisions.
- `CHỦ NHIỆM` and `CHỦ TỊCH QUỐC HỘI` can identify a competent authority in
  substantive text as well as appear in signature regions.
- Article-level `parent_text` naturally repeats a marker for every child chunk
  belonging to that Article.

The read-only placement audit found 3,019 parent-only events and 542 events in
both fields. The shortest reviewed direct-text hits were still valid provisions
such as “Bộ trưởng Bộ Y tế quy định chi tiết Điều này.” No reviewed example was
a standalone signature or certification block.

Policy interpretation:

- keep these markers warning-only;
- do not remove authority phrases from legal provisions;
- prioritize direct `text` over `parent_text` when manually auditing risk;
- treat repeated parent-context warnings as context-selection signals, not
  proof of upstream contamination.

### Short-Text Warnings

Short text is expected in hierarchy-preserving legal chunking. Points often
represent one enumerated condition, object, exception, or consequence.
Merging them by default would weaken Point/Clause/Article traceability and
could make retrieval citations less precise.

Policy interpretation:

- short text must not block embedding;
- do not lower the threshold merely to reduce the warning count;
- do not drop or merge short chunks by default;
- retain the warning as an observability signal for retrieval evaluation;
- use the retrieved child citation and Article parent context during answer
  assembly when the child text is insufficient on its own.

Changing the canonical `text` or embedding contract is not approved by this
audit. Any later derived embedding representation must be evaluated separately
and must preserve the original chunk text and citation anchor.

## Policy Decisions

### Keep as Warning-Only

1. Keep `WARNING_CONTAMINATION_FOUND` warning-only for the current authority
   markers.
2. Keep `TEXT_LENGTH_WARNING` warning-only for non-empty, structurally valid
   chunks.
3. Keep parent-only marker findings warning-only.
4. Keep direct-text authority findings warning-only unless a later audit proves
   that the text is a signature/footer block rather than an operative rule.
5. Keep warning totals visible in reports; do not suppress them to make the
   gate appear cleaner.

### Defer to Phase 8

The following are retrieval/context concerns rather than corpus-validity
failures:

1. Select or compress `parent_text` after retrieval so answer context includes
   the relevant Article material without blindly passing unrelated authority
   language.
2. Preserve short child chunks as retrieval units and attach their citation,
   hierarchy metadata, and parent Article context during answer assembly.
3. Evaluate retrieval quality separately for short Points and Clauses before
   considering any derived embedding enrichment.
4. Track whether parent-only marker warnings affect context relevance,
   reranking, token budgets, or answer grounding.

These are policy requirements for later design review, not authorization to
start Phase 8 in this task.

### Consider Cleaner/Chunker Follow-Up

No immediate cleaner or chunker change is justified by the reviewed examples.
An upstream issue should be opened only when evidence shows one of these
patterns:

- direct `text` is predominantly a standalone signature, name, title, or
  certification block;
- direct `text` contains repeated footer/source boilerplate unrelated to the
  cited legal unit;
- a hierarchy node incorrectly includes material beyond the Article boundary;
- a short chunk is an extraction artifact rather than a complete legal Point
  or Clause.

A later manual audit should prioritize the 542 direct-text marker chunks,
especially the 59 under 100 characters. The shortest reviewed examples were
valid delegations, so length plus an authority marker is not sufficient
evidence for modification.

### Accept as Expected Legal Structure

Accept and document:

- concise Point-level list items;
- short Clause-level enumerations;
- provisions assigning regulatory authority to a Minister or other office;
- child chunks whose clean `text` inherits an authority marker only through
  shared Article `parent_text`;
- repeated warnings caused by one Article context being associated with
  several valid child chunks.

## Recommended Next Actions

1. Approve the current Phase 7 result as embedding-ready with warnings.
2. Preserve all 8,206 warnings in the validation report for auditability.
3. Before production indexing, perform a stratified manual review of direct
   marker hits by marker, law, chunk kind, and text length.
4. Define Phase 8 context-selection tests for parent-only marker warnings and
   concise child chunks.
5. Add retrieval evaluation cases for short but legally decisive Points and
   Clauses.
6. Require evidence and regression tests before any future cleaner, chunker,
   threshold, or severity change.

## Non-Goals

This policy audit does not:

- modify processed chunks or hierarchy files;
- resolve, suppress, reclassify, or recount warnings;
- change warning thresholds or markers;
- change the `text`/`parent_text` contract;
- authorize cleaner or chunker modifications;
- implement embedding, indexing, retrieval, context compression, or RAG;
- provide legal advice or assess the substantive validity of a law.

## Appendix: Representative Examples

### Short Legal Units

| Citation | Chars | Interpretation |
| --- | ---: | --- |
| Bộ luật Dân sự 2015, Khoản 1, Điều 8 | 13 | Valid enumerated basis: “Hợp đồng.” |
| Bộ luật Dân sự 2015, Điểm b, Khoản 1, Điều 62 | 28 | Valid guardianship-ending condition |
| Bộ luật Dân sự 2015, Điểm a, Khoản 2, Điều 77 | 26 | Valid required charter item |
| Bộ luật Dân sự 2015, Điểm c, Khoản 1, Điều 47 | 38 | Valid category of protected person |

These units need their Clause/Article context for interpretation, but they
remain precise legal citation anchors.

### Authority Marker Findings

| Placement | Example interpretation | Policy |
| --- | --- | --- |
| Direct `text` and `parent_text` | Minister is assigned authority to regulate or authorize | Keep warning-only |
| `parent_text` only | Another Clause/Point in the same Article mentions the Minister | Defer context selection |
| Short direct `text` | “Bộ trưởng ... quy định chi tiết Điều này.” | Accept as operative legal text |

The examples support monitoring and contextual handling, not deletion.
