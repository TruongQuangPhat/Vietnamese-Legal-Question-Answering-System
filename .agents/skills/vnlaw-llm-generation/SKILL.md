---
name: vnlaw-llm-generation
description: Use for LLM client wrappers, legal QA generation prompts, provider abstraction, answer formatting, citation validation, fallback responses, and hallucination prevention.
---

# LLM Generation Skill

Use this skill when implementing or reviewing legal answer generation.

This skill starts after retrieval/context packing has produced evidence packets. It must not perform retrieval itself.

## Goal

Generate legally grounded answers from retrieved evidence only.

```text
evidence packets
  → prompt rendering
  → LLM provider call
  → answer formatting
  → citation validation
  → fallback decision
  → response object
```

## Expected Files

```text
src/generation/llm_client.py
src/generation/prompts.py
src/generation/answer_formatter.py
src/generation/citation_validator.py
src/generation/fallback_policy.py

configs/prompts/legal_qa.j2
configs/models.yml

tests/unit/generation/
```

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
vLLM local or remote endpoint
other explicitly approved provider
```

Business logic must not depend directly on a concrete provider SDK.

## Prompt Requirements

Prompts must enforce:

- answer only from provided evidence;
- cite every legal claim;
- never invent laws, articles, clauses, points, procedures, or penalties;
- distinguish quoted law text from analysis;
- mention legal validity when query date matters;
- fallback when evidence is insufficient;
- include a legal advice disclaimer or safety note where appropriate.

## Citation Validation

After generation, validate:

```text
cited law exists in evidence
cited Article/Clause/Point exists in evidence
law name matches metadata
source URL is present
no unsupported legal claim is present
```

If citation validation fails, do not return the unsupported answer. Regenerate with stricter instructions or return fallback.

## Answer Format

Default answer structure:

```text
Legal issue:
Applicable provisions:
Analysis:
Conclusion:
Sources:
Safety note:
```

Do not expose chain-of-thought. Provide concise, citation-backed legal analysis.

## OOP and Docstring Rules

Expected components:

```text
BaseLLMClient
OpenAICompatibleLLMClient
VLLMLLMClient
LegalPromptBuilder
LegalAnswerFormatter
CitationValidator
FallbackPolicy
```

Rules:

- Keep provider calling separate from prompt rendering.
- Keep citation validation separate from answer formatting.
- Use typed request/response models.
- Public classes/functions must have Google-style docstrings.
- Docstrings must explain provider assumptions, timeout behavior, fallback behavior, and legal safety assumptions.

## Safety Rules

- Do not send raw secrets to the LLM.
- Do not include unnecessary user PII.
- Do not log full prompts in production if they contain user-sensitive facts.
- Do not let the LLM choose citations not present in evidence.
- Do not return uncited legal claims.

## Do Not

- Do not perform retrieval inside the LLM client.
- Do not hardcode provider credentials.
- Do not expose chain-of-thought in the final answer.
- Do not treat model output as trusted before citation validation.
- Do not hide low confidence or missing evidence.