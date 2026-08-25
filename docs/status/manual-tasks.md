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

**Last updated:** 2026-08-25 (Dhan promoted to top priority, Kite Connect
demoted to low-priority/later — Rakesh's explicit call, both now saved via
Settings UI into the DB instead of `.env`)

---

## Open

- [ ] **🔴 Dhan API access token + client ID — IMPORTANT, DO THIS NOW.**
      dhan.co account → generate an access token via the Dhan web/app UI
      (Profile → DhanHQ Trading APIs). Optional: PIN + TOTP secret for
      auto-refresh when the token expires (~daily).
      **Enter it in the app itself now, not `.env`:** Settings → Brokers →
      Dhan card → paste Client ID + Access Token → Save & Connect. As of
      2026-08-25 this is stored encrypted in the DB (`BrokerCredential`
      table via `xillion/auth/credstore.py`), the same pattern Zerodha
      already used — added this session specifically so multi-provider
      credentials don't have to live in `.env` and can be entered/rotated
      from the running app (see the question this answered, further down
      in `task-tracker.md`'s CP15 follow-up).
      As of the same session, paper mode no longer needs Zerodha at all —
      three real bugs were found and fixed that had hardcoded paper mode's
      live-tick feed to Zerodha and silently dropped `PaperBroker`'s price
      updates for *any* broker. With this token, you can see the app place
      real paper trades end-to-end for **free**, no Kite Connect
      subscription needed.
      **Blocks:** CP15 live verification, and now the fastest path to
      seeing the whole system run for real.
      **Cost:** free.

- [ ] **Kite Connect developer app — LOW PRIORITY, LATER.** Register at
      developers.kite.trade, get API key + secret. Needs a Zerodha account
      with TOTP 2FA already enabled (for the auto-login secret). Also
      DB-backed now — Settings → Brokers → Zerodha card, no `.env` editing.
      **Deferred by your own call, 2026-08-25** — not needed to see the app
      work, and costs money the free Dhan path doesn't. Pick this up only
      when you actually want the Zerodha-specific live-trading path (better
      liquidity data, real order routing there) — after Dhan is running,
      not before.
      **Blocks:** the Zerodha-specific live path, Options S4 going live.
      **Cost:** ₹500/mo.

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
