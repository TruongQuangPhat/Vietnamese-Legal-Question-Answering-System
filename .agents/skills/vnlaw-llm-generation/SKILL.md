---
name: vnlaw-llm-generation
description: Use for LLM client wrappers, legal QA generation prompts, provider abstraction, answer formatting, citation ID validation, fallback responses, answerability guards, and hallucination prevention.
---

# LLM Generation Skill

Use this skill when maintaining, reviewing, or extending legal answer generation.

Generation starts after retrieval/evidence selection has produced evidence packets. It must not perform retrieval itself.

## Current Status

Legal generation is implemented as part of the RAG workflow.

The current best evaluated workflow uses:

```text
coverage-aware hybrid retrieval
  → evidence selection
  → strict legal generation
  → citation ID guard
  → answerability fallback guard
  → strict generation evaluation
```

The evaluated provider/model configuration used OpenRouter with `google/gemini-2.5-flash`.

Do not call real LLM providers, OpenRouter, Gemini, or external APIs unless the user explicitly scopes that run.

## Goal

Generate legally grounded answers from selected evidence only.

```text
selected evidence packets
  → prompt rendering
  → LLM provider call
  → answer formatting
  → citation ID validation
  → answerability/fallback decision
  → response object or evaluation result
```

## Relevant Components

Use the repository’s current structure. Relevant components may include:

```text
LLM provider/client abstraction
legal prompt builder
answer formatter
citation guard / citation validator
fallback policy
strict generation evaluator
generation evaluation schemas
tests/unit/retrieval/
tests/unit/evaluation/
tests/integration/evaluation/
```

Do not create new generation modules unless the task explicitly scopes implementation work.

## Provider Abstraction

Wrap all LLM providers behind a typed interface.

```python
class BaseLLMClient(Protocol):
    """Interface for legal answer generation providers."""

    async def generate(self, prompt: str, *, request_id: str) -> LLMResponse:
        """Generate a response from a fully rendered prompt."""
        ...
```

Supported provider types may include:

```text
OpenAI-compatible API
OpenRouter
vLLM local or remote endpoint
other explicitly approved provider
```

Business logic must not depend directly on a concrete provider SDK.

## Prompt Requirements

Prompts must enforce:

* answer only from selected evidence;
* cite every legal claim using valid selected evidence IDs;
* never invent laws, articles, clauses, points, procedures, penalties, dates, or citations;
* distinguish quoted law text from explanation;
* preserve Article/Clause/Point hierarchy when available;
* fallback when evidence is insufficient, unsafe, indirect, parent-only, or missing citation metadata;
* avoid professional legal advice beyond the cited documents;
* never use model memory as legal evidence.

Do not claim time-aware legal validity behavior unless a time-aware workflow is explicitly implemented and evaluated.

## Evidence Requirements

Selected evidence should contain citation-ready child evidence:

```text
chunk_id or evidence_id
law_id
law_name when available
citation or legal reference
source_url
citable child text
legal hierarchy metadata when available
```

Parent context may be included as auxiliary context, but it must not be treated as directly citable evidence.

## Citation Validation

After generation, validate:

```text
every cited evidence ID exists in selected evidence
every legal claim has a citation
citations do not refer to parent-only context
source URL and legal metadata are present where required
no unsupported legal claim is present
```

If citation validation fails, do not return the unsupported answer. Return fallback or mark the case invalid according to the active workflow.

Citation ID validity is required, but it is not a substitute for qualified human legal review.

## Answerability Fallback Guard

Fallback is required when:

```text
selected evidence is empty
evidence is parent-context-only
citation metadata is missing
the model cites an unknown evidence ID
the answer contains unsupported legal claims
the question is outside the current corpus
strict evaluation mode has explicit empty expected targets
```

Fallback-required cases must not be answered during strict evaluation.

## Answer Format

Default answer structure:

```text
Legal issue:
Applicable legal basis:
Answer:
Sources:
Limitations / safety note:
```

Do not expose chain-of-thought. Provide concise, citation-backed legal analysis only.

## OOP and Docstring Rules

Expected components may include:

```text
BaseLLMClient
OpenAICompatibleLLMClient
OpenRouterLLMClient
LegalPromptBuilder
LegalAnswerFormatter
CitationValidator
CitationGuard
FallbackPolicy
StrictGenerationEvaluator
```

Rules:

* Keep provider calling separate from prompt rendering.
* Keep citation validation separate from answer formatting.
* Keep retrieval outside the LLM client.
* Use typed request/response models.
* Public classes/functions must have Google-style docstrings where project style requires it.
* Docstrings must explain provider assumptions, timeout behavior, fallback behavior, and legal safety assumptions.

## Testing Guidance

Use mocks/fakes for LLM providers in unit and integration tests.

Routine tests must not call:

```text
real OpenRouter/Gemini/API
real Qdrant
real embedding model
real reranker
full benchmark pipeline
```

When changing generation behavior, test:

* fallback on empty evidence;
* fallback on invalid citation ID;
* fallback on parent-only evidence;
* valid answer with selected citation IDs;
* no LLM call for strict fallback-required cases when expected targets are explicitly empty.

## Safety Rules

* Do not send raw secrets to the LLM.
* Do not include unnecessary user PII.
* Do not log full prompts in production if they contain user-sensitive facts.
* Do not let the LLM choose citations not present in selected evidence.
* Do not return uncited legal claims.
* Do not treat model output as trusted before citation validation.

## Do Not

* Do not perform retrieval inside the LLM client.
* Do not hardcode provider credentials.
* Do not expose chain-of-thought in the final answer.
* Do not treat model output as trusted before citation validation.
* Do not make parent context directly citable.
* Do not hide low confidence or missing evidence.
* Do not bypass the answerability fallback guard.
* Do not call real LLM/API workflows unless explicitly scoped by the user.
