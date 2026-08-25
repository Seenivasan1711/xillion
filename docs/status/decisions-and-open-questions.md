# 10 — Decisions & Open Questions

A living log of trade-offs the design has committed to, and questions that still need your call.

## Part A: Decisions made (with rationale)

### D1. Python is the strategy authoring language
- **Decision:** strategies are written in Python, dropped as `.py` files.
- **Why:** matches the broker SDKs (Kite Connect, Upstox, etc.); huge ecosystem of indicators, ML libs; you write Python.
- **Trade-off:** non-developers can't write strategies. (Future no-code layer would translate to Python under the hood.)

### D2. Plugin discovery via filesystem scan, not a registry
- **Decision:** drop a file in `strategies/` or `brokers/`; loader auto-discovers it.
- **Why:** simplest possible UX for "add a new thing." No CLI command to register.
- **Trade-off:** plugins must follow naming/structure rules; hot-reload is non-trivial; no separate plugin marketplace yet.

### D3. Same code in backtest, paper, and live
- **Decision:** `Strategy` interface is mode-agnostic; framework injects the right broker.
- **Why:** the #1 source of bugs in trading systems is "it worked in backtest."
- **Trade-off:** strategies can't access mode-specific features without special opt-ins (and we should resist adding those).

### D4. SQLite default, Postgres path documented
- **Decision:** ship with SQLite; tables and SQLAlchemy types are Postgres-compatible.
- **Why:** zero-config dev; SQLite handles a single user comfortably.
- **Trade-off:** SQLite has no concurrent writers; if you want background jobs that write heavily while the app is running, you'll feel pressure to migrate. Plan accordingly.

### D5. Single user in v1
- **Decision:** one user, password + TOTP, no roles.
- **Why:** product is "for me." Multi-user is a different product (regulatory + UX).
- **Trade-off:** every multi-tenant feature is deferred. Schema hints at the future but we don't build for it.

### D6. FastAPI + React, no SSR
- **Decision:** API service + SPA, communicating over REST + WebSocket.
- **Why:** simple to reason about; mobile-friendly; familiar stack.
- **Trade-off:** initial page load is slower than SSR. Acceptable for an internal tool.

### D7. Modular monolith, not microservices
- **Decision:** one process, organised as packages.
- **Why:** complexity is the enemy at this scale; observability and deployment are simpler.
- **Trade-off:** if someone later needs to scale one component (e.g., backtests) horizontally, refactoring needed.

### D8. Asyncio over threading
- **Decision:** asyncio is the concurrency model. Threads only for blocking IO that can't be made async.
- **Why:** matches broker WebSocket SDKs; one event loop is easier to reason about.
- **Trade-off:** any third-party library that's blocking needs an `asyncio.to_thread` wrapper.

### D9. Risk Manager is a hard gate, not advisory
- **Decision:** every order must pass Risk Manager; strategies cannot bypass.
- **Why:** the cost of a bypass route is zero benefit + huge tail risk.
- **Trade-off:** marginally less flexibility for "I know what I'm doing" cases. Worth it.

### D10. Audit log with hash chain
- **Decision:** append-only, hash-linked.
- **Why:** SEBI requires audit; hash chain detects tampering cheaply.
- **Trade-off:** small write overhead. Worth it.

### D11. Static IP enforcement is a runtime check, not a build-time enforcement
- **Decision:** at startup, check outbound IP matches `APP_BIND_IP`. Warn if not.
- **Why:** the broker enforces it anyway; we can pre-warn the user.
- **Trade-off:** false positives if the user is testing from a different network. Override available.

### D12. No HFT goals
- **Decision:** target sub-second latency, not microsecond.
- **Why:** SEBI's 10 OPS retail threshold puts us firmly in low-frequency territory; HFT requires a different stack.
- **Trade-off:** strategies dependent on millisecond reactions are out of scope.

