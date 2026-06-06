---
name: vnlaw-naive-rag
description: Use when building the first Naive RAG baseline, simple retrieval, baseline prompt, strict citation generation, fallback handling, and baseline evaluation.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# Naive RAG Baseline Skill

Use this skill to build the first working legal QA baseline (Phase 9) before Advanced RAG or GraphRAG.

**Prerequisites**: Phases 0-8 must be complete. Processed JSONL must validate. Embeddings must be indexed in Qdrant.

## Goal

Build the simplest reliable legal QA pipeline.

```text
query
→ dense retrieval (or BM25)
→ top-k candidates
→ parent context packing
→ legal QA prompt
→ strict citation answer
→ citation validation
→ fallback if unsupported
```

## Baseline Retrieval

Start simple:

```text
dense vector search OR BM25
top-k candidates (5-10)
parent article context (from parent_text)
strict citation prompt
```

Avoid complex query rewriting, graph traversal, multi-agent orchestration, or fine-tuning at this stage.

## Expected Files

```text
src/retrieval/vector_store.py        # Qdrant hybrid search
src/generation/llm_client.py         # LLM provider wrapper
src/generation/prompts.py            # Legal QA prompt templates
src/generation/context_packer.py     # Evidence packet assembly
src/generation/citation_validator.py # Citation integrity checks
src/generation/fallback_policy.py    # Low-confidence fallback
src/api/routes/qa.py                 # QA endpoint
src/api/schemas.py                   # Request/response models

data/eval/golden_qa_v1.jsonl
tests/evaluation/
tests/unit/generation/
tests/unit/retrieval/
```

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
Vấn đề pháp lý:
Quy định áp dụng:
Phân tích:
Kết luận:
Nguồn:
Hạn chế:
```

## Minimum Fallback Behavior

Use fallback when:

```text
retrieval returns no useful context
top evidence is below confidence threshold (0.75)
citation validation fails
question is outside the current corpus
```

## OOP and Docstring Rules

Expected components:

```text
NaiveRetriever           # simple dense/sparse search
ContextPacker            # parent + child text assembly
LegalPromptBuilder       # prompt rendering with citation rules
BaseLLMClient            # provider abstraction
CitationValidator        # citation integrity checks
FallbackPolicy           # confidence-based fallback
QAService                # end-to-end QA orchestration
```

Rules:

- Keep retrieval, generation, citation validation, and API route logic separate.
- Use typed models for candidates, evidence packets, citations, and responses.
- Public classes/functions must have Google-style docstrings.
- Docstrings must explain legal/RAG assumptions and fallback behavior.

## Definition of Done

- [ ] `/api/v1/qa` can answer from ingested corpus.
- [ ] Strict citation format is present in every answer.
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
