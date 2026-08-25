---
doc_id: 11-SOURCES
title: Source Ledger and Confidence Audit
topic: where every claim came from, how much to trust it, known-stale warnings
compiled: 2026-08-24
use_when: User asks "how do you know this", or a claim needs provenance
---

# 11 — SOURCE LEDGER AND CONFIDENCE AUDIT

## Confidence tier definitions

| Tier | Meaning | How to present it |
|---|---|---|
| **T1** | Real backtest, stated sample size / period / metrics | "Backtested over N trades…" |
| **T2** | Academic / preprint, methodology disclosed | "A study of X found…" |
| **T3** | Vendor or education site, no methodology | "A broker site claims… (unverified)" |
| **T4** | True by construction (arithmetic) | State plainly — most reliable content here |
| **T5** | Rules exist, no performance data | "Rules are documented; no win rate is known" |

---

## T1 — BACKTESTED (the only performance evidence with disclosed samples)

| Claim | Detail | Source |
|---|---|---|
| **8-yr Nifty ORB** | 48.7% WR, PF 1.23, Sharpe 1.16, DD −11.2%, **2,122 trades**, Jul 2017–Mar 2026, +91.6% | intradaylab.com |
| **ORB 5-min variants** | 57.1% WR (1.5R cap) / 71.4% WR (RSI exit), **42 signals**, Jul–Oct 2025, Nifty futures | dailybulls.in |
| **45-DTE Nifty straddle** | ~70% WR, **~86% with VIX>75th pct filter**, ~86 cycles, Jan 2019–Jun 2026, net of costs; one trade lost >1,000 pts despite stop | Zerodha (In The Money) |
| 45-DTE strangle comparison | 30Δ: ~62% WR · 16Δ: ~57% WR | Zerodha (In The Money) |
| **Short strangle, 60 cycles** | 68% WR, −24% max DD from a 5-loss cluster; 12% index fall modelled at 7.7× max profit. **US SPY data** | apexvol.com |

⚠️ The strangle study is **US SPY**, not Indian. Mechanism transfers; magnitudes do not.

---

## T2 — ACADEMIC / RESEARCH

| Claim | Detail | Source |
|---|---|---|
| **Nifty VRP structure** | VRP positive 74.9% of days, mean +1.208 vol pts; costs erase 27.6%; left-tail asymmetry 1.975×; **early-2026 inversion to −4.63 vol pts**. 43M one-minute bars, Aug 2022–Mar 2026 | SSRN (Agarwal) — Variance Risk Premium in Nifty 50 |
| **Pullback+breakout scalping** | 65% WR, 1:2 R:R, **53 trades**, Bank Nifty, TradingView paper accounts | IJCRT paper |
| **SEBI F&O study (FY22)** | 91.1% of individuals lost after costs; ₹1.1L avg loss; **71% of ₹51,689cr aggregate losses were transaction costs**; 1–2% cleared >₹1L; profitable traders traded *less* | SEBI via marketnetra.in |

⚠️ 53 trades is below the threshold for statistical confidence (`09` §Sample size).

---

## T3 — VENDOR-CLAIMED (no methodology — treat as hypotheses)

| Claim | Source |
|---|---|
| Iron condor 65–70% at entry, ~80% managed; 15–20Δ; 30–45 DTE; 50% profit target; 200% stop | apexvol.com |
| Credit spread 60–70%, ~75% managed; delta→POP table | apexvol.com |
| 10-strategy win-rate ranking (condor 70–80% … naked 30–40%) | zerroday.com |
| Time-based straddle: SL-width → win rate table (25%→65-70%, 50%→72-78%, none→55-60%); entry-time comparison | quintalmind.com |
| 9/21 EMA: 45–50% base → 60–68% filtered | sahi.com |
| Expiry-day theta/gamma magnitudes (₹20–40/hr decay; 50-pt move → 35–45 pt premium swing; 70–80% value loss 1–3 PM) | sahi.com, lemonn.co.in |
| Expiry-day scalping setups (ORB scalp, theta scalp, max pain convergence) + 3 windows | sahi.com |
| VWAP setups (pullback, reclaim, rejection, squeeze) | sahi.com, tradejini.com |
| Bank Nifty 1-min scalp break-even math; ₹40–60/lot costs | bankniftyoptions.com |
| Option chain reads: OI, PCR thresholds, buildup quadrants, max pain | optionx.trade, niftytrader.in |
| Butterfly worked example (3:1 R:R) — ⚠️ source's rupee figures assume lot 25; corrected to lot 65 in `06` | quintalmind.com |
| BWB structure and credit-entry property | optionx.trade |
| 9:20 straddle edge decay in 2023 (crowding + low vol) | marketcalls.in |
| Hedged vs naked margin differential | 5paisa.com |
| Backtesting platform comparison | algotest.in |

