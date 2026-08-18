"""
Centralized backend configuration, read from environment variables.

This is the project's first environment-variable-driven config point --
currently it only holds the Re-ID decision engine's thresholds
(app.services.reid_decision), but it's the natural place to extend if the
project grows more configuration later.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class InvalidReIDConfigError(ValueError):
    """Raised when the Re-ID threshold configuration is invalid (e.g. a
    non-numeric env var, a value outside [-1.0, 1.0], or
    AUTO_MATCH_THRESHOLD <= REVIEW_THRESHOLD). Fails loudly and early
    rather than silently misclassifying every /api/analyze call."""


# ---------------------------------------------------------------------------
# Re-ID decision engine thresholds
# ---------------------------------------------------------------------------
#
# These are PROTOTYPE / DEMO defaults, NOT scientifically validated values.
# They are compared against app.services.ai_pipeline.cosine_similarity's
# output: the cosine similarity of two L2-normalized MegaDescriptor-L-384
# embeddings, which is mathematically bounded to [-1.0, 1.0] (1.0 =
# identical embedding, 0.0 = orthogonal, negative = anti-correlated).
#
# Treat these two defaults as a starting point only, to be calibrated
# against real Pench/tiger data before any production use:
#   REID_AUTO_MATCH_THRESHOLD = 0.75  -- auto-accept as the same tiger
#   REID_REVIEW_THRESHOLD     = 0.50  -- flag for human review instead of
#                                        auto-accepting or auto-rejecting
#
# Override either via environment variables of the same name, e.g.:
#   REID_AUTO_MATCH_THRESHOLD=0.80 REID_REVIEW_THRESHOLD=0.55 uvicorn app.main:app
DEFAULT_AUTO_MATCH_THRESHOLD = 0.75
DEFAULT_REVIEW_THRESHOLD = 0.50

_AUTO_MATCH_ENV_VAR = "REID_AUTO_MATCH_THRESHOLD"
_REVIEW_ENV_VAR = "REID_REVIEW_THRESHOLD"


def _read_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise InvalidReIDConfigError(
            f"Environment variable {name}='{raw}' is not a valid float."
        ) from exc


@dataclass(frozen=True)
class ReIDSettings:
    auto_match_threshold: float
    review_threshold: float

    def __post_init__(self) -> None:
        if not (-1.0 <= self.review_threshold <= 1.0):
            raise InvalidReIDConfigError(
                f"{_REVIEW_ENV_VAR}={self.review_threshold} is out of the "
                "valid cosine-similarity range [-1.0, 1.0]."
            )
        if not (-1.0 <= self.auto_match_threshold <= 1.0):
            raise InvalidReIDConfigError(
                f"{_AUTO_MATCH_ENV_VAR}={self.auto_match_threshold} is out "
                "of the valid cosine-similarity range [-1.0, 1.0]."
            )
        if self.auto_match_threshold <= self.review_threshold:
            raise InvalidReIDConfigError(
                f"{_AUTO_MATCH_ENV_VAR} ({self.auto_match_threshold}) must "
                f"be strictly greater than {_REVIEW_ENV_VAR} "
                f"({self.review_threshold})."
            )


def get_reid_settings() -> ReIDSettings:
    """Read + validate the Re-ID thresholds from the environment.

    Deliberately not cached/memoized: re-reading os.environ on every call
    is cheap, keeps a long-running process able to pick up config changes
    without a restart, and lets tests monkeypatch/os.environ per-test
    without needing to reset a module-level cache.
    """
    return ReIDSettings(
        auto_match_threshold=_read_float_env(
            _AUTO_MATCH_ENV_VAR, DEFAULT_AUTO_MATCH_THRESHOLD
        ),
        review_threshold=_read_float_env(_REVIEW_ENV_VAR, DEFAULT_REVIEW_THRESHOLD),
    )
