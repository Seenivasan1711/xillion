---
name: xillion-manual-tasks
description: Track things only Rakesh can do — account signups, payments, API keys, real-world confirmations — in docs/status/manual-tasks.md so nothing said in one chat session gets lost by the next. Use PROACTIVELY whenever a manual/external blocker comes up in conversation (not code work), and whenever the user reports one done. Also use when the user asks "what do I need to do", "what's on my manual list", "what's blocked on me".
---

# Manual tasks — the one durable list of "only you can do this"

This project runs across many cold sessions. A manual blocker mentioned in
chat (an account to create, an API key to fetch, a payment to make) is
**gone** the moment that session's context is gone, unless it lands in
`docs/status/manual-tasks.md`. That file is the single durable record —
treat it the same way `docs/status/task-tracker.md` is treated for code
checkpoints: read it, keep it current, never let it silently drift from
reality.

## When to fire (do not wait to be asked)

- **A new manual/external blocker surfaces.** Anything that requires
  Rakesh's own action outside the code — a broker/API signup, a payment, a
  document/legal step, a real-world confirmation, a deploy-dashboard click
  only he can make. The moment you'd otherwise just say it in chat and move
  on, add it to the file instead. Don't wait for the user to ask.
- **The user reports something done.** "I set up the Kite app", "bot token's
  in the .env now", "pushed both" (deploy items), etc. — find the matching
  item and check it off.
- **The user asks what's outstanding** — "what do I need to do", "what's
  left for me", "what's blocked on me" — read the file and answer from it,
  don't reconstruct the list from memory or from scanning the conversation.

## How to add an item

1. Open `docs/status/manual-tasks.md`.
2. Add a new `- [ ]` bullet under **Open**, in the same shape as the
   existing entries: a bold one-line title, then **Blocks:**, **Cost:**,
   and any notes worth keeping (why it matters, what it unblocks, anything
   non-obvious). Keep it as terse as the existing entries — this is a
   checklist, not a document.
3. If it directly maps to a checkpoint or pipeline stage, also check
   whether `docs/status/task-tracker.md`'s "Blocked on you" table needs a
   matching row (don't duplicate detail there — one line pointing at this
   file is enough).
4. Update **Last updated** at the top of `manual-tasks.md`.

## How to check an item off

1. Find the matching bullet under **Open**.
2. Move it to the **Done** section (don't delete it), mark `- [x]`, and add
   the date it was completed. Preserve the original text — the history is
   the point, not just the current state.
3. If `task-tracker.md`'s "Blocked on you" table has a matching row, update
   it the same way that table already handles resolved items (strikethrough
   + "✅ Resolved YYYY-MM-DD").
4. If the item is only partially done (account created but payment not yet
   made, say), don't check it off — edit the bullet to reflect the real
   state instead.
5. Update **Last updated**.

## Rules

- **Never delete an item outright.** Move it to Done, checked, dated. A
  vanished line looks the same as one that was never tracked — the whole
  point of this file is that nothing silently disappears.
- **This file is for the user's own actions only.** Code work, even if
  currently blocked, belongs in `task-tracker.md`, not here. If something
  is ambiguous (e.g. "run the real backfill" — a command Rakesh runs, but
  it's still just a shell command), it belongs here because *he* has to be
  the one to execute it (this sandbox can't reach the target host) — the
  test is "can Claude do this in the current session", not "is it a
  command".
- **Keep it in sync with `task-tracker.md`.** If you update one and the
  other has a related row, update both in the same pass.
- Don't editorialize or re-prioritize the list on your own initiative —
  add/check off what actually happened in the conversation. If the user
  wants re-prioritization, that's a explicit ask, not something to infer.