### D13. Telegram is the primary alert channel
- **Decision:** Telegram bot first, email second, mobile push later.
- **Why:** lowest friction for a personal user; instant notification; bot can also accept commands later (e.g., `/kill`).
- **Trade-off:** depends on Telegram being up, but for personal use that's acceptable.

### D14. Backtest determinism is required
- **Decision:** same code + data + seed = identical results.
- **Why:** if you can't reproduce a backtest, you can't trust it.
- **Trade-off:** strategy authors can't use unseeded `random.random()` carelessly. Acceptable.

### D15. Strategies are not sandboxed in v1
- **Decision:** strategies run in the main process; can import any library, read any file.
- **Why:** single-user system, you wrote the strategies. Sandboxing is huge complexity for no v1 benefit.
- **Trade-off:** for commercial multi-tenant, this becomes a problem. Address then.

### D16. Compliance configured, not hardcoded
- **Decision:** OPS limit, daily loss cap defaults, IP, audit retention are env/DB config.
- **Why:** SEBI rules will evolve; you should be able to tighten without a release.
- **Trade-off:** must remember to keep them current.

### D17. Retrofit the automation-platform spec into xillion, don't build it separately
- **Decision:** the 52-job automation harness spec (`docs/architecture/automation-platform-spec/`) is xillion's **target architecture**, not a separate system. Map its job catalog onto what CP1-CP10 already built (risk engine, kill switch, journal, Telegram alerting + self-healing, daily digest, position reconciliation, Zerodha broker); build only the genuine gaps.
- **Why:** the spec is written as Phase-0-from-empty-repo, but xillion already has a working, tested implementation of most of what Phase 1's "18 P0 jobs" describe. Starting over would throw away CP1-CP10's real engineering and testing.
- **Trade-off:** the spec's own phase numbering and file organisation don't map 1:1 onto xillion's CP numbering — the mapping itself is judgment, done in `task-tracker.md`, and won't be perfect on the first pass.

### D18. Infra stack: adopt the spec's pieces, but free/minimal-cost until a VPS exists
- **Decision:** bring in Redis, DuckDB+Parquet, and a metrics/dashboard layer as the spec recommends, but every piece must be free or genuinely minimal-cost at today's scale (no VPS, no paid tier) — swap to paid/self-hosted-on-a-VPS only when a VPS actually gets provisioned. OpenAlgo adoption is deferred (see open question Q11).
- **Why:** explicit instruction — no ongoing infra cost until the user chooses to pay for one, even though the target architecture assumes a VPS eventually.
- **Trade-off:** the free tiers of hosted Redis (e.g. Upstash) and Grafana Cloud have real limits (connection count, retention, series count) that a VPS deployment wouldn't have — some pieces will need re-provisioning once a VPS exists, not just a config change. Documented per-component in the architecture doc's cost table.
- **Grafana specifically:** Grafana OSS self-hosted is fully free (AGPL, zero licence cost) but needs a place to run — with no VPS yet, the interim choice is a lightweight metrics view inside xillion's own React frontend (already free, zero new infra) rather than standing up Grafana locally. Revisit once a VPS exists.

### D19. Build Dhan out to a full trading broker, in parallel with Zerodha, immediately
- **Decision:** Dhan gets built to full parity with Zerodha (auth, live ticks, order placement) now, not sequenced after Zerodha. Both are wired as `BrokerAdapter`-equivalent plugins from the start; Zerodha isn't demoted, Dhan isn't blocked on Zerodha being "done."
- **Why:** the automation spec's broker comparison (`02-SYSTEM-ARCHITECTURE.md` §2.5) makes a real cost/rate-limit case for Dhan (free API vs Zerodha's ₹2,000/mo, more generous rate limits, native MCX support for the gold Lane B2) — and the user wants both built together rather than sequentially.
- **Trade-off:** more surface area to get right at once (two live broker integrations, two sets of auth/reconnect edge cases) instead of hardening one before starting the second.

