"""Buscador modular de oportunidades de financiación para CARIBDIS."""

from .models import Incident, Opportunity, RunResult, ScoringBreakdown
from .scoring import apply_caribdis_scoring, score_caribdis

__all__ = [
    "Incident",
    "Opportunity",
    "RunResult",
    "ScoringBreakdown",
    "apply_caribdis_scoring",
    "score_caribdis",
]
