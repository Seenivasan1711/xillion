---
name: xillion-tooling
description: Turn a repeated manual task into permanent tooling — a skill, a hook, or a CLAUDE.md rule. Use PROACTIVELY the moment something is done a third time, re-explained after being forgotten, or corrected twice; also when the user says "make this a skill", "automate this", "add a hook", "we keep doing this", "you forgot again".
---

# Tooling reflex — never do the same thing manually three times

This project runs for months across many cold sessions. Anything held only in
one session's context is lost at the next compaction. **The only durable memory
is a file in the repo.** This skill converts recurring work into that file.

## When to fire (do not wait to be asked)

Trigger on any of these signals. The user has explicitly asked for this to be
proactive — noticing and proposing is part of the job, not an interruption.

| Signal | Example that actually happened here |
|---|---|
| **Third repetition** | Adding a data provider (NSE bhavcopy → Kite → DhanHQ) |
| **Same thing forgotten twice** | `alembic` run without `DATABASE_URL`, silently hitting SQLite |
| **Same correction twice** | Attribution trailers on commits |
| **A near-miss with real cost** | 32MB CSV nearly committed to history |
| **A check done every time** | "does the tracker match reality?" |
| **A process with an order that must not change** | pipeline stages, checkpoint close-out |
| **Something that will run N times ahead** | per-asset pipeline advance — 6 assets × 6 stages |

If a signal fires mid-task, **finish the current task first**, then raise it.
Don't derail work to build tooling.

## Step 1 — pick the right instrument

Choosing wrong is the main failure mode. Match the shape of the problem:

| Shape | Instrument | Why |
|---|---|---|
| A multi-step **procedure** with judgement in it | **Skill** (`.claude/skills/<name>/SKILL.md`) | Loads only when relevant; can hold nuance |
| A mistake that **fails silently** and must be *impossible* | **Hook** (`PreToolUse`, exit 2) | Blocks before damage; a rule can be forgotten, a hook cannot |
| A fact/preference that must apply to **every** session | **CLAUDE.md rule** | Always in context; costs tokens on every turn, so keep it short |
| Orientation info needed at **session start** | **SessionStart hook** | Free, printed once |
| A condition that must hold before a session **ends** | **Stop hook** | Last line of defence for protocol drift |
| A one-off | **Nothing** | Just do it |

**Bias against building.** A skill that fires twice a year is noise in every
future session's skill list. Two honest questions before creating anything:

1. *Will this actually recur?* Three past occurrences, or a known future count
   (like "6 assets × 6 stages"), is evidence. "Might be useful" is not.
2. *Would the next cold session get this wrong without it?* If a competent
   session would do the right thing anyway, skip it.

If either answer is no, say so out loud and move on — declining to build is a
valid outcome of this skill.

## Step 2 — propose in one line, then build

Say what you spotted, what you'd build, and why — then build it. Don't write a
proposal document and wait.

> "That's the third data provider. I'm turning the sequence into
> `/xillion-add-provider` so the next one doesn't re-derive the scrip-master
> caching and credential-field wiring."

Only stop and ask first if the instrument is a **hook that blocks commands** —
those change what the user can do, so confirm scope before wiring one in.

## Step 3 — write it

### Skills
- Path: `.claude/skills/<name>/SKILL.md`, frontmatter `name` + `description`
- `description` decides whether it ever fires. Include the **trigger phrases a
  user would actually type**, not a summary of the contents
- Prefix project skills `xillion-` so they group together
- Put the *why* next to each step, with the real incident that motivated it —
  a step with no reason gets skipped by a future session under time pressure
- State scope limits explicitly (what the skill must NOT do without asking)

### Hooks
- Path: `.claude/hooks/<name>.sh`, then **register in `.claude/settings.json`**
  (a hook not registered is dead code) and `chmod +x`
- **Exit 2 blocks** and feeds stderr back for self-correction; exit 0 allows
- Read the JSON payload from stdin
- Every blocking hook needs an **escape hatch** and a **loop guard**
  (`stop_hook_active` for Stop hooks) — a hook that can't be satisfied wedges
  the session
- Gate narrowly. A hook that fires on normal work gets disabled and then
  protects nothing
- **Test it before declaring it done**:
  ```bash
  echo '{"tool_input":{"command":"alembic upgrade head"}}' | bash .claude/hooks/bash-guard.sh; echo "exit=$?"
  ```
  Assert both the blocking case and the allowed case.

### CLAUDE.md rules
Short, imperative, dated. Only for things every session must know.

## Step 4 — register and record

Every new skill/hook must land in **all** of these, in the same turn:

1. `docs/process/automation-registry.md` — the durable inventory. Add a row,
   and delete the corresponding entry from the candidate watchlist.
2. `docs/status/task-tracker.md` — bump **Last updated**; note it in the
   current checkpoint if it affects the workflow.
3. `CLAUDE.md` — only if the tooling changes the session protocol.

Then tell the user the one-line invocation.

## Step 5 — when a signal fires but you're NOT building yet

If something looks repeatable but has only happened once or twice, **do not
build**. Add it to the candidate watchlist in
`docs/process/automation-registry.md` with a tally mark. When the count reaches
three, the next session builds it without re-deriving the case.

This is what makes the reflex survive compaction: the count lives in a file,
not in context.

## Maintenance — prune, don't just accumulate

When closing a checkpoint, if a skill exists for a phase that is now finished
(e.g. a backfill skill after the backfill is done), move it to the registry's
"retired" section and delete it. Stale tooling is worse than none: it gets
invoked and gives wrong instructions.
