---
doc_id: 01-REGULATORY
title: Regulatory Constraints That Shape the Design
audience: engineering + owner
version: 1.0
date: 2026-08-24
criticality: READ BEFORE CODING
---

# 01 — REGULATORY CONSTRAINTS

These are not legal advice — they are **engineering constraints derived from published rules**. They dictate hard limits in the architecture. Verify current status with your broker and a CA before go-live.

---

## 1.1 SEBI ALGO TRADING FRAMEWORK — LANE A (Indian markets)

**Timeline:** phased from Oct 2025; **full applicability 1 April 2026** — i.e. **already in force**.

### The threshold that defines the whole design

```
< 10 orders per second (per exchange, per client account)  →  NO algo registration required
≥ 10 OPS                                                    →  Exchange registration, Algo ID, simulation testing
```

**Design decision: the system is hard-capped at 7 OPS with a token-bucket throttle** (`10-RISK-ENGINE.md` §5). We stay structurally below the threshold with headroom. This is not a limitation in practice — our strategies are minute-scale, not microsecond-scale. Even aggressive scalping needs single-digit orders per *minute*.

> Note: Zerodha's Kite Connect independently enforces 10 OPS per client account and returns HTTP 429 above it. Both rejected and successful orders count. Our 7 OPS cap keeps us clear of both limits.

### Hard requirements to build for

| Requirement | Engineering impact |
|---|---|
| **Static IP whitelisting** | Orders only from 1–2 registered static IPs. **VPS with a static IP is mandatory infrastructure, not optional.** Data/read endpoints are exempt on Kite. |
| **OAuth mandatory** | No password-based login. Implement OAuth flow + secure token storage. |
| **2FA every session** | Manual daily re-auth step. **Job `P01` must handle this and alert if it fails.** |
| **Sessions auto-close daily** | No persistent sessions. Token refresh is a daily job, not a one-off. |
| **Unique exchange algo ID per order** | Order tagging must be plumbed through every order object. |
| **Broker liable for API orders** | Broker may impose additional limits. Confirm with Dhan/Zerodha/Groww. |
| **Audit trail retained ≥5 years** | Our own audit log must match. `03-DATA-MODEL.md` §audit_log. |
| **Code hosted on Indian servers** (if registered) | Choose an India-region VPS from day one to avoid a migration later. |

### What is explicitly permitted
✅ Self-built strategies for **personal use and immediate family** (spouse, dependent children/parents)
✅ Automation below 10 OPS without registration
✅ Manual order placement (unaffected by the framework)

### What is prohibited
❌ Sharing/selling your strategy outside immediate family
❌ Unregistered black-box algos
❌ Guaranteed-return claims
❌ Direct exchange connectivity (must route through broker)
❌ Open APIs / non-OAuth login

**Consequence for the roadmap:** this is a single-user system. Do not build multi-tenancy. Do not build a strategy marketplace. Both are regulatory dead ends.

---

## 1.2 LANE B — THE GOLD QUESTION

You've specified **Funding Pips + MT5**. Here is the accurate picture, stated once, then we build.

### Two genuinely different legal questions

| | Retail offshore forex | **Prop firm evaluation** |
|---|---|---|
| What is remitted | Trading margin | **An evaluation/service fee** |
| Account type | Live money in an offshore account | **Typically simulated/demo** |
| FEMA characterisation | Unauthorised forex transaction | **Payment for services (a permissible current-account transaction)** |
| RBI Alert List | Some platforms listed | Prop firms not generally listed |

**Retail offshore forex is clearly prohibited** for Indian residents under FEMA — penalties up to 3× the amount involved, ₹5,000/day for continuing violations, asset freezing, prosecution. That is not the situation you're describing.

**Prop firm trading is materially different** and is generally regarded as permissible, because:
- Challenge fees are a **service payment**, permitted under LRS ($250k/yr limit; 20% TCS above ₹7L is a refundable credit)
- Accounts are **simulated** — no actual offshore forex position is opened in your name
- Payouts are **inward remittance for services rendered**, permissible under FEMA

### The one nuance worth knowing

Sources distinguish **futures prop firms** (CME/CBOT-based) from **forex/CFD prop firms**. Funding Pips sits on the **forex/CFD** side — XAUUSD there is a CFD, not a CME futures contract. That side attracts somewhat more regulatory attention, though the simulated-account structure is the main mitigating factor and no restriction on prop participation existed as of early 2026.

