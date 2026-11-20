"""Deterministic job-fit scoring and skill-gap classification."""

from .gaps import classify_gaps
from .models import FitScore, GapResult, RequirementMatch
from .score import calculate_fit

__all__ = ["FitScore", "GapResult", "RequirementMatch", "calculate_fit", "classify_gaps"]
