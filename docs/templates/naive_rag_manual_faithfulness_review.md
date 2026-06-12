# Naive RAG Manual Faithfulness Review Template

Use this template to inspect generated legal answers against the selected
evidence referenced by `[E#]` citation IDs. Citation-ID integrity alone does
not establish semantic faithfulness or legal correctness.

## Review Method

1. Separate the answer into material legal claims.
2. Record every `[E#]` attached to each claim.
3. Open the corresponding selected evidence and verify its source, hierarchy,
   and text.
4. Check that the answer does not broaden the rule, omit a controlling
   condition, combine unrelated provisions, or treat auxiliary parent context
   as directly citable evidence.
5. Inspect every caution-marked evidence item. An all-caution case requires
   special attention and may need more evidence even when citation IDs are
   valid.
6. Assign one verdict:
   - `pass`: every material claim is supported without material overstatement.
   - `partial`: core claims are supported but some detail is incomplete or too
     broad.
   - `fail`: a material claim conflicts with or is unsupported by its evidence.
   - `needs_more_evidence`: available evidence cannot support a reliable
     verdict.
   - `not_applicable_for_fallback`: no generated legal answer was produced.

## Case

- Case ID:
- Query:
- Decision:
- Blocking:
- Manual review required:
- All selected evidence caution:
- Preliminary verdict: `unchecked`

## Claim-to-Citation Checklist

| Claim | Citation IDs | Reviewer check | Notes |
| --- | --- | --- | --- |
| | | unchecked | |

## Evidence Notes

| Citation ID | Legal source and hierarchy | Supporting text summary | Caution notes |
| --- | --- | --- | --- |
| | | | |

Evidence previews must contain only bounded safe-citable child text. Do not
copy full parent Article context into this worksheet. Record auxiliary context
presence separately and never treat it as directly citable evidence.

## Fallback Review

Review fallback cases separately:

- [ ] The LLM was not called.
- [ ] The response avoided unsupported legal claims.
- [ ] The fallback reason matches the evidence limitation.
- [ ] Verdict is `not_applicable_for_fallback` when appropriate.

This review supports legal research quality control. It is not professional
legal advice and does not make the system production-ready.
