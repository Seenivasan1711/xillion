---
doc_id: 02-ARCHITECTURE
title: System Architecture
audience: architect, backend
version: 1.0
date: 2026-08-24
---

# 02 — SYSTEM ARCHITECTURE

## 2.1 Guiding constraint: own the stack, pay no subscriptions

Every component below is **open source and self-hosted**. Recurring cost is a VPS, broker API fees, and market data — nothing else.

| Layer | Choice | Licence | Cost |
|---|---|---|---|
| Broker abstraction (Lane A) | **OpenAlgo** (self-hosted) or custom adapters | AGPL-3.0 | Free |
| Gold execution (Lane B1) | **MetaTrader5 Python package** | Free | Free |
| Gold execution (Lane B2) | Same broker adapter as Lane A (MCX) | — | Free |
| Job orchestration | **APScheduler** (v1) → **Prefect** (v2, self-hosted) | Apache-2.0 | Free |
| Transactional store | **PostgreSQL** | PostgreSQL Licence | Free |
| Time-series / tick store | **DuckDB + Parquet** (v1) → **QuestDB** (if volume demands) | MIT / Apache-2.0 | Free |
| Cache / state / pub-sub | **Redis** | RSAL/AGPL | Free |
| Backtesting | **Custom engine on DuckDB + Polars** (see §2.7) | — | Free |
| Metrics | **Prometheus** | Apache-2.0 | Free |
| Dashboards | **Grafana** | AGPL-3.0 | Free |
| Logs | **Loki** or plain structured JSON → Postgres | Apache-2.0 | Free |
| Alerts + kill switch UI | **Telegram Bot API** | Free | Free |
| Runtime | **Python 3.12+** | PSF | Free |

> ⚠️ **AGPL note on OpenAlgo and Grafana:** AGPL obligations trigger on *distribution* / network service to third parties. Personal single-user self-hosting is fine. If you ever expose this to anyone outside your family, get legal input — and recall `01` §1.1 prohibits strategy sharing anyway.

### Build vs. adopt: OpenAlgo

**Adopt it for Lane A.** It gives you, free and self-hosted:
- 34 Indian broker plugins (covers Dhan, Zerodha, Groww)
- Unified REST + WebSocket order API — write once, swap brokers without touching strategy code
- Options analytics: Greeks, volatility surface, Greeks exposure
- DuckDB historical data storage
- Sandbox/paper mode
- Telegram notifications

**Do not adopt it as your whole system.** It is an execution and data layer. The job harness, risk engine, trailing-stop logic and journal in this spec are yours. Treat OpenAlgo as a **library behind your own `BrokerAdapter` interface** (§2.4) so you can replace it later without rewriting strategies.

---

## 2.2 Service topology

```
┌──────────────────────────────────────────────────────────────────┐
│  SCHEDULER  (APScheduler → Prefect)                              │
│  Owns cron triggers, retries, job dependency graph               │
└───────────────┬──────────────────────────────────────────────────┘
                │ dispatches
                ▼
┌──────────────────────────────────────────────────────────────────┐
│  JOB RUNNER   —  every job in 05-09 executes here                │
│  Stateless workers. State lives in Postgres/Redis only.          │
└───┬──────────────────┬──────────────────┬────────────────────────┘
    │                  │                  │
    ▼                  ▼                  ▼
┌─────────┐      ┌──────────┐      ┌──────────────┐
│ MARKET  │      │ STRATEGY │      │ RISK ENGINE  │◄── every order
│  DATA   │─────▶│  PLUGINS │─────▶│  (mandatory  │    passes here.
│ SERVICE │      │          │      │   gate)      │    No bypass.
└────┬────┘      └──────────┘      └──────┬───────┘
     │                                    │ approved orders only
     │                                    ▼
     │                            ┌───────────────┐
     │                            │ ORDER MANAGER │
     │                            │  idempotency, │
     │                            │  retry, recon │
     │                            └───────┬───────┘
     │                                    │
     │                    ┌───────────────┴──────────────┐
     ▼                    ▼                              ▼
┌─────────────┐  ┌──────────────────┐        ┌────────────────────┐
│ WS FEEDS    │  │ BrokerAdapter A  │        │ BrokerAdapter B    │
│ (ticks, OI) │  │ OpenAlgo→Dhan/   │        │ MT5 (Funding Pips) │
│             │  │ Zerodha/Groww    │        │ or MCX via A       │
└─────────────┘  └──────────────────┘        └────────────────────┘

        ┌───────────────────────────────────────────┐
        │  PERSISTENCE                              │
        │  Postgres: orders, positions, journal,    │
        │            config, audit, metrics         │
        │  DuckDB/Parquet: ticks, candles, chains   │
        │  Redis: live state, locks, pub-sub, OPS   │
        │         token bucket                      │
        └───────────────────────────────────────────┘

        ┌───────────────────────────────────────────┐
        │  OBSERVABILITY                            │
        │  Prometheus ◄─ metrics    Grafana ◄─ dash │
        │  Telegram ◄─ alerts + KILL SWITCH         │
        └───────────────────────────────────────────┘
```

