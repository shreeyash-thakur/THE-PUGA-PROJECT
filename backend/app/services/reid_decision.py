"""
Re-ID decision engine.

Turns a list of ranked candidate matches (per-tiger best similarity
scores, as already computed by app.services.analyze_service) into exactly
one automatic decision:

    AUTO_MATCH    -- best similarity >= REID_AUTO_MATCH_THRESHOLD
    REVIEW        -- REID_REVIEW_THRESHOLD <= best similarity < REID_AUTO_MATCH_THRESHOLD
    POSSIBLE_NEW  -- best similarity < REID_REVIEW_THRESHOLD (or no candidates at all)

This module is pure decision logic: it does not touch the database, the
filesystem, or the AI pipeline, and it does not decide *what to do* with
the decision (e.g. whether to create/assign a Tiger row) -- that's
app.services.analyze_service's job. Keeping this separate makes the
thresholds/logic easy to unit test and easy to recalibrate later.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional, Sequence

from app import schemas
from app.config import get_reid_settings

logger = logging.getLogger(__name__)

AUTO_MATCH = "AUTO_MATCH"
REVIEW = "REVIEW"
POSSIBLE_NEW = "POSSIBLE_NEW"


@dataclass(frozen=True)
class ReIDDecision:
    match_status: str  # AUTO_MATCH | REVIEW | POSSIBLE_NEW
    matched_tiger_id: Optional[str]
    best_similarity: Optional[float]
    confidence: Optional[float]
    review_required: bool


def _rank_valid_candidates(
    candidates: Sequence["schemas.CandidateMatch"],
) -> list["schemas.CandidateMatch"]:
    """Defensive normalization of the incoming candidate list: drops
    invalid (None/NaN) similarity scores, collapses duplicate tiger_ids
    down to their single best score, and sorts descending.

    analyze_service already produces a deduped, sorted, valid list, but
    the decision engine shouldn't silently trust that -- this keeps the
    engine correct even if called from somewhere else, or with hand-built
    test data.
    """
    best_per_tiger: dict[str, "schemas.CandidateMatch"] = {}
    for candidate in candidates:
        score = candidate.similarity_score
        if score is None or (isinstance(score, float) and math.isnan(score)):
            continue
        existing = best_per_tiger.get(candidate.tiger_id)
        if existing is None or score > existing.similarity_score:
            best_per_tiger[candidate.tiger_id] = candidate

    return sorted(
        best_per_tiger.values(), key=lambda c: c.similarity_score, reverse=True
    )


def decide(candidates: Sequence["schemas.CandidateMatch"]) -> ReIDDecision:
    """Classify a candidate list into a Re-ID decision using the
    configured thresholds (app.config.get_reid_settings).

    Raises app.config.InvalidReIDConfigError if the configured thresholds
    are invalid -- callers should let this propagate as a clear startup
    /request-time error rather than silently falling back to defaults.
    """
    settings = get_reid_settings()

    ranked = _rank_valid_candidates(candidates)

    if not ranked:
        # Covers both "no existing tiger embeddings at all" and "every
        # candidate had an invalid/NaN score" -- both mean we have no
        # usable evidence of a match.
        logger.info(
            "RE-ID: no valid candidates (received=%d) -> decision=%s",
            len(candidates),
            POSSIBLE_NEW,
        )
        return ReIDDecision(
            match_status=POSSIBLE_NEW,
            matched_tiger_id=None,
            best_similarity=None,
            confidence=None,
            review_required=True,
        )

    best = ranked[0]
    best_similarity = best.similarity_score

    if best_similarity >= settings.auto_match_threshold:
        match_status = AUTO_MATCH
        matched_tiger_id = best.tiger_id
        review_required = False
    elif best_similarity >= settings.review_threshold:
        match_status = REVIEW
        matched_tiger_id = None
        review_required = True
    else:
        match_status = POSSIBLE_NEW
        matched_tiger_id = None
        review_required = True

    logger.info(
        "RE-ID: best_candidate=%s similarity=%.4f decision=%s "
        "auto_match_threshold=%.4f review_threshold=%.4f",
        best.tiger_id,
        best_similarity,
        match_status,
        settings.auto_match_threshold,
        settings.review_threshold,
    )

    return ReIDDecision(
        match_status=match_status,
        matched_tiger_id=matched_tiger_id,
        best_similarity=best_similarity,
        confidence=best_similarity,
        review_required=review_required,
    )
