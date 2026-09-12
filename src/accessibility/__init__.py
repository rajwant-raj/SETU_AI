"""SETU Road Accessibility Intelligence Module."""

from .accessibility_scorer import (
    AccessibilityValidationError,
    calculate_accessibility,
    score_segments,
    ACCESSIBILITY_WEIGHTS,
    LEVEL_HIGH_THRESHOLD,
    LEVEL_MEDIUM_THRESHOLD,
    LEVEL_LOW_THRESHOLD,
)

__all__ = [
    "AccessibilityValidationError",
    "calculate_accessibility",
    "score_segments",
    "ACCESSIBILITY_WEIGHTS",
    "LEVEL_HIGH_THRESHOLD",
    "LEVEL_MEDIUM_THRESHOLD",
    "LEVEL_LOW_THRESHOLD",
]
