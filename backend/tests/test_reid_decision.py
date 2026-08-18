"""
Unit tests for the Re-ID decision engine (app.services.reid_decision) and
its configuration (app.config).

These are pure unit tests -- no HTTP layer, no DB, no AI models -- for the
decision logic and threshold validation in isolation. End-to-end coverage
through /api/analyze lives in tests/test_analyze.py.

Run from backend/:  pytest -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import schemas
from app.config import InvalidReIDConfigError, ReIDSettings, get_reid_settings
from app.services import reid_decision


def _candidate(tiger_id: str, score: float) -> schemas.CandidateMatch:
    return schemas.CandidateMatch(tiger_id=tiger_id, similarity_score=score)


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------


def test_high_similarity_is_auto_match(monkeypatch):
    monkeypatch.delenv("REID_AUTO_MATCH_THRESHOLD", raising=False)
    monkeypatch.delenv("REID_REVIEW_THRESHOLD", raising=False)

    decision = reid_decision.decide([_candidate("TIGER-001", 0.94)])

    assert decision.match_status == reid_decision.AUTO_MATCH
    assert decision.matched_tiger_id == "TIGER-001"
    assert decision.best_similarity == pytest.approx(0.94)
    assert decision.review_required is False


def test_middle_similarity_is_review(monkeypatch):
    monkeypatch.delenv("REID_AUTO_MATCH_THRESHOLD", raising=False)
    monkeypatch.delenv("REID_REVIEW_THRESHOLD", raising=False)

    decision = reid_decision.decide([_candidate("TIGER-001", 0.60)])

    assert decision.match_status == reid_decision.REVIEW
    assert decision.matched_tiger_id is None
    assert decision.best_similarity == pytest.approx(0.60)
    assert decision.review_required is True


def test_low_similarity_is_possible_new(monkeypatch):
    monkeypatch.delenv("REID_AUTO_MATCH_THRESHOLD", raising=False)
    monkeypatch.delenv("REID_REVIEW_THRESHOLD", raising=False)

    decision = reid_decision.decide([_candidate("TIGER-001", 0.20)])

    assert decision.match_status == reid_decision.POSSIBLE_NEW
    assert decision.matched_tiger_id is None
    assert decision.best_similarity == pytest.approx(0.20)
    assert decision.review_required is True


def test_no_candidates_is_possible_new(monkeypatch):
    monkeypatch.delenv("REID_AUTO_MATCH_THRESHOLD", raising=False)
    monkeypatch.delenv("REID_REVIEW_THRESHOLD", raising=False)

    decision = reid_decision.decide([])

    assert decision.match_status == reid_decision.POSSIBLE_NEW
    assert decision.matched_tiger_id is None
    assert decision.best_similarity is None
    assert decision.confidence is None
    assert decision.review_required is True


def test_thresholds_are_inclusive_boundaries(monkeypatch):
    """AUTO_MATCH is best_similarity >= threshold (not strictly greater),
    and likewise for REVIEW -- exact boundary values should land on the
    higher-confidence side."""
    monkeypatch.setenv("REID_AUTO_MATCH_THRESHOLD", "0.75")
    monkeypatch.setenv("REID_REVIEW_THRESHOLD", "0.50")

    assert reid_decision.decide([_candidate("T", 0.75)]).match_status == reid_decision.AUTO_MATCH
    assert reid_decision.decide([_candidate("T", 0.50)]).match_status == reid_decision.REVIEW
    assert (
        reid_decision.decide([_candidate("T", 0.4999)]).match_status
        == reid_decision.POSSIBLE_NEW
    )


def test_nan_similarity_is_ignored_like_no_candidate(monkeypatch):
    monkeypatch.delenv("REID_AUTO_MATCH_THRESHOLD", raising=False)
    monkeypatch.delenv("REID_REVIEW_THRESHOLD", raising=False)

    decision = reid_decision.decide([_candidate("TIGER-NAN", float("nan"))])

    assert decision.match_status == reid_decision.POSSIBLE_NEW
    assert decision.matched_tiger_id is None


def test_duplicate_and_tied_candidates_use_best_score(monkeypatch):
    monkeypatch.delenv("REID_AUTO_MATCH_THRESHOLD", raising=False)
    monkeypatch.delenv("REID_REVIEW_THRESHOLD", raising=False)

    # Duplicate tiger_id: keep the higher of the two scores.
    decision = reid_decision.decide(
        [_candidate("TIGER-DUP", 0.3), _candidate("TIGER-DUP", 0.9)]
    )
    assert decision.match_status == reid_decision.AUTO_MATCH
    assert decision.matched_tiger_id == "TIGER-DUP"
    assert decision.best_similarity == pytest.approx(0.9)

    # Two different tigers tied at the same score: decision is still
    # deterministic and doesn't crash.
    decision = reid_decision.decide(
        [_candidate("TIGER-A", 0.9), _candidate("TIGER-B", 0.9)]
    )
    assert decision.match_status == reid_decision.AUTO_MATCH
    assert decision.matched_tiger_id in {"TIGER-A", "TIGER-B"}


# ---------------------------------------------------------------------------
# Configuration validation
# ---------------------------------------------------------------------------


def test_default_thresholds_are_valid(monkeypatch):
    monkeypatch.delenv("REID_AUTO_MATCH_THRESHOLD", raising=False)
    monkeypatch.delenv("REID_REVIEW_THRESHOLD", raising=False)

    settings = get_reid_settings()
    assert settings.auto_match_threshold == pytest.approx(0.75)
    assert settings.review_threshold == pytest.approx(0.50)


def test_custom_thresholds_from_env(monkeypatch):
    monkeypatch.setenv("REID_AUTO_MATCH_THRESHOLD", "0.85")
    monkeypatch.setenv("REID_REVIEW_THRESHOLD", "0.60")

    settings = get_reid_settings()
    assert settings.auto_match_threshold == pytest.approx(0.85)
    assert settings.review_threshold == pytest.approx(0.60)


def test_auto_match_threshold_must_exceed_review_threshold():
    with pytest.raises(InvalidReIDConfigError):
        ReIDSettings(auto_match_threshold=0.5, review_threshold=0.5)

    with pytest.raises(InvalidReIDConfigError):
        ReIDSettings(auto_match_threshold=0.4, review_threshold=0.6)


def test_thresholds_out_of_range_are_rejected():
    with pytest.raises(InvalidReIDConfigError):
        ReIDSettings(auto_match_threshold=1.5, review_threshold=0.5)

    with pytest.raises(InvalidReIDConfigError):
        ReIDSettings(auto_match_threshold=0.9, review_threshold=-2.0)


def test_non_numeric_env_var_raises_clear_error(monkeypatch):
    monkeypatch.setenv("REID_AUTO_MATCH_THRESHOLD", "not-a-number")
    monkeypatch.setenv("REID_REVIEW_THRESHOLD", "0.5")

    with pytest.raises(InvalidReIDConfigError):
        get_reid_settings()


def test_invalid_env_config_surfaces_from_decide(monkeypatch):
    """The decision engine must propagate a bad configuration as a clear
    error rather than silently misclassifying every request."""
    monkeypatch.setenv("REID_AUTO_MATCH_THRESHOLD", "0.4")
    monkeypatch.setenv("REID_REVIEW_THRESHOLD", "0.5")  # invalid: auto <= review

    with pytest.raises(InvalidReIDConfigError):
        reid_decision.decide([_candidate("TIGER-001", 0.9)])