### Your obligations regardless
- Declare payouts as **business/professional income** in your ITR — non-disclosure of foreign income carries penalties up to 120% of tax due plus prosecution
- Use authorised banking channels only
- Keep records ≥6 years
- **Talk to a CA who handles foreign income** before your first payout

**Engineering decision: we build Lane B, and we build it twice-portable.**

| | Lane B1 — **Funding Pips / MT5** | Lane B2 — **MCX Gold** |
|---|---|---|
| Instrument | XAUUSD CFD | GOLD / GOLDM futures + options |
| Venue | Prop firm via MT5 | MCX (domestic, SEBI-regulated) |
| Session | 24/5 | 09:00–23:30 IST |
| Capital | Prop firm's (simulated) | Your own |
| Status | Primary per your instruction | **Fallback + hedge against rule change** |

**Why build both:** the analytics, session logic, volatility drivers, and trailing-stop engines are **~85% shared**. MCX's evening session covers the same London/NY windows that make gold tradeable. Building the gold lane with a pluggable execution adapter costs perhaps 15% extra effort and means a rule change, a prop firm shutting down, or a failed challenge does not strand the work. See `11-INSTRUMENT-LANES.md`.

---

## 1.3 FUNDING PIPS CONSTRAINTS — these are *system* constraints, not preferences

Prop firm rules are **hard limits enforced by the firm**. Breaching one ends the account instantly. The risk engine must treat them as inviolable.

| Rule | Value (verify against your account's live terms) | System implication |
|---|---|---|
| Profit target | ~8% | Target tracking job |
| **Daily drawdown** | **~5%** | 🚨 **Hard kill switch. Must trigger BEFORE the firm's.** |
| **Max drawdown** | **~10%** | 🚨 **Hard kill switch, trailing model** |
| Drawdown model | **Trailing** (resets on new peak balance) | Must track **peak equity**, not starting balance |
| Profit split | Up to 80%; Zero program 95% | Reporting only |
| Payout | Monthly, 5–10 business days | Reporting only |
| **EAs / algos** | **✅ Explicitly permitted** — scalping and HF strategies allowed | Green light for automation |
| News trading | Restrictions typical but not fully published | Build the event-veto job anyway (`P03`) |
| Weekend holding | Generally allowed | Configurable |

> ⚠️ **Sources note Funding Pips does not publish exact drawdown percentages on its marketing site.** Job `P07-B` must read the live account terms and current equity/peak from MT5 at startup and refuse to arm if it cannot confirm the limits.

**Design rule: our internal limits are set at 80% of the firm's.** If the firm's daily DD is 5%, we halt at 4%. The gap absorbs slippage, spread widening at rollover, and the fact that their equity calculation may differ from ours by a tick.

---

## 1.4 DERIVED HARD LIMITS — implement these as constants

```yaml
# These are not tunable. They are compliance boundaries.
compliance:
  max_orders_per_second: 7          # SEBI threshold 10, we cap below
  max_orders_per_second_burst: 9    # absolute ceiling, never exceed
  static_ip_required: true
  oauth_only: true
  session_max_lifetime_hours: 24    # forced daily re-auth
  audit_retention_years: 5
  multi_user: false                 # regulatory dead end
  strategy_sharing: false

lane_b_prop:
  internal_daily_dd_pct: 4.0        # firm ~5.0 — we stop first
  internal_max_dd_pct: 8.0          # firm ~10.0
  dd_model: trailing_peak_equity
  halt_on_breach: immediate_flatten
```

---

## 1.5 REGULATORY WATCH LIST

Rules changed **four times in under two years**. Build for change:

- Nov 2024 — weekly expiries cut to one per exchange; Bank Nifty weeklies removed
- Sep 2025 — Nifty expiry moved to Tuesday, Sensex to Thursday
- Jan 2026 — lot sizes revised (Nifty 75→65, Bank Nifty 35→30)
- Apr 2026 — STT on options raised 0.10%→0.15%; SEBI algo framework fully in force

**Engineering consequence:** expiry day, lot size, and cost rates are **configuration, never constants in code** (`12-CONFIG-SCHEMA.md`). Job `R06` audits config against live exchange data weekly and alerts on drift. A hard-coded lot size will silently mis-size every position the day it changes.
