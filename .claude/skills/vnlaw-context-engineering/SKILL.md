---
name: vnlaw-context-engineering
description: Use for legal prompt design, context packing, query rewriting, evidence ordering, citation anchors, answer structure, fallback behavior, and hallucination prevention.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# Context Engineering Skill

Use this skill to design prompts, evidence packets, and answer formats for Vietnamese legal QA.

## Objectives

- Maximize legal faithfulness.
- Keep citations traceable.
- Provide enough parent context without overloading the LLM.
- Prevent hallucination.
- Make fallback behavior explicit.
- Preserve legal validity information.

## Context Packet Format

Each evidence document should be packed as:

```text
[Evidence {i}]
Law: {law_name}
Law ID: {law_id}
Version: {year_or_vbhn}
Effective: {effective_date} to {expiry_date}
Hierarchy: {Part > Chapter > Section > Article > Clause > Point}
Source URL: {source_url}
Retrieval Score: {retrieval_score}
Rerank Score: {rerank_score}

Relevant child excerpt:
{content}

Parent article context:
{parent_content}
```

## Prompt Rules

The generation prompt must instruct the model to:

- use only provided evidence;
- cite every legal claim;
- never invent laws, articles, clauses, or points;
- distinguish quote from paraphrase;
- mention legal validity when query date matters;
- use fallback if evidence is insufficient;
- avoid giving professional legal advice beyond the cited documents.

## Query Processing Techniques

Use only when helpful:

- query normalization;
- date extraction;
- legal intent classification;
- entity extraction;
- legal term expansion;
- exact article detection;
- query decomposition for multi-part questions.

Do not apply query rewriting if it removes important legal terms.

## Evidence Ordering

Prefer ordering by:

1. direct exact citation match;
2. higher rerank score;
3. legal authority tier;
4. effective version at query date;
5. parent-child completeness;
6. cross-reference support;
7. source freshness.

## Context Budget Policy

When context is too large:

1. keep exact article/clause matches first;
2. keep parent article for direct evidence;
3. summarize only secondary cross-references;
4. drop low-score unrelated chunks;
5. never remove citation anchors.

## Answer Format

Default answer format:

```text
Issue:
Applicable law:
Analysis:
Conclusion:
Sources:
Limitations:
```

For low confidence:

```text
I could not find sufficient legal basis in the current corpus...
```

## Expected Components

```text
src/generation/prompts.py
src/generation/context_packer.py
src/generation/answer_formatter.py
src/generation/citation_validator.py
configs/prompts/legal_qa.j2
tests/unit/generation/
```

## OOP and Docstring Rules

Expected components:

```text
ContextPacker
LegalPromptBuilder
CitationAnchorBuilder
AnswerFormatter
FallbackPolicy
```

Rules:

- Keep prompt construction separate from retrieval and LLM client logic.
- Use typed evidence packet models.
- Public classes/functions must have Google-style docstrings.
- Docstrings must explain legal assumptions and fallback behavior.

## Do Not

- Do not stuff too many unrelated chunks.
- Do not mix expired and active laws without explaining validity.
- Do not hide low confidence.
- Do not summarize away citation anchors.
- Do not let the final answer cite evidence that was not provided.
- Do not rewrite queries in a way that changes legal meaning.