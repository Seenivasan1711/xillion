#!/usr/bin/env bash
# SessionStart hook — orient a cold session automatically.
# Prints current position from the tracker so no one has to ask "where are we".
set -uo pipefail

TRACKER="${CLAUDE_PROJECT_DIR:-.}/docs/status/task-tracker.md"

printf '═══ XILLION ═══\n'

if [ -f "$TRACKER" ]; then
  grep -E '^\*\*(Last updated|Current position|Active branch)' "$TRACKER" 2>/dev/null || true
else
  printf 'WARNING: docs/status/task-tracker.md not found\n'
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
