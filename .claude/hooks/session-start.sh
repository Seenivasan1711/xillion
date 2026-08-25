#!/usr/bin/env bash
# SessionStart hook — orient a cold session automatically.
# Prints current position from the tracker so no one has to ask "where are we".
set -uo pipefail

TRACKER="${CLAUDE_PROJECT_DIR:-.}/docs/status/task-tracker.md"
MANUAL_TASKS="${CLAUDE_PROJECT_DIR:-.}/docs/status/manual-tasks.md"

printf '═══ XILLION ═══\n'

if [ -f "$TRACKER" ]; then
  grep -E '^\*\*(Last updated|Current position|Active branch)' "$TRACKER" 2>/dev/null || true
else
  printf 'WARNING: docs/status/task-tracker.md not found\n'
fi

# Manual tasks (things only the user can do) -- open-item count only; the
# skill (.claude/skills/xillion-manual-tasks/) does the actual reading/
# editing when one comes up in conversation.
if [ -f "$MANUAL_TASKS" ]; then
  open_count=$(awk '/^## Open/{f=1;next}/^## Done/{f=0}f && /^- \[ \]/{c++}END{print c+0}' "$MANUAL_TASKS")
  if [ "${open_count:-0}" -gt 0 ]; then
    printf '**Manual tasks open:** %s (docs/status/manual-tasks.md)\n' "$open_count"
  fi
fi

# Uncommitted work is the most common source of tracker/reality drift.
if command -v git >/dev/null 2>&1; then
  count=$(git -C "${CLAUDE_PROJECT_DIR:-.}" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  if [ "${count:-0}" -gt 0 ]; then
    printf '**Uncommitted:** %s file(s) — tracker may be stale\n' "$count"
  fi
fi

printf 'Protocol: CLAUDE.md → START HERE · /xillion-status for detail\n'
printf 'Checkpoint done? → /xillion-checkpoint (updates tracker + commits)\n'
