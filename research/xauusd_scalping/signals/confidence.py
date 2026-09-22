"""
Generic confidence-score composer -- the "confidence level markup" layer
Rakesh asked to keep indicators around for (2026-09-22), same
informational-not-a-gate shape as `_confidence_score()` in this repo's own
production `strategies/gold_sweep_reversal.py` (weighted components, a
0-100 score, human-readable reasons), but generic and reusable rather than
hardcoded to one strategy's specific inputs -- any strategy module (or a
future LLM/JEV orchestrator) hands it a list of named, weighted components
and gets a score + reasons back.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfidenceComponent:
    """One input to the score. `value_0_100` is the component's own
    contribution on a 0-100 scale (the caller normalizes whatever raw
    signal it has -- an ATR percentile, an RSI divergence magnitude, a
    loss-streak count -- into this range before handing it in, since only
    the caller knows that signal's own natural range). `weight` is how much
    this component counts toward the final score; weights need not sum to
    1.0 (they're normalized internally)."""

    name: str
    value_0_100: float
    weight: float
    reason: str = ""


@dataclass(frozen=True)
class ConfidenceResult:
    score: int  # 0-100
    reasons: list[str]


class ConfidenceScorer:
    def score(self, components: list[ConfidenceComponent]) -> ConfidenceResult:
        """Weighted average of every component's 0-100 value, clamped and
        rounded to an int 0-100. Empty input scores neutral (50), not 0 --
        "no confidence signal available" is not the same claim as "very low
        confidence," and should not silently look identical to it."""
        if not components:
            return ConfidenceResult(score=50, reasons=["no confidence components supplied"])

        total_weight = sum(c.weight for c in components)
        if total_weight <= 0:
            return ConfidenceResult(score=50, reasons=["all component weights were zero"])

        weighted_sum = sum(c.value_0_100 * c.weight for c in components)
        raw_score = weighted_sum / total_weight
        clamped = max(0, min(100, round(raw_score)))

        reasons = [c.reason for c in components if c.reason] or [
            f"{c.name}={c.value_0_100:.0f} (weight {c.weight})" for c in components
        ]
        return ConfidenceResult(score=clamped, reasons=reasons)
