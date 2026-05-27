---
name: vnlaw-legal-accuracy
description: Use for any task involving legal answers, citations, legal document hierarchy, legal validity dates, confidence fallback, hallucination prevention, or Vietnamese legal QA safety.
---

# Legal Accuracy and Citation Skill

This is the highest-priority VnLaw-QA skill.

Use it whenever a task affects legal answers, citations, retrieval evidence, legal validity, fallback behavior, or user-facing legal QA.

## Non-Negotiable Rules

- Never let the LLM invent laws, articles, clauses, points, penalties, procedures, or citations.
- Every answer must be grounded in retrieved legal documents.
- Every legal claim must have a citation.
- If confidence is below the threshold, default `0.75`, use fallback instead of guessing.
- Do not provide professional legal advice.
- Always preserve source traceability.

## Required Citation Format

Clause-level citation:

```text
According to Clause {X}, Article {Y}, {Law Name} {Year or VBHN Version}: "{quoted legal content}"
```

Point-level citation:

```text
According to Point {A}, Clause {X}, Article {Y}, {Law Name} {Year or VBHN Version}: "{quoted legal content}"
```

If the answer paraphrases instead of quotes, do not present the paraphrase as a direct quote.

## Fallback Response

If the answer is unsupported or confidence is too low:

```text
I could not find a specific regulation for this issue in the current legal corpus. Please check thuvienphapluat.vn directly or consult a qualified lawyer.
```

## Required Legal Metadata

Every cited document must preserve:

```text
law_id
law_name
year
effective_date
expiry_date
status
hierarchy
source_url
crawled_at
parser_version
```

Use query date when available. If no query date is provided, use the current date or a documented default.

## Conflict Resolution

If retrieved documents conflict:

1. Prefer higher legal tier.
2. Prefer the effective version at query date.
3. Prefer VBHN where applicable.
4. Report uncertainty instead of forcing an answer.

## Answer Structure

Use this structure in generation prompts:

```text
Legal issue identified:
Applicable provisions:
Analysis based only on retrieved law:
Conclusion:
Sources:
Safety note:
```

## OOP and Docstring Rules

Expected components:

```text
CitationValidator
LegalValidityResolver
ConfidencePolicy
FallbackPolicy
LegalAnswerVerifier
```

Rules:

- Keep citation validation separate from answer generation.
- Use typed citation models.
- Public classes/functions must have Google-style docstrings.
- Docstrings must explain legal validity assumptions and failure behavior.

## Review Checklist

- [ ] Every legal claim has a citation.
- [ ] Citation exists in retrieved context.
- [ ] Law version is valid for query date.
- [ ] Unsupported claims are removed or fallback is used.
- [ ] The answer does not claim to be legal advice.
- [ ] Source URL and hierarchy are preserved.

## Do Not

- Do not cite a document not present in context.
- Do not paraphrase a law as if it were an exact quote.
- Do not hide missing evidence.
- Do not use general web content as legal truth unless explicitly approved.
- Do not answer based on memory.
- Do not let confidence scoring be ignored.