### D20. Today's scope: docs and plan first, then continue straight into building in the same session
- **Decision:** store both spec packages in the repo, update PRD/architecture/task-tracker/decisions docs first — then, in the same session, move into actual code (foundational scaffolding first, MCP server layer whenever the user says go).
- **Why:** explicit instruction — plan needed to be right before code started, but the session continues past planning into building rather than stopping and waiting for a new session.
- **Trade-off:** none really — sequencing, not a scope cut.

## Part B: Open questions (decide before relevant phase)

### Q1. Auto-login automation: legal status?
- **Question:** Zerodha's developer terms have at times discouraged programmatic login (TOTP automation). Is this currently allowed?
- **Decide before:** Phase 3
- **How to decide:** Re-read Kite Connect terms; ask Zerodha support; consider falling back to a daily semi-automated flow if needed.
- **Default:** Implement automation, document a manual-fallback path.

### Q2. Where will this run?
- **Question:** VPS provider? Region (Mumbai for low latency to NSE)? Cost target?
- **Decide before:** Phase 7
- **How to decide:** comparison of Hetzner / DigitalOcean / E2E Networks (Indian) / AWS Mumbai. Static IP availability is the gating feature.
- **Default:** Hetzner CX22 in a nearby region for dev, switch to a Mumbai-based provider before going live for latency.

### Q3. Postgres now or later?
- **Question:** Should v1 ship on SQLite and migrate later, or start on Postgres?
- **Decide before:** Phase 0 finishes (or commit to SQLite-only for v1)
- **How to decide:** estimate concurrent write load; if you'll run heavy backtests while live trading, Postgres pays off sooner.
- **Default:** Start on SQLite; revisit at end of Phase 5.

### Q4. Time-series storage for bars
- **Question:** Plain Postgres table vs TimescaleDB hypertable vs DuckDB column store?
- **Decide before:** Phase 2 (only matters once history grows)
- **How to decide:** measure query times on 5 years of 1-min NIFTY bars in plain Postgres; if > 500ms, upgrade.
- **Default:** plain table; add Timescale extension if/when needed.

### Q5. Strategy hot-reload
- **Question:** Do we support live hot-reload of running strategy code, or require restart?
- **Decide before:** Phase 4
- **How to decide:** restart is simpler but interrupts trading. Live reload is harder but slicker.
- **Default:** Restart only in v1. Document the workflow ("pause → reload code → resume"). Live reload in v1.5.

### Q6. How do we handle the "first-tick after market open" edge case?
- **Question:** Bar aggregator behaviour at exactly 09:15 IST: include the first tick in the 09:15 bar?
- **Decide before:** Phase 2
- **How to decide:** Standard convention is bars are labelled by their open time, inclusive on the left. Match that.
- **Default:** Inclusive-left, exclusive-right.

### Q7. What's the second broker plugin?
- **Question:** After Zerodha, which broker validates the abstraction?
- **Decide before:** Phase 8
- **Options:** Upstox (popular API), Fyers (good docs), AngelOne (largest user base), Dhan (newer, modern API).
- **Default:** Upstox for variety in API style; Fyers as second choice.

### Q8. Commercial pivot path: vendor model or self-hosted?
- **Question:** If you commercialise, do users self-host or do you operate it?
- **Decide before:** any actual commercialisation
- **How to decide:** SEBI vendor empanelment is heavyweight; self-hosted side-steps some of this but limits scale.
- **Default:** undecided; revisit when v1 has been stable for 6 months.

### Q9. Mobile native app or stay PWA?
- **Question:** Is responsive web enough, or do you need React Native / native apps?
- **Decide before:** Phase 6 retrospective
- **How to decide:** dogfood the responsive UI for a month after v1; if it falls short, build mobile.
- **Default:** PWA (with `manifest.json`, offline shell). Native deferred indefinitely.

