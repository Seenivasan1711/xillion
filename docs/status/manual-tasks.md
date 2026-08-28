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

**Last updated:** 2026-08-29 (M01 funds reconciliation built, one watch-item
caveat added; Dhan product-type decision made and built — MARGIN, Forever
Orders wired; the Zerodha half of that question split out as its own
still-open item)

---

## Open

- [ ] **Decide how Gold (XAUUSD) backtesting should work — no historical
      data source exists yet.** The MT5/Funding Pips broker+bridge built
      2026-08-28 only covers live/paper trading (real-time ticks from your
      Wine terminal); there's no way to backtest the Gold strategy today.
      Three candidate approaches are written up in
      `docs/status/deferred-backlog.md` ("Gold Lane B1 specifics") — take a
      look when you're ready to think about this, no rush since it's just
      a design/build task, not blocked on anything external.
      **Blocks:** backtesting Gold before/alongside running it live.
      **Cost:** none to decide; possibly a small one depending which
      approach you pick.

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

- [ ] **Decide Zerodha's product type for multi-day option holds (MIS vs.
      NRML) — not urgent, flagging for awareness.** `brokers/zerodha.py`
      still hardcodes every order (and its GTT legs) to `MIS` (intraday
      margin) — an intraday product would normally force-square-off a
      multi-day credit-spread/condor position same day at the broker,
      before expiry. **Dhan's own version of this decision was made
      2026-08-29 (see Done below) — this item is now Zerodha-only, and
      the two aren't linked: Dhan's GTT (Forever Orders) genuinely needed
      a product-type change to work at all (its API rejects INTRADAY
      outright); Zerodha's GTT already works fine under MIS today — this
      is purely about whether multi-day holds themselves should survive
      Zerodha's own intraday square-off.** **Blocks:** nothing today
      (paper mode isn't affected the same way) — decide before the
      Zerodha live path (Options S4).
      **Cost:** none to decide; whatever margin difference NRML carries
      vs. MIS once you do go live.

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

- [x] **M01 funds reconciliation (broker P&L vs. computed P&L) — built
      2026-08-29, needs no decision from you, just a watch item.**
      `Broker.get_realised_pnl_today()` now implemented for both brokers;
      Dhan's version sums `realizedProfit` across every position the
      broker returns. Honest caveat, same spirit as the Forever-Order one
      below: Dhan's own docs don't say whether `realizedProfit` resets
      daily or is cumulative since a position was first opened — matters
      now that positions are carried under `MARGIN` across days rather
      than squared off same-day. Nothing to decide here; just worth a
      glance the first time M01's Reconciliation panel (Configuration →
      Risk) shows a funds mismatch on Dhan with a multi-day position open
      — if the number looks like a running total rather than "today's"
      figure, that's this caveat showing up for real.
- [x] **Dhan product type for multi-day option holds — decided 2026-08-29:
      MARGIN, attempt Forever Orders with it.** `brokers/dhan.py` switched
      from `INTRADAY` to `MARGIN` (Dhan's NRML-equivalent F&O carry
      product) for every order, and `place_protective_gtt`/`cancel_gtt`
      now place real Forever Orders. Honest caveat: Dhan's own Forever
      Order docs say productType only accepts `CNC`/`MTF`, not `MARGIN` —
      built exactly as documented, but whether Dhan's server actually
      accepts it for an F&O leg carried under MARGIN is unverified against
      a real account (none exists in this sandbox). If it turns out to be
      rejected in practice, the software stop (already the primary
      protection mechanism regardless) is unaffected — worth watching for
      the actual API response the first time this runs live/paper on Dhan
      with GTT enabled.
- [x] **Dhan API access token + client ID — connected live on Render,
      2026-08-26.** Entered via Settings → Brokers → Dhan card, stored
      encrypted in the DB. **Same day, a real production bug was found and
      fixed:** the `dhanhq` SDK's `MarketFeed.__init__` was corrupting the
      main event loop, crash-looping `dhan_tick_broadcaster` with "cannot
      reuse already awaited coroutine" until it exhausted its restart
      budget and gave up silently — this is why paper instances on Dhan
      showed "No live tick source" with the feed never coming back. Fixed
      in `brokers/dhan.py` + `xillion/main.py` + `xillion/observability/
      task_supervisor.py` (see `task-tracker.md` for the full writeup);
      also fixed a leaked-broadcaster-task bug and an unbounded feed-error
      log flood found while chasing it. Merged to `main` 2026-08-26.
- [x] **Telegram bot — connected live on Render, 2026-08-26.** Bot token +
      chat ID entered via Settings → Notifications, confirmed working via
      the "Send test message" button.
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
- [x] **Real 2-5yr NSE backfill — done 2026-08-26.** 2021-2026 NIFTY +
      BANKNIFTY history fully persisted (2,680,368 bars for 2021-2023 legacy
      format alone). `bar_coverage` shows one continuous span 2021-01-01 →
      2026-08-25.
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