---

## T4 — STRUCTURAL (arithmetic — the most reliable content in this KB)

- `Max loss (credit spread) = (width − credit) × lot size × lots`
- `Max loss (long option / butterfly) = premium or debit paid`
- `Max loss (naked short) = unbounded`
- `Break-even win rate = stop / (stop + target)`
- `Expectancy = (Win% × AvgWin) − (Loss% × AvgLoss)`
- `₹ P&L = points × lot size × lots`
- Theta and gamma both accelerate into expiry, in opposite directions for buyer vs seller
- A hedged position's margin is lower because worst-case loss is capped

**These do not require trust. They are true by construction.**

---

## T5 — UNQUANTIFIED (rules exist, no performance data found anywhere)

Iron fly (Indian intraday variants) · 0DTE credit spread win rate · calendar spread on Nifty weeklies · broken wing butterfly · ratio spreads · ZEBRA · jade lizard · Bollinger mean reversion · RSI divergence · price-action BOS/liquidity sweep · delta/footprint divergence · Supertrend on Indian options · gap-up/gap-down systems · max pain convergence · Indian short strangle (backtest published, results section unretrievable)

**Any win rate the user encounters for these online is unsourced.**

---

## 🚨 KNOWN STALE CLAIMS — flag immediately if encountered

Indian F&O rules changed four times in under two years. Much online material is out of date and **still ranks well in search**.

| Stale claim | Current reality | Changed |
|---|---|---|
| "Nifty expires Thursday" | **Tuesday** (NSE) | 1 Sep 2025 |
| "Bank Nifty weekly expiry Wednesday" | **No weekly at all** — monthly, last Tuesday | Nov 2024 |
| "FinNifty Tuesday weekly / MidCpNifty Monday weekly" | **No weeklies** — monthly only | Nov 2024 |
| "Sensex expires Friday" | **Thursday** (BSE) | 1 Sep 2025 |
| "Nifty lot size 75" | **65** | Jan 2026 |
| "Bank Nifty lot size 35" | **30** | Jan 2026 |
| "STT on options 0.10%" | **0.15%** (sell side) | 1 Apr 2026 |
| "Multiple weekly expiries per week" | **One per exchange** | Nov 2024 |
| "No extra expiry-day margin" | **+2% ELM on expiry-day shorts** | Current |

**Encountered during this research:** at least two otherwise-credible sources still described Bank Nifty as having Wednesday weekly expiries, and one described Nifty as Thursday. **If a strategy's edge depends on a specific expiry day, verify the day before trusting the strategy.**

---

## Contradictions found in research (unresolved — do not paper over)

1. **Lot size effective date** — sources gave Oct 2025, Dec 2025, and Jan 2026. Two independent sources agreed on the **values** (Nifty 65, BankNifty 30); the effective date is reported inconsistently. Values are more reliable than dates here.
2. **Transaction charges** — exchange transaction charge quoted anywhere from 0.05% to 0.053%; one calculator still showed the pre-hike 0.05% STT. **Use your broker's actual contract note, not any published table.**
3. **Iron condor win rate** — 65–70% (apexvol) vs 70–80% (zerroday). Both T3, neither with methodology. The disagreement is itself informative about T3 reliability.
4. **Nifty spot level** — one source page showed ~24,252 in an article dated August 2026 while a same-day market report showed ~24,201. Intraday timing differences; use live data.

---

## Full source list

