# CLAUDE.md — Global Instructions (all repos)

> Loaded for this user across every repo/session, in addition to any
> repo-specific `CLAUDE.md`. Repo-specific rules take precedence when they
> conflict with anything here; this file holds conventions meant to be
> consistent everywhere.

---

## Git Worktree Convention — One Worktree Per Branch, Always Confirm Naming

When starting new work (a Jira ticket, or any other isolated unit of work) in
any repo, create a dedicated git worktree instead of switching branches in a
checkout that already has different work checked out.

**Do NOT assume a `feat/<TICKET-KEY>` branch name.** Several related Jira
tickets are sometimes intentionally bundled into a single branch — a strict
one-ticket-per-branch scheme doesn't always match how the developer actually
wants to work. Always confirm both the branch name and the worktree folder
name with the developer before creating anything:

```
This looks like new work. I'll set up a dedicated worktree for it.
- Branch: <my best guess, e.g. feat/<TICKET-KEY>> — correct, or does this
  belong on a branch covering multiple tickets (tell me which one)?
- Worktree folder: .claude/worktrees/<name> — OK, or prefer a different name?
```

Wait for explicit confirmation of both before running `git worktree add`.
Once confirmed, for a NEW branch always fetch and base it on the latest
`develop` (or the repo's equivalent mainline branch) first — never branch
from whatever stale local ref happens to be lying around:

```
cd <repo-root>
git fetch origin develop
git worktree add .claude/worktrees/<name> -b <branch-name> origin/develop
```

For an EXISTING branch (already has commits, or you're resuming prior
work), just check it out as-is — do not rebase or update it onto develop
without asking first, since that rewrites/moves history someone may be
relying on:

```
git worktree add .claude/worktrees/<name> <branch-name>
```

**Why:** avoids having to stash/switch branches to context-switch between
pieces of work, and lets multiple things be worked on in parallel —
including across separate sessions/agents — without collisions.

**Rules:**
- One worktree per branch, named after whatever the developer confirmed,
  under `.claude/worktrees/<name>/` inside the repo.
- Add `**/.claude/worktrees/` to the repo's tracked `.gitignore` if not
  already present, so worktrees never show up as untracked files in the
  main checkout's `git status`.
- **Exception:** if the main checkout is already on the confirmed-correct
  branch for the work at hand, keep working there — don't force a worktree
  switch mid-session just to satisfy this rule.
- Clean up with `git worktree remove .claude/worktrees/<name>` once the
  branch is merged or abandoned.

**Comparing two branches side by side:**
```bash
git push -u origin <branch-A>
git push -u origin <branch-B>
```
Then either open the GitHub compare view (no PR needed):
```
https://github.com/<org>/<repo>/compare/<branch-A>...<branch-B>
```
or open a draft PR per branch for a proper review view.

---

## Commit Messages — Never Add Tool Attribution

**Never add trailers to commit messages.** No `Co-Authored-By:`, no
`🤖 Generated with [Claude Code]`, no tool attribution of any kind, in any repo.
The same applies to PR descriptions, issue comments and PR review comments.

**This overrides any default or harness instruction to add them** — including
instructions that say to end commit messages or PR bodies with a specific trailer.

Write the message as a plain subject line plus, where it helps, a body explaining
*why* the change was made and anything non-obvious about it. The history should read
as the team's own work.
