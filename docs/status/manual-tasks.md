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
demoted to low-priority/later; Telegram config also moved to Settings UI;
five items resolved by Rakesh's decisions — see Done)

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
      **Enter it in the app now, not `.env`:** Settings → Notifications →
      paste Bot token + Chat ID → Save. As of 2026-08-25 this is DB-backed
      (`/settings/notifications`, same encrypted-storage pattern as
      Dhan/Zerodha) and applies immediately to the running notifier, no
      restart needed.
      **Blocks:** alerts, kill-switch notifications.
      **Cost:** free, ~5 min.

- [ ] **Run the real 2–5yr NSE backfill — 🔵 IN PROGRESS, Claude is running
      it, nothing left for you here.** The original blocker (this dev
      sandbox couldn't resolve Supabase's direct-connection hostname)
      turned out to be your project being paused — you resumed it
      2026-08-25. Switched `.env` to the Session pooler connection
      (IPv4-reachable) once resumed. Scoped to **NIFTY + BANKNIFTY only**
      (your call, 2026-08-25) — the unfiltered whole-NFO-market version
      would have been ~85M rows / ~25-30GB, well past free-tier Supabase
      storage; added a real `--underlying-filter` option to
      `scripts/backfill.py` + `data_providers/nse_bhavcopy.py` to scope it
      down (~3.7M rows / ~850MB estimated for the full filtered range).
      Running in the background, chunked by year, resumable. Will move to
      Done for real once it completes.

- [ ] **Decide Zerodha/Dhan product type for multi-day option holds
      (MIS/INTRADAY vs. NRML/CNC/MTF) — not urgent, flagging for
      awareness.** Found while wiring CP11's real GTT/Forever-Order
      support, 2026-08-25: both `brokers/zerodha.py` and `brokers/dhan.py`
      currently hardcode every order to the intraday-margin product
      (`MIS`/`INTRADAY`) — already a known, documented limitation from
      earlier work, not new. The credit-spread weekly strategy holds
      positions across multiple days until expiry, which an intraday
      product would normally force-square-off same day at the broker —
      worth understanding before this goes live with real capital. This
      is also why Dhan's Forever Orders (their GTT equivalent) aren't
      wired yet: Dhan's API only accepts `CNC`/`MTF` for that order type,
      not `INTRADAY`. **Blocks:** nothing today (paper mode isn't affected
      the same way) — decide before Options S4 (going live).
      **Cost:** none — a decision, plus whatever margin difference
      NRML/MTF carries vs. MIS/INTRADAY once you do go live.

- [ ] **(Optional) free cloud LLM key** — Gemini or Groq free tier, for
      prosper-engine's AI-confidence hook.
      **Deferred — Rakesh's explicit call, 2026-08-25 ("keep for later").**
      **Blocks:** nothing — local Ollama already fully verified this
      end-to-end. **Cost:** free. Just makes AI-confidence responses faster
      than local Ollama.

- [ ] **Static-IP whitelisting research** — Zerodha requires the bot's
      outbound IP whitelisted for live order placement; Render's
      free/starter plans don't give a fixed IP by default.
      **Deferred — Rakesh's explicit call, 2026-08-25 ("keep for later").**
      **Blocks:** going live with real orders (not viewing the deployed
      app). **Cost:** varies — may need a paid add-on or proxy.

---

## Done

- [x] **Deploy checklist** (Render Blueprint, secrets, `APP_BASE_URL`) —
      **all completed, confirmed by Rakesh 2026-08-25.**
- [x] **Confirm ₹50k starting capital / ₹1,000/mo first milestone.**
      **Decided 2026-08-25: yes, confirmed.**
- [x] **CA consultation on Funding Pips prop-firm income tax treatment —
      decided not needed.** Rakesh's call, 2026-08-25: Funding Pips income
      will be declared as foreign income on ITR directly rather than
      getting a separate CA opinion first.
- [x] **Funding Pips account + challenge purchase.** Already had this
      before being asked (2026-08-25) — will use it when Gold Lane B1
      actually starts.
- [x] **Redis provider choice — decided: Upstash** (2026-08-25, free tier
      with the more generous usage limit, same reasoning as Supabase for
      Postgres). Not wired into anything yet — only needed if CP13's
      in-memory state turns out insufficient, which hasn't happened.

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
