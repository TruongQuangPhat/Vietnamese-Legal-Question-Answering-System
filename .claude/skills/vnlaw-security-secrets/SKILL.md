---
name: vnlaw-security-secrets
description: Use when reviewing or implementing secrets handling, PII safety, logging safety, API security, vector/graph DB exposure, Docker security, or legal QA safety.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, MultiEdit, Write
---

# Security and Secrets Skill

Use this skill for security-sensitive code and reviews.

## Secrets

Never hardcode:

```text
API keys
database passwords
JWT secrets
connection strings
tokens
provider credentials
```

Use `.env` and `pydantic-settings`.

Keep `.env.example` with placeholders only.

## PII and Legal Question Safety

User legal questions may contain sensitive personal or business information.

Do not log raw legal questions in production unless explicitly approved and redacted.

Potential sensitive fields include:

```text
citizen ID
address
phone number
tax code
land parcel information
case details
company secrets
family disputes
medical or employment facts
```

## Logging

Use structured logs with safe metadata:

```text
request_id
user_id when available
timestamp
operation
status
latency
safe error category
```

Do not log:

```text
raw API keys
raw prompts
raw user PII
full legal dispute details
provider secrets
```

## API Security

- JWT Bearer authentication for protected endpoints.
- Rate limiting, default 60 requests/min/user.
- No `allow_origins=["*"]` in production.
- LLM timeout default max 30 seconds.
- Vector search timeout default max 5 seconds.
- Return `503` for timeout where appropriate.
- Return safe error messages to clients.

## Database Security

- Qdrant must require authentication in production.
- Neo4j Bolt port must not be public.
- Redis must require password and not be public.
- Sanitize every Cypher input.
- Never build Cypher queries by string concatenating raw user input.

## Agent Safety

When Claude works on this repository:

- Do not print secrets.
- Do not run `cat .env`.
- Do not run destructive shell commands.
- Do not delete raw data unless explicitly requested.
- Ask before running expensive crawls, training, or full corpus ingestion.

## Review Checklist

- [ ] No secrets in code.
- [ ] No secrets in tests.
- [ ] `.env` is ignored.
- [ ] `.env.example` has placeholders only.
- [ ] No raw PII logs.
- [ ] Inputs sanitized.
- [ ] Timeouts configured.
- [ ] Rate limiting present.
- [ ] Production CORS is restricted.
- [ ] Neo4j/Qdrant/Redis are not publicly exposed.

## Do Not

- Do not expose stack traces to users.
- Do not log full prompts with sensitive user content.
- Do not commit raw credentials.
- Do not use wildcard CORS in production.
- Do not run destructive shell commands without explicit instruction.