---

## 2.3 Deployment

### Lane A (India) — must be India-region with a static IP (`01` §1.1)

```
VPS: 4 vCPU / 8 GB / 100 GB SSD, India region, STATIC IP
     (Mumbai region on any provider — proximity to exchange colo helps latency)

Docker Compose services:
  ├── scheduler
  ├── job-runner        (2 replicas: one for jobs, one for the T-series monitor loop)
  ├── openalgo          (broker abstraction)
  ├── postgres
  ├── redis
  ├── prometheus
  ├── grafana
  └── telegram-bridge
```

### Lane B1 (MT5) — a separate box; MT5 needs a running terminal

```
VPS: Windows Server 2 vCPU / 4 GB, LOW LATENCY TO BROKER SERVER
     (typically London or NY — ask Funding Pips which datacentre their server is in;
      latency to their MT5 server matters far more than latency to you)

  ├── MetaTrader 5 terminal (must run continuously — the Python package talks to it via IPC)
  ├── mt5-bridge         (Python service exposing our BrokerAdapter over HTTP to the main box)
  └── local watchdog     (restarts MT5 if the terminal dies — it does)
```

> **Why two boxes:** MT5's Python integration requires the terminal process running locally. Linux is possible via Wine but is a reliability liability for money. Use Windows for the MT5 box, Linux for everything else, and connect them over an authenticated private link.

---

## 2.4 The BrokerAdapter interface — the most important abstraction

Every broker sits behind this. Strategy code never imports a broker SDK.

```python
from abc import ABC, abstractmethod
from decimal import Decimal

class BrokerAdapter(ABC):
    """One implementation per venue. Strategies depend on THIS, never on a vendor SDK."""

    # --- identity ---
    @abstractmethod
    def lane(self) -> str: ...                     # "A" | "B1" | "B2"
    @abstractmethod
    def health(self) -> HealthStatus: ...          # connected? authed? clock skew?

    # --- auth lifecycle (SEBI: daily re-auth, 01 §1.1) ---
    @abstractmethod
    def authenticate(self) -> AuthResult: ...
    @abstractmethod
    def session_expires_at(self) -> datetime: ...

    # --- market data ---
    @abstractmethod
    def quote(self, symbol: str) -> Quote: ...     # bid, ask, ltp, spread
    @abstractmethod
    def candles(self, symbol, tf, frm, to) -> pl.DataFrame: ...
    @abstractmethod
    def option_chain(self, underlying, expiry) -> OptionChain: ...   # Lane A/B2 only
    @abstractmethod
    def subscribe(self, symbols: list[str], cb) -> Subscription: ...

    # --- account ---
    @abstractmethod
    def balance(self) -> AccountBalance: ...       # incl. peak_equity for Lane B trailing DD
    @abstractmethod
    def margin_available(self) -> Decimal: ...
    @abstractmethod
    def margin_required(self, legs: list[Leg]) -> Decimal: ...

    # --- orders (ALL calls carry an idempotency_key) ---
    @abstractmethod
    def place(self, order: Order, idempotency_key: str) -> OrderAck: ...
    @abstractmethod
    def modify(self, order_id: str, changes: dict, idempotency_key: str) -> OrderAck: ...
    @abstractmethod
    def cancel(self, order_id: str) -> OrderAck: ...
    @abstractmethod
    def cancel_all(self) -> list[OrderAck]: ...    # kill switch path
    @abstractmethod
    def orders(self) -> list[OrderState]: ...
    @abstractmethod
    def positions(self) -> list[Position]: ...
    @abstractmethod
    def flatten_all(self) -> list[OrderAck]: ...   # kill switch path

    # --- capability flags: strategies branch on these, not on broker name ---
    @abstractmethod
    def capabilities(self) -> Capabilities: ...
```