### Q10. Backtest engine: build vs buy?
- **Question:** Use Backtrader / Backtesting.py, or build a custom engine?
- **Decide before:** Phase 2
- **How to decide:** Backtrader is feature-rich but coupling it to your strategy interface is awkward. Backtesting.py is leaner. A custom engine is more code but matches your event-driven runtime exactly.
- **Default:** Custom engine, deliberately small. The runtime already iterates events; backtesting is just "iterate canned events." Reuse the live runtime as much as possible — that's also the cleanest way to keep backtest and live in sync.

### Q11. OpenAlgo — adopt as a library, or keep xillion's own broker abstraction?
- **Question:** the automation spec recommends adopting OpenAlgo (self-hosted, AGPL, 34 broker plugins, unified order API) as the execution layer *behind* a thin `BrokerAdapter` wrapper — not replacing xillion's `Broker` ABC, but sitting underneath it for Dhan/Zerodha/Groww specifically. Worth the new dependency and AGPL surface, or keep extending xillion's own already-working Zerodha plugin and build a native Dhan plugin the same way?
- **Decide before:** the Dhan broker build starts (D19)
- **How to decide:** OpenAlgo's main pitch is "don't hand-write 3 broker SDKs." xillion already hand-wrote Zerodha successfully (reconnect hardening, live ticks, order placement, all proven across CP1-CP10) — the question is whether that pattern is cheap enough to repeat for Dhan that OpenAlgo's abstraction isn't worth the new moving part.
- **Default:** lean toward a native Dhan plugin matching xillion's existing `brokers/*.py` pattern (consistent with everything else in the codebase), skip OpenAlgo, revisit only if a third broker makes the hand-written pattern feel expensive.

### Q12. Redis: which free-tier provider, and when does it become load-bearing?
- **Question:** the spec uses Redis for the OPS token bucket, live position state, distributed locks, and the kill-switch flag. Which free-tier hosted Redis (Upstash, Redis Cloud's free 30MB tier, etc.), and does xillion need it from day one of this work or only once multi-leg/high-frequency-relative-to-today's-usage checks actually require sub-second shared state?
- **Decide before:** the OPS token bucket / idempotency-key work starts
- **How to decide:** xillion's current single-process asyncio model can hold this state in-memory (like `RiskManager`'s in-memory OPS window today) without Redis at all, as long as it stays single-process. Redis only becomes necessary the moment there's more than one process/worker needing to share that state.
- **Default:** keep state in-memory (extend the existing `RiskManager` pattern) until there's a concrete reason to split into multiple processes; introduce Redis then, not preemptively.

### Q13. When does Lane B (gold) work actually start?
- **Question:** the automation spec's own roadmap sequences Lane B at Phase 3, after Lane A's risk engine and first automated strategy are solid (matches xillion's existing `docs/process/asset-pipeline.md` per-asset notes, which already put Options first). Confirm this default still holds, or does gold move up given Funding Pips is now flagged "primary per your instruction" in the regulatory doc?
- **Decide before:** any Lane B code starts
- **Default:** Options (Lane A) first, per both documents' own sequencing and the existing "Blocked on you" list (CA opinion + Funding Pips account are still outstanding). Revisit only if the user explicitly says otherwise.

## Part C: Things that are explicitly NOT decisions

These are intentional non-decisions for v1. Don't be tempted.

- No machine learning framework choice — strategies that want it can `import torch` themselves.
- No plugin marketplace — single user, your own plugins only.
- No real-time collaborative editing — single user.
- No multi-account support — one Zerodha account at a time per broker connection.
- No automated parameter sweeps in v1 — Phase 8.

## Part D: Decision log template

When you make a new decision later, add it as `D17`, `D18`, ... with the same structure:

```markdown
### D17. <One-line title>
- **Decision:** <what you decided>
- **Why:** <one or two sentences>
- **Trade-off:** <what you're giving up>
```

Same for new open questions: `Q11`, `Q12`, ...
