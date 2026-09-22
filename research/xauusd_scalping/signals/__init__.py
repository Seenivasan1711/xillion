"""
Composable signal toolkit for the XAUUSD scalping research pipeline.

Deliberately split into independently-callable pieces, per Rakesh's own
instruction (2026-09-22): "have separate classes methods to call for each
things separately so when we move to LLM/JEV they may use them separately
whatever order they wanted to come up with proper signals kind off." None
of the 10 shortlisted strategies reimplement detection logic inline -- they
compose calls into `PriceActionSignals` (market-structure/liquidity
triggers), `IndicatorSignals` (the confidence-layer inputs -- kept and
available even though v1's indicator-led strategies aren't standalone
anymore), and `ConfidenceScorer` (the generic weighted composer). A future
LLM/JEV orchestrator can call any of these methods directly, in any
combination/order, rather than being limited to one of the 10 fixed
pipelines below.
"""

from .confidence import ConfidenceScorer
from .indicators import IndicatorSignals
from .price_action import PriceActionSignals

__all__ = ["PriceActionSignals", "IndicatorSignals", "ConfidenceScorer"]