```python
@dataclass(frozen=True)
class Capabilities:
    supports_bracket_order: bool
    supports_gtt: bool
    supports_oco: bool
    supports_trailing_sl_native: bool   # if False, we trail in software (T03)
    supports_multileg_atomic: bool      # almost always False in India — see 07 §T-note
    supports_options: bool
    supports_partial_fill: bool
    max_orders_per_second: int
    tick_size: Decimal
    lot_size: int
```

**Critical design note:** Indian brokers do **not** support atomic multi-leg execution. A 4-leg iron condor is 4 separate orders that can partially fill. `06-JOBS-ENTRY.md` §E05 specifies the leg-failure protocol — this is the single most dangerous part of the system and must be built before any multi-leg strategy goes live.

---

## 2.5 Broker comparison — the three you named

Verified Aug 2026. Re-verify before committing; these change.

| | **Dhan** | **Zerodha (Kite Connect)** | **Groww** |
|---|---|---|---|
| API cost | **Free** (data ~₹500/mo) | ₹2,000/mo + ~₹500 data | **₹499/mo** incl. |
| Order rate limit | **10/sec** | **10/sec** (429 above) | 10/sec, **250/min** |
| Data API limit | 5/sec | — | 10/sec, 300/min |
| Quote API limit | 1/sec | — | — |
| Non-trading limit | 20/sec | — | 20/sec, 500/min |
| WebSocket | ✅ | ✅ | ✅ **1000 subscriptions** |
| Segments | Eq, F&O, Currency, **MCX** | Eq, F&O, Currency, **MCX** | Eq, F&O, **MCX** |
| Order types | Full + super order | Full + GTT | Market, Limit, SL, SL-M, AMO, **GTT, OCO** |
| Historical data | ✅ | ✅ | ⚠️ **only 3 months** |
| Static IP required | Confirm | ✅ since Apr 2025 | Confirm |
| Token lifecycle | Daily | Daily | **Daily expiry** |
| SDK | Python (official) | Python (official) | Python + REST |
| Webhooks | ✅ | — | — |

### Recommendation

**Primary: Dhan.** Free API, the most generous documented rate limits, MCX included (which Lane B2 needs), webhook support, official Python SDK. The cost structure matters when you are testing — ₹2,000/mo to Zerodha before you've proven an edge is a real drag.

**Secondary: Zerodha.** The most mature and best-documented API in the market, and the one with the largest community when you hit an obscure problem. Worth the fee once the strategy is proven and running.

**Groww:** viable and cheap, but the **3-month historical data limit disqualifies it as your data source**. You cannot backtest a year of expiry cycles on 3 months of history. Usable for execution; not for research.

**Build both Dhan and Zerodha adapters in Phase 1.** OpenAlgo gives you both, so the marginal cost is near zero, and broker outages are real — the ability to fail over on a bad morning is worth having.

---

## 2.6 Data architecture

```
                     ┌──────────────┐
   WS tick stream ──▶│ tick buffer  │──▶ Parquet (partitioned by date/symbol)
                     │  (Redis)     │
                     └──────┬───────┘
                            │ 1-min aggregation
                            ▼
                     ┌──────────────┐
                     │   DuckDB     │◄── backtests query this directly
                     │  candles,    │    (embedded, zero-ops, fast on Parquet)
                     │  chains, OI  │
                     └──────────────┘

   Postgres: orders, fills, positions, journal, config, audit, strategy_metrics
   Redis:    live position state, locks, OPS token bucket, kill-switch flag
```

**Why DuckDB + Parquet over a server database for v1:** zero operational overhead, excellent columnar scan performance, queries Parquet in place, and the whole dataset is portable files you can back up with `rsync`. Options chain data is wide and append-only — an ideal Parquet workload. Move to QuestDB only if tick ingestion actually becomes the bottleneck, which for a single trader it will not.