**Backtests / data:**
- [intradaylab.com — Nifty ORB 8-year backtest](https://intradaylab.com/blog/nifty-orb-breakout-strategy-backtest)
- [dailybulls.in — ORB intraday backtest](https://dailybulls.in/orb-intraday-trading-strategy-backtest/)
- [Zerodha In The Money — 45 DTE backtest](https://inthemoneybyzerodha.substack.com/p/we-backtested-the-famous-45-dte-strategy)
- [apexvol.com — short strangle 60-cycle backtest](https://apexvol.com/strategies/strangle/backtest)

**Academic:**
- [SSRN — Variance Risk Premium in Nifty 50 (Agarwal)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6530119)
- [SSRN — Trading the Volatility Risk Premium on Nifty 50 (Pillai)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6876580)
- [IJCRT — Breakout and pullback scalping strategy](https://www.ijcrt.org/papers/IJCRT2504775.pdf)
- [marketnetra.in — SEBI F&O loss data](https://marketnetra.in/blog/why-91-percent-fo-traders-lose-money-sebi)

**Strategy references:**
- [apexvol.com — iron condor](https://apexvol.com/strategies/iron-condor) · [credit spreads](https://apexvol.com/strategies/credit-spread)
- [quintalmind.com — time-based straddle](https://www.quintalmind.com/blog/time-based-straddle-strategy-nifty-options) · [butterfly spread](https://www.quintalmind.com/strategies/butterfly-spread)
- [sahi.com — options scalping guide](https://www.sahi.com/blogs/scalping-trading-strategies-complete-guide) · [expiry day scalping](https://www.sahi.com/blogs/nifty-expiry-day-strategies-scalping-guide) · [0DTE](https://www.sahi.com/blogs/how-to-trade-options-on-expiry-day) · [9/21 EMA](https://www.sahi.com/blogs/ema-scalping-strategy-the-9-21-crossover-setup-for-nifty-and-bank-nifty) · [VWAP setups](https://www.sahi.com/blogs/vwap-scalping-strategy-for-nifty-and-bank-nifty-3-setups-that-work)
- [tradejini.com — Nifty options scalping](https://www.tradejini.com/blogs/introduction-to-scalping-in-nifty-options)
- [zerroday.com — strategies ranked by win rate](https://zerroday.com/blog/best-options-trading-strategies-2026)
- [optionx.trade — option chain](https://optionx.trade/blogs/how-to-read-option-chain-oi-pcr-max-pain) · [broken wing butterfly](https://optionx.trade/blogs/broken-wing-butterfly-options)
- [lemonn.co.in — 0DTE India guide](https://lemonn.co.in/blog/fno/0dte-options-strategy-india-weekly-expiry-guide/)
- [bankniftyoptions.com — Bank Nifty scalping](https://bankniftyoptions.com/artigos/banknifty-scalping-options)
- [Zerodha Varsity — short straddle](https://zerodha.com/varsity/chapter/the-short-straddle/) · [iron condor](https://zerodha.com/varsity/chapter/iron-condor/)
- [marketcalls.in — is the 9:20 straddle still working](https://www.marketcalls.in/futures-and-options/is-the-920-straddle-no-more-working.html)

**Market structure:**
- [strota.in — India expiry schedule 2026](https://strota.in/india-expiry-schedule)
- [venturasecurities.com — NSE/BSE expiry changes](https://www.venturasecurities.com/blog/changes-in-expiry-nse-and-bse/) · [lot size changes Jan 2026](https://www.venturasecurities.com/blog/nifty-bank-nifty-lot-size-changes-january-2026-know-how-it-impacts-traders/)
- [sahi.com — lot sizes 2026](https://www.sahi.com/blogs/nifty-lot-size-2026-bank-nifty-sensex)
- [pocketful.in — SEBI F&O rules](https://www.pocketful.in/blog/trading/sebi-fo-new-rules/)
- [vrdnation.com — STT rates](https://www.vrdnation.com/stt-cash-fno-intraday/) · [patronaccounting.com — STT hike 2026](https://www.patronaccounting.com/blog/stt-hike-2026-securities-transaction-tax-fo-traders)
- [5paisa — hedged vs naked margin](https://www.5paisa.com/stock-market-guide/derivatives-trading-basics/hedged-vs-naked-option-selling-margin-risk-caps-and-sebi-rules)
- [algotest.in — backtesting platforms](https://algotest.in/blog/free-options-backtesting/)
- [finnovate.in — India VIX 2026](https://www.finnovate.in/learn/blog/india-vix-2026-what-fear-index-tells-investors) · [hdfcsky.com — VIX 24 Aug 2026](https://hdfcsky.com/news/india-vix-11-69-iran-sanctions-crude-august-24-2026)

---

## Audit summary

| Tier | Count of distinct claims | Share |
|---|---|---|
| T1 Backtested | 5 | ~8% |
| T2 Research | 3 | ~5% |
| T3 Vendor | ~16 | ~26% |
| T4 Structural | 8 | ~13% |
| T5 Unquantified | ~15 | ~24% |
| Market structure facts | ~15 | ~24% |

**Roughly half of all performance claims in circulation about Indian options strategies are T3 or T5 — vendor marketing or entirely unquantified. Only five carry a disclosed sample size and period, and one of those is US data.**

That ratio is the most important meta-fact in this knowledge base.
