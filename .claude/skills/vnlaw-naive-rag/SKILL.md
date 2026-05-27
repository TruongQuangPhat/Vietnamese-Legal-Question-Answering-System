---
name: vnlaw-naive-rag
description: Use when building the first Naive RAG baseline, simple retrieval, baseline prompt, strict citation generation, fallback handling, and baseline evaluation.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# Naive RAG Baseline Skill

Use this skill to build the first working legal QA baseline before Advanced RAG or GraphRAG.

## Goal

Build the simplest reliable legal QA pipeline.

```text
query
  → simple retrieval
  → parent context packing
  → legal QA prompt
  → strict citation answer
  → citation validation
  → fallback if unsupported
```

## Expected Files

```text
src/retrieval/vector_store.py
src/generation/llm_client.py
src/generation/prompts.py
src/generation/context_packer.py
src/generation/citation_validator.py
src/api/routes/qa.py
src/api/schemas.py

data/eval/golden_qa_v1.jsonl
tests/evaluation/run_ragas.py
tests/unit/generation/
tests/unit/retrieval/
```

## Baseline Retrieval

Start simple:

```text
dense vector search OR BM25
top-k candidates
parent article context
strict citation prompt
```

Avoid complex query rewriting, graph traversal, multi-agent orchestration, or fine-tuning at this stage.

## Prompt Requirements

The LLM must be instructed to:

- answer only from provided context;
- cite every legal claim;
- use Article/Clause/Point hierarchy;
- say it cannot find the rule when context is insufficient;
- avoid professional legal advice;
- distinguish quote from analysis.

## Baseline Answer Format

```text
Legal issue:
Applicable regulation:
Answer:
Sources:
Limitations:
```

## Minimum Fallback Behavior

Use fallback when:

```text
retrieval returns no useful context
top evidence is below confidence threshold
citation validation fails
question is outside the current corpus
```

## OOP and Docstring Rules

Expected components:

```text
NaiveRetriever
ContextPacker
LegalPromptBuilder
BaseLLMClient
CitationValidator
FallbackPolicy
QAService
```

Rules:

- Keep retrieval, generation, citation validation, and API route logic separate.
- Use typed models for candidates, evidence packets, citations, and responses.
- Public classes/functions must have Google-style docstrings.
- Docstrings must explain legal/RAG assumptions and fallback behavior.

## Definition of Done

- [ ] `/api/v1/qa` can answer from ingested corpus.
- [ ] Strict citation format is present.
- [ ] Unsupported questions trigger fallback.
- [ ] Golden QA evaluation can run.
- [ ] Empty retrieval is tested.
- [ ] Low-confidence fallback is tested.
- [ ] Citation validation is tested.
- [ ] No uncited legal claim is returned.

## Do Not

- Do not over-engineer the baseline.
- Do not add GraphRAG before the baseline works.
- Do not allow uncited legal claims.
- Do not use model memory as legal evidence.
- Do not skip citation validation.