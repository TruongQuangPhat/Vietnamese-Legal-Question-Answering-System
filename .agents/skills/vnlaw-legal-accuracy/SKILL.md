---
name: vnlaw-legal-accuracy
description: Use for any task involving legal answers, citations, legal document hierarchy, legal validity, evidence sufficiency, fallback behavior, hallucination prevention, or Vietnamese legal QA safety.
---

# Legal Accuracy and Citation Skill

This is the highest-priority VnLaw-QA skill.

Use it whenever a task affects legal answers, citations, retrieval evidence, legal hierarchy, legal validity, fallback behavior, or user-facing legal QA.

## Non-Negotiable Rules

* Never let the LLM invent laws, articles, clauses, points, penalties, procedures, dates, or citations.
* Every legal answer must be grounded in selected legal evidence.
* Every legal claim must cite selected evidence.
* No trusted evidence -> no confident legal answer.
* No traceable citation -> invalid legal answer or fallback.
* Parent context is auxiliary only and not directly citable.
* Do not provide professional legal advice.
* Always preserve source traceability.

## Citation Requirements

Citations must refer to selected citation-ready evidence.

Citation-ready evidence should include:

```text
chunk_id or evidence_id
law_id
law_name when available
citation or legal reference
hierarchy when available
source_url
citable child text
```

Preserve these fields when available:

```text
year
version_or_vbhn
effective_date
expiry_date
status
crawled_at
parser_version
chunker_version
```

Do not require date-validity behavior unless a time-aware workflow is explicitly implemented and evaluated.

## Required Citation Style

Clause-level citation:

```text
According to Clause {X}, Article {Y}, {Law Name} {Year or VBHN Version}: "{quoted legal content}"
```

Point-level citation:

```text
According to Point {A}, Clause {X}, Article {Y}, {Law Name} {Year or VBHN Version}: "{quoted legal content}"
```

If the answer paraphrases instead of quotes, do not present the paraphrase as a direct quote.

If the system uses citation IDs, the final answer must cite only valid evidence IDs from selected evidence.

## Fallback Response

Use fallback when the answer is unsupported, unsafe, insufficiently evidenced, parent-context-only, missing required citation metadata, or outside the current corpus.

Recommended fallback:

```text
I could not find sufficient legal basis in the current corpus to answer this safely. Please check the official legal source directly or consult a qualified legal professional.
```

## Fallback Triggers

Fallback is required when:

```text
retrieval returns no useful evidence
selected evidence is empty
selected evidence is parent-context-only
citation metadata is missing
citation ID validation fails
the answer cites an unknown evidence ID
the question is outside the current corpus
evidence is insufficient, indirect, or unsafe
strict evaluation mode has explicit empty expected targets
```

## Conflict Resolution

If retrieved documents conflict:

1. Prefer the stronger legal source or higher legal authority when this metadata is available.
2. Prefer VBHN when applicable and available.
3. Prefer the version valid for the query date only if time-aware validity is explicitly supported.
4. Report uncertainty or fallback instead of forcing an answer.

Do not guess validity dates or legal hierarchy when metadata is missing.

## Answer Structure

Use this structure in generation prompts:

```text
Legal issue identified:
Applicable provisions:
Analysis based only on selected evidence:
Conclusion:
Sources:
Limitations / safety note:
```

## Citation Guard and Answerability Guard

The current legal QA workflow must preserve:

* strict citation ID validation;
* no citations outside selected evidence;
* fallback when citation validation fails;
* fallback when answerability evidence is insufficient;
* fallback-required cases must not be answered during strict evaluation.

Citation ID validity is necessary, but it is not the same as full human legal faithfulness review.

## OOP and Docstring Rules

Expected components may include:

```text
CitationValidator
CitationGuard
LegalValidityResolver
EvidenceSufficiencyPolicy
FallbackPolicy
LegalAnswerVerifier
```

Rules:

* Keep citation validation separate from answer generation.
* Use typed citation/evidence models.
* Public classes/functions must have Google-style docstrings where project style requires it.
* Docstrings must explain legal validity assumptions, citation requirements, and fallback behavior.

## Review Checklist

* [ ] Every legal claim has a citation.
* [ ] Every citation ID exists in selected evidence.
* [ ] Selected evidence contains citable child text.
* [ ] Parent context is not treated as directly citable.
* [ ] Unsupported claims are removed or fallback is used.
* [ ] The answer does not claim to be professional legal advice.
* [ ] Source URL and hierarchy are preserved where available.
* [ ] Time-aware validity is not claimed unless implemented and evaluated.

## Do Not

* Do not cite a document not present in selected evidence.
* Do not cite parent context as if it were direct legal evidence.
* Do not paraphrase a law as if it were an exact quote.
* Do not hide missing evidence.
* Do not use general web content as legal truth unless explicitly approved.
* Do not answer based on model memory.
* Do not ignore citation validation.
* Do not bypass fallback when evidence is insufficient.
* Do not claim human legal review has occurred unless it has.
