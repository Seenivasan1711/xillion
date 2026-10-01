---
name: feedback-second-opinion-for-ambiguous-design
description: "For genuinely ambiguous research/design calls with no objectively correct answer, write a self-contained problem statement for a second LLM rather than unilaterally picking a threshold"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: c4a629f4-5810-4c61-8b59-3a9063bc1426
  modified: 2026-09-23T15:51:05.529Z
---

When a fix requires picking a genuinely arbitrary design choice (a
detection algorithm, a threshold with no principled derivation, anything
where "correct" isn't determinable by testing alone) — don't just pick one
and ship it, even if it's clearly labeled as a best-effort guess. Either
leave it explicitly unresolved/deferred, or write a self-contained
problem-statement document (buggy code, empirical evidence of the
problem, prior attempts already tried and why they failed, the exact
interface/constraints the answer must fit) that could be handed to a
completely different LLM with zero other context and get back something
directly actionable.

**Why:** confirmed 2026-09-23 on xillion's XAUUSD research track (Track
B) — found a real bug in a range-detection check (`range_spring_upthrust`
in `research/xauusd_scalping/signals/price_action.py`), tried two
candidate fixes, correctly judged both as guesses rather than validated
corrections, and left it unresolved with the reasoning documented (see
D27 in `docs/status/decisions-and-open-questions.md`). Rakesh's response
confirmed this was the right call: not "here's my fix, good enough" but
"write this up so I can get another LLM's opinion on it" — validating the
instinct to flag genuine design ambiguity rather than resolve it alone
under time pressure.

**How to apply:** watch for the tell that a "fix" is actually an
unprincipled guess — e.g. no clean derivation from data/spec, chosen
because "something needs to work" rather than because it's demonstrably
correct, or arrived at by trying values until one produces a plausible-
looking result. In that situation, default to writing the portable
problem-statement doc (see
`research/xauusd_scalping/S04_range_detection_design_question.md` for the
concrete template: buggy code + empirical evidence + rejected attempts +
exact interface to fit) rather than presenting a single-model guess as if
it were a resolved fix. This generalizes beyond this one repo — the
pattern is "ambiguous design judgment call, no way to verify correctness
from data alone" → get a second opinion, don't unilaterally decide.
