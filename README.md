# VnLaw-QA Claude-Native Skill Pack

This package converts the previous Antigravity-style project context into a Claude Code native layout.

It intentionally does **not** include `.agents/`. The project context, rules, workflow, technical patterns, OOP constraints, docstring rules, and RAG roadmap are now encoded directly in:

```text
CLAUDE.md
.claude/skills/<skill-name>/SKILL.md
```

## Install

Copy this package into the root of your `vnlaw_qa` repository:

```bash
cp -r CLAUDE.md .claude README.md MANIFEST.json /path/to/vnlaw_qa/
cd /path/to/vnlaw_qa
claude
```

Then run:

```text
/skills
/vnlaw-project-charter
/vnlaw-workflow-review
```

## Design

The roadmap is:

```text
Naive RAG → Advanced RAG → GraphRAG
```

The implementation standards are:

- legal accuracy first,
- strict citations,
- no hallucinated law,
- Thư Viện Pháp Luật as the trusted source,
- parent-child legal chunking,
- dense + sparse hybrid retrieval,
- reranking,
- time-aware filtering,
- Neo4j cross-reference GraphRAG,
- RAGAS evaluation,
- strong OOP boundaries,
- Google-style docstrings,
- type hints, async I/O, Pydantic V2, structlog, ruff, mypy, pytest.
