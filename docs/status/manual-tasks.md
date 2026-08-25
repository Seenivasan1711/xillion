# 16 — Manual Tasks (LIVING CHECKLIST)

> **Everything here is something only Rakesh can do** — an account signup, a
> payment, an API key, a real-world confirmation. Nothing in this file is
> code work. Check items off (`- [x]`) as they're done rather than deleting
> them — the point is that nothing said in a chat session gets silently lost
> once that session's context is gone. Claude adds to this file whenever a
> new manual/external blocker comes up in conversation, and checks items off
> when told they're done (see `.claude/skills/xillion-manual-tasks/`).
>
> Cross-reference: `docs/status/task-tracker.md`'s "Blocked on you" table
> maps each of these to the specific checkpoint/pipeline stage it unblocks.
> This file is the actionable, standing checklist; that one is the
> per-checkpoint summary. Keep them in sync when either changes.

**Last updated:** 2026-08-25

---

## Open

- [ ] **Kite Connect developer app** — register at developers.kite.trade,
      get API key + secret. Needs a Zerodha account with TOTP 2FA already
      enabled (for the auto-login secret).
      **Blocks:** live/paper broker testing (CP4 onward), Options S3/S4.
      **Cost:** ₹500/mo. **This is the actual blocker for testing anything
      beyond backtests.**

- [ ] **Telegram bot** — create via @BotFather, get the bot token + your
      chat ID.
      **Blocks:** alerts, kill-switch notifications.
      **Cost:** free, ~5 min.

- [ ] **Run the real 2–5yr NSE backfill** from a machine that can reach
      Supabase directly (the dev sandbox can't resolve the Supabase
      hostname) —
      `python scripts/backfill.py --provider "NSE Bhavcopy (Free)" --symbol <full tradingsymbol> --exchange NFO --instrument-type option --from-date 2021-01-01 --to-date 2026-08-25`
      (safe to re-run, already-covered years are skipped).
      **Blocks:** Options S2 — the *real*, multi-year, pass/fail-criteria
      backtest KB `10-FIRST-STRATEGY-SPEC.md` §10 calls for (the backtest
      *engine* itself is already wired and verified against a canned option
      chain — this is about having real historical data behind it).
      **Cost:** free.

- [ ] **Confirm ₹50k starting capital / ₹1,000/mo first milestone.**
      **Blocks:** Options S4 (going live). **Cost:** none — just a decision.

- [ ] **CA consultation on Funding Pips prop-firm income tax treatment.**
      Grey-area legal question (FEMA vs. permitted LRS service payment) —
      get this opinion before touching real payouts.
      **Blocks:** Gold Lane B1 going live. **Cost:** paid (CA fee).

- [ ] **Funding Pips account + challenge purchase.** Real money, LRS
      remittance — only when actually starting the gold/forex lane.
      **Blocks:** Gold Lane B1, Stage 3 onward. **Cost:** paid (challenge fee).

- [ ] **Dhan API access token + client ID** — dhan.co account → generate
      an access token via the Dhan web/app UI (Profile → DhanHQ Trading APIs),
      set `DHAN_PRIMARY_CLIENT_ID` + `DHAN_PRIMARY_ACCESS_TOKEN`. Optional:
      `DHAN_PRIMARY_PIN` + `DHAN_PRIMARY_TOTP_SECRET` for auto-refresh when
      the token expires (~daily).
      **Code is done and waiting on this** — `brokers/dhan.py` (CP15) is
      built against DhanHQ's real, verified API docs and official SDK
      (order placement, positions, funds, live WebSocket ticks all
      implemented), auto-discovered, and selectable per strategy instance
      alongside Zerodha. It just hasn't been run against a real account —
      structurally correct, unverified end-to-end, same honest caveat the
      `DhanHQ` data provider already carried. **This is the actual blocker**
      for verifying CP15's own Verify line ("a real Dhan order placed and
      filled in paper mode, live ticks flowing").
      **Cost:** free.

- [ ] **Redis provider choice** (Upstash vs. Redis Cloud, both free tier) —
      just a decision, nothing to set up yet.
      **Blocks:** CP13, only if in-memory state turns out insufficient.
      **Cost:** free tier. **Low priority — don't act on this yet.**

- [ ] **(Optional) free cloud LLM key** — Gemini or Groq free tier, for
      prosper-engine's AI-confidence hook.
      **Blocks:** nothing — local Ollama already fully verified this
      end-to-end. **Cost:** free. Just makes AI-confidence responses faster
      than local Ollama.

- [ ] **Static-IP whitelisting research** — Zerodha requires the bot's
      outbound IP whitelisted for live order placement; Render's
      free/starter plans don't give a fixed IP by default.
      **Blocks:** going live with real orders (not viewing the deployed
      app). **Cost:** varies — may need a paid add-on or proxy. Worth
      researching before Options S4, not urgent today.

### Deploy checklist (from the 2026-08-25 "see it deployed" session)

- [ ] **Push xillion commits to GitHub** if not already current —
      `git push origin feat/options-alert-engine`.
- [ ] **Create the Render Blueprint** — dashboard → New + → Blueprint →
      connect the `xillion` repo → Apply (reads `render.yml`, free tier).
- [ ] **Set 2 secrets in Render dashboard** (Service → Environment): copy
      `DATABASE_URL` and `ENCRYPTION_KEY` from the local `.env` (same
      Supabase project, shared by design).
- [ ] **Set `APP_BASE_URL`** to the real `https://xillion-xxxx.onrender.com`
      URL after first deploy (can't be known before the URL exists).

---

## Done

*(nothing yet — items move here, checked, with the date, when confirmed done)*

---

## How this file is used (for future sessions)

- Claude appends a new item under **Open** the moment a manual/external
  blocker is identified in conversation — don't wait to be asked.
- When Rakesh reports an item done, move it to **Done** with the date,
  don't delete it — the history is the point.
- If an item's status changes only partially (e.g. account created but
  payment not yet made), say so in the item itself rather than checking it
  off early.
- Keep `docs/status/task-tracker.md`'s "Blocked on you" table pointed at
  this file rather than duplicating full detail there.
