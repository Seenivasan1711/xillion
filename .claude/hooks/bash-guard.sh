#!/usr/bin/env bash
# PreToolUse(Bash) guard — blocks two mistakes that fail SILENTLY in this repo.
#
# Exit 2 = block the command and feed stderr back to Claude so it self-corrects.
# Both cases below were hit for real during development; neither errors on its
# own, which is exactly why they need a hard stop.
set -uo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | python3 -c \
  "import json,sys;print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || printf '')

[ -z "$cmd" ] && exit 0

# ── 1. alembic without DATABASE_URL ───────────────────────────────────────
# migrations/env.py reads DATABASE_URL from the raw shell env, NOT from .env.
# Without it, alembic silently targets a local SQLite file and reports success
# while the real Postgres is untouched. This actually happened: a `stamp head`
# went to a stray data/xillion.db and went unnoticed.
if printf '%s' "$cmd" | grep -qE '(^|[;&|[:space:]])alembic[[:space:]]'; then
  if ! printf '%s' "$cmd" | grep -q 'DATABASE_URL'; then
    cat >&2 <<'EOF'
BLOCKED: `alembic` without DATABASE_URL exported.

xillion/db/migrations/env.py reads DATABASE_URL from the shell environment,
not from .env. Without it alembic silently falls back to local SQLite, creates
a stray data/xillion.db, and reports success while Postgres is untouched.

Re-run as:
  export DATABASE_URL=$(grep '^DATABASE_URL=' .env | cut -d= -f2-) && alembic <cmd>
EOF
    exit 2
  fi
fi

# ── 2. git commit with a large or ignored-category file staged ────────────
# A 32MB instrument-master CSV nearly landed in history. Committing large
# binaries is painful to undo once pushed.
if printf '%s' "$cmd" | grep -qE 'git[[:space:]]+commit'; then
  big=$(git -C "${CLAUDE_PROJECT_DIR:-.}" diff --cached --name-only 2>/dev/null | while read -r f; do
    [ -f "$f" ] || continue
    sz=$(wc -c <"$f" 2>/dev/null | tr -d ' ')
    [ "${sz:-0}" -gt 5000000 ] && printf '%s (%sMB)\n' "$f" "$((sz / 1000000))"
  done)
  if [ -n "$big" ]; then
    printf 'BLOCKED: staged file(s) over 5MB:\n%s\n\n' "$big" >&2
    printf 'Large data files belong in .gitignore and should be refetched on demand.\n' >&2
    printf 'Unstage with: git restore --staged <file>\n' >&2
    exit 2
  fi
fi

exit 0
