---
doc_id: 00-README
title: Trading Automation Platform — Scope and Reading Guide
audience: engineering team
version: 1.0
date: 2026-08-24
owner: Rakesh
---

# 00 — README AND SCOPE

## What we are building

A **job-based trading operations platform** that automates the rituals a discretionary trader performs manually every day. The design principle: **a human trader's day is a sequence of discrete, schedulable checks.** Each becomes an independent job with defined inputs, logic, outputs and failure behaviour.

This is **not** "an algo that trades for you." It is an **operations harness**: it prepares, gates, sizes, monitors, protects and reports. Strategy logic plugs into it. The harness is the durable asset; strategies come and go.

## Two instrument lanes

| Lane | Instrument | Venue | Session | Status |
|---|---|---|---|---|
| **LANE-A** | Nifty / Sensex weekly index options | NSE / BSE | 09:15–15:30 IST | Primary |
| **LANE-B** | Gold | **MCX (GOLD / GOLDM futures + options)** | 09:00–23:30 IST | Secondary |

> 🚨 **On XAUUSD specifically — read `01-REGULATORY-CONSTRAINTS.md` before writing any code for this lane.** Spot XAUUSD via offshore forex/CFD brokers is **not legally available to Indian residents under FEMA**. This spec therefore implements the gold lane on **MCX**, which is a domestic, SEBI-regulated venue offering gold futures and options.
>
> The good news for the design: MCX's evening session (to 23:30 IST) covers the **London and New York windows** that make gold tradeable in the first place. Nearly all of the session logic, volatility drivers and scalping structure that applies to XAUUSD **maps directly onto MCX Gold**. The lane is built once and the analytics are shared.

## Design principles

1. **Every job is independently schedulable, independently testable, independently killable.** No job may assume another job's in-memory state — only its persisted output.
2. **Idempotency.** Re-running any job with the same inputs produces the same result and no duplicate side effects. Order placement is the sole exception and is guarded by an idempotency key.
3. **Fail closed.** If a job cannot verify a precondition, it blocks the trade. Ambiguity never resolves to "proceed."
4. **The risk engine is not a job — it is a gate every order passes through.** It cannot be bypassed by any strategy.
5. **Observability over cleverness.** Every decision writes a structured reason. "Why didn't it trade today?" must be answerable from logs alone.
6. **Human override always available.** A kill switch reachable from a phone, that works even if the main app is wedged.
7. **Paper mode is a first-class runtime**, not a debug flag. Identical code path, orders routed to a simulator.

## File map

| File | Contents | Primary reader |
|---|---|---|
| `00-README-AND-SCOPE.md` | This file | Everyone |
| `01-REGULATORY-CONSTRAINTS.md` | SEBI algo rules, FEMA, hard limits that shape the design | Everyone — **read before coding** |
| `02-SYSTEM-ARCHITECTURE.md` | Services, data flow, tech stack, deployment | Architect / backend |
| `03-DATA-MODEL.md` | Schemas, tables, event contracts | Backend / data |
| `04-JOB-CATALOG.md` | Master index of all 52 jobs with schedules | Everyone |
| `05-JOBS-PREMARKET.md` | P-series job specs | Backend |
| `06-JOBS-ENTRY.md` | O- and E-series job specs | Backend |
| `07-JOBS-INTRADE.md` | T-series — monitors, trailing SL, adjustments | Backend |
| `08-JOBS-POSTMARKET.md` | X- and M-series job specs | Backend / data |
| `09-JOBS-PERIODIC.md` | R-series — revalidation, decay detection | Data / quant |
| `10-RISK-ENGINE.md` | Pre-trade gates, kill switches, circuit breakers | Backend — **critical path** |
| `11-INSTRUMENT-LANES.md` | Lane-A vs Lane-B differences in full | Backend / quant |
| `12-CONFIG-SCHEMA.md` | Complete YAML config contract | Backend / ops |
| `13-IMPLEMENTATION-ROADMAP.md` | Phase 0–6 plan with deliverables and gates | PM / everyone |
| `14-TESTING-AND-ACCEPTANCE.md` | Test strategy, acceptance criteria per phase | QA / backend |
| `15-RUNBOOK-AND-OBSERVABILITY.md` | Alerts, dashboards, incident response | Ops |

## Job ID convention

```
<PHASE><NN>[-<LANE>]

PHASE:  P = Pre-market      O = Open
        E = Entry           T = In-trade
        X = Exit            M = Post-market
        R = Periodic        K = Cross-cutting

LANE:   A = options, B = gold, omitted = both

Example: T03-A = In-trade job 03, options lane
```

## Glossary

| Term | Meaning |
|---|---|
| **Lane** | An instrument family with its own session, venue and rules (A = options, B = gold) |
| **Job** | A scheduled or event-triggered unit of work with a spec in this document set |
| **Gate** | A blocking check. Fails closed. |
| **Arming** | Marking a strategy eligible to fire today. An unarmed strategy cannot generate orders. |
| **Kill switch** | Immediate halt: cancel all open orders, optionally flatten positions, block new orders |
| **Flatten** | Close all open positions at market |
| **Cycle stage** | S1–S5, position within the weekly options expiry cycle (see strategy KB `01` §1.2) |
| **Idempotency key** | Unique per logical order; prevents duplicate submission on retry |
| **Paper mode** | Full pipeline with a simulated broker |
| **OPS** | Orders per second — SEBI's algo registration threshold metric |

## Relationship to the strategy knowledge base

This spec is the **execution harness**. The **strategy knowledge base** (delivered separately: `options-scalping-rag.zip`) defines *what* to trade and *why*. Cross-references appear as `KB 07 §Expectancy Math`.

The split matters: strategies are hypotheses with a short shelf life, the harness is infrastructure. Do not embed strategy logic in harness code — strategies are plugins loaded from config (`12`).

## Explicit non-goals for v1

- ❌ High-frequency / sub-second execution (SEBI 10 OPS cap makes it moot — see `01`)
- ❌ Multi-user / SaaS (single-trader system; sharing strategies outside family is prohibited)
- ❌ ML-based signal generation (harness first; models later, if ever)
- ❌ Full order-book / market-microstructure modelling
- ❌ Auto-deployment of new strategies without human approval
