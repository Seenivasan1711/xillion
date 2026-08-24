#!/usr/bin/env bash
# Stop hook — enforce the tracker-update protocol.
#
# The whole cold-start design depends on docs/status/task-tracker.md being
# current. A session that writes code and leaves the tracker stale silently
# breaks the next session's ability to orient.
#
# Fires only when ALL of these hold, so it can't nag during normal work:
#   1. not already fired this turn (stop_hook_active) — prevents loops
#   2. uncommitted changes exist under code paths
#   3. the tracker is NOT among those changes
#   4. the tracker's "Last updated" is not today
#
# Updating the tracker satisfies every condition, so this is always escapable.
set -uo pipefail

input=$(cat)
DIR="${CLAUDE_PROJECT_DIR:-.}"
TRACKER_REL="docs/status/task-tracker.md"

# 1. Loop guard
active=$(printf '%s' "$input" | python3 -c \
  "import json,sys;print(json.load(sys.stdin).get('stop_hook_active',False))" 2>/dev/null || printf 'False')
[ "$active" = "True" ] && exit 0

command -v git >/dev/null 2>&1 || exit 0
changed=$(git -C "$DIR" status --porcelain 2>/dev/null) || exit 0
[ -z "$changed" ] && exit 0

# 2. Did any real code change?
code=$(printf '%s\n' "$changed" | grep -E '^\s*[MARC?]{1,2}\s+(xillion/|strategies/|brokers/|data_providers/|frontend/src/|tests/)' || true)
[ -z "$code" ] && exit 0

# 3. Is the tracker already part of this change set?
printf '%s\n' "$changed" | grep -q "$TRACKER_REL" && exit 0

# 4. Was the tracker touched today anyway?
today=$(date +%Y-%m-%d)
if [ -f "$DIR/$TRACKER_REL" ] && grep -q "^\*\*Last updated:\*\* $today" "$DIR/$TRACKER_REL"; then
  exit 0
fi

cat >&2 <<EOF
Tracker not updated. Code changed under xillion/ · strategies/ · brokers/ ·
data_providers/ · frontend/src/ · tests/, but $TRACKER_REL was not touched and
its "Last updated" is not today.

Before finishing, update $TRACKER_REL:
  - tick completed items, set ⬜ → ✅ / 🟡
  - refresh **Last updated** and **Current position**
  - note anything surprising you found (this is what the next cold session needs)

If a checkpoint is genuinely complete, use /xillion-checkpoint instead — it
updates the tracker and commits in one pass.

If this work is intentionally mid-checkpoint, just bump **Last updated** to
$today with a 🟡 note on what's in flight.
EOF
exit 2
