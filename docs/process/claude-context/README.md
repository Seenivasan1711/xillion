# Claude Code context, for a new machine

Claude Code keeps two things **outside** this repo, on the laptop itself. A
new machine starts without them unless they're restored from here.
Snapshot taken 2026-10-01, when moving off the work laptop.

| File here | Where it lives on a machine | What it is |
|---|---|---|
| `global-CLAUDE.md` | `~/.claude/CLAUDE.md` | Rakesh's global rules for every repo: the worktree-per-branch convention, and **never** adding attribution trailers to commits or PRs |
| `memory/*.md` | Claude Code's per-project memory dir (on the old laptop: `~/.claude-work/projects/-Users-seenivasan-Documents-personal-Projects-xillion/memory/`) | What Claude learned across sessions: who Rakesh is, his direction (XAUUSD first), feedback rules, current status, pending asks |

## Restore

```bash
mkdir -p ~/.claude && cp docs/process/claude-context/global-CLAUDE.md ~/.claude/CLAUDE.md
```

**Memory:** the folder name depends on where the repo is cloned and on
the Claude Code config dir. The easy way is to start Claude Code in the
repo and say:

> Restore your project memory from docs/process/claude-context/memory/

It knows its own memory path and copies the files there. If memory is
missing it doesn't break anything: `CLAUDE.md` → `docs/status/task-tracker.md`
(the ▶️▶️ COLD START block) is the real source of truth, and these notes are
just a faster warm-up.

The repo's own Claude setup is **in git** and needs no restore:
`.claude/skills/` (xillion-status, xillion-checkpoint, ...),
`.claude/hooks/` (bash-guard, session-start, tracker-guard), and
`.claude/settings.json`.

## Keeping this snapshot current

This is a point-in-time copy. Refresh it before any future machine change:

```bash
cp <memory dir>/*.md docs/process/claude-context/memory/
cp ~/.claude/CLAUDE.md docs/process/claude-context/global-CLAUDE.md
```
