# Codex Instruction Index

Codex should look first at `AGENTS.md`, then at the repo-scoped skills under
`.agents/skills/`, then at the mirrored context files under `.codex/context/`.

## Instruction Surfaces

| Location | Role | Notes |
|---|---|---|
| `AGENTS.md` | Main Codex instruction entrypoint | Read first for mission, architecture, phase status, workflow, security, and command rules |
| `.agents/skills/<skill-name>/SKILL.md` | Active Codex repo skill folder | This is the only active Codex skill location for this repo |
| `.agents/skills/README.md` | Active skill inventory | Lists skill folder, skill name, trigger, phase, and Claude mirror status |
| `.agents/skills/SKILL_INDEX.md` | Active task-to-skill routing | Use when choosing which skill applies |
| `.codex/context/PROJECT_CONTEXT.md` | Codex context mirror of `PROJECT_CONTEXT.md` | Current phase, roadmap, architecture status, and out-of-scope work |
| `.codex/context/CLAUDE_MIRROR.md` | Codex-compatible mirror of `CLAUDE.md` | Original project-wide assistant rules preserved as reference |
| `.codex/context/skills_mirror/*/SKILL.mirror.md` | Inactive skill mirror/reference | Preserved content only; not an active skill source |
| `.claude/skills/<skill-name>/SKILL.md` | Claude-only original skills | Must be preserved for Claude compatibility |
| `.claude/` settings files | Claude configuration | Do not mirror local/private settings into Codex files |

## Active Skill Policy

- Active Codex repo skills live only in `.agents/skills/`.
- `.codex/context/` contains Codex-specific context and mirrors only.
- `.codex/context/skills_mirror/` is inactive reference only.
- `.codex/skills` should not be used as an active skill folder in this repo.
- `.claude/skills/` is Claude-only and must be preserved.
- Current phase status: Phase 6 Parent-child Chunking is complete and
  hardened; `data/processed/legal_chunks.jsonl` has 40,389 chunks, 0 failed
  laws, 0 source-tail markers in `text`/`parent_text`, and 180
  empty/repealed chunks flagged. Phase 7 Processed JSONL Validation /
  embedding-readiness checks is next.

## Source-to-Codex Mapping

| Original/reference file | Codex location | Purpose |
|---|---|---|
| `CLAUDE.md` | `.codex/context/CLAUDE_MIRROR.md` | Original project instructions mirrored for Codex context |
| `PROJECT_CONTEXT.md` | `.codex/context/PROJECT_CONTEXT.md` | Project context, roadmap, current phase, architecture status |
| `.claude/skills/<name>/SKILL.md` | `.agents/skills/<name>/SKILL.md` | Task-specific repo skill for active Codex discovery |
| Previous `.codex/skills/<name>/SKILL.md` | `.codex/context/skills_mirror/<name>/SKILL.mirror.md` | Inactive mirror/reference only |

## Preservation Warning

Do not delete, rename, move, overwrite, or modify `.claude/`, `.claude/skills/`,
Claude settings files, `CLAUDE.md`, or `PROJECT_CONTEXT.md` unless a task
explicitly asks for that change. The Codex files are compatibility mirrors, not
a destructive migration.

Do not copy `.env`, secrets, tokens, credentials, or local-only settings into
`.agents/` or `.codex/`.

## Settings Exclusion

Claude settings files are not mirrored into Codex instruction directories. In
particular, `.claude/settings.local.json` and the local `.claude/setting.json`
file are intentionally excluded because local settings may contain private
values, provider settings, tokens, or machine-specific preferences.