### Data you must capture from day one

**You cannot backtest what you did not record, and option chain history is expensive to buy.** Start recording before you start building — the dataset compounds in value and the gap can never be filled retroactively.

| Dataset | Frequency | Retention | Why |
|---|---|---|---|
| Underlying 1-min OHLCV | 1 min | Forever | Core |
| **Option chain snapshot** (all strikes: LTP, bid, ask, OI, IV, volume) | **1 min** | Forever | **The single most valuable asset. Buy nowhere, record daily.** |
| ATM straddle price | 1 min | Forever | Expected-move proxy (KB `02` §D5) |
| India VIX | 1 min | Forever | Regime classification |
| Own order/fill records | Per event | 5 yrs (compliance) | Slippage analysis, audit |
| XAUUSD / GOLDM ticks | Tick | 1 yr, then 1-min | Lane B |
| Account equity curve | 1 min | Forever | Drawdown tracking |

Storage estimate: a full Nifty option chain at 1-min for a full session ≈ 2–5 MB/day compressed. **Under 2 GB/year.** This is nothing — record everything.

---

## 2.7 Backtesting engine

**Recommendation: build a custom engine on DuckDB + Polars. Do not adopt a framework for Lane A.**

Reasoning:
- **Backtrader** entered maintenance mode in 2023 — do not start new work on it
- **VectorBT** is excellent for parameter sweeps but its simplified fill model overstates fills, which is exactly the error that kills options backtests (KB `09` Rule 3)
- **NautilusTrader** is the strongest production framework (Rust core, live-trading parity) but its Indian weekly-options support and chain modelling would need substantial adaptation

Indian weekly index options are a narrow enough domain that a purpose-built engine — reading your own recorded chain data from DuckDB — is both simpler and more accurate than bending a general framework. The engine must implement every rule in KB `09-BACKTEST-PROTOCOL.md`, especially:
- Fills at the **unfavourable side of the recorded spread**, never mid
- Full Indian cost model (STT 0.15% sell-side, brokerage, exchange, GST, stamp duty)
- Stops filling at **next open**, not trigger price (gap modelling)
- Per-leg costs on multi-leg structures

**Consider NautilusTrader for Lane B** — XAUUSD is a single instrument with continuous data, which is exactly its sweet spot. Decide in Phase 4.

---

## 2.8 Tech stack summary

```
Language      Python 3.12+
Async         asyncio (WS feeds, monitor loops)
Data          Polars (not pandas — faster, saner API, better memory)
DB            PostgreSQL 16 + SQLAlchemy 2.x
Analytics     DuckDB + Parquet
Cache/State   Redis 7
Scheduler     APScheduler (v1) → Prefect 3 self-hosted (v2)
Broker A      OpenAlgo → Dhan / Zerodha / Groww
Broker B1     MetaTrader5 Python package
Config        Pydantic Settings + YAML
Validation    Pydantic v2 everywhere on IO boundaries
Testing       pytest + pytest-asyncio + hypothesis
Metrics       prometheus-client
Dashboards    Grafana
Alerts        python-telegram-bot
Container     Docker + Docker Compose
CI            GitHub Actions
```

---

## 2.9 Failure philosophy

| Failure | Behaviour |
|---|---|
| Data feed drops | Freeze new entries. **Existing positions keep protective orders.** Alert. |
| Broker API down | Stop new orders. Retry with backoff. If positions open and no recovery in 60s → **alert human, escalate to phone call** |
| Job crashes | Scheduler retries per policy. 3 consecutive failures → disable job + alert |
| Risk engine unreachable | **Block all orders.** No order ever bypasses the gate. |
| Clock skew > 2s | Halt. Time-based entries and expiry logic are unsafe with a bad clock. |
| Partial multi-leg fill | Execute the leg-failure protocol (`06` §E05). **Never leave a naked short leg.** |
| Kill switch fires | Cancel all → optionally flatten → block new orders → alert → **require manual re-arm** |

**Rule: the system may fail to make money. It may not fail to protect capital.** Every ambiguous state resolves to "stop trading and tell the human."
