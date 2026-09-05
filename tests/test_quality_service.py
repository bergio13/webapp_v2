"""
tests/test_quality_service.py — Unit tests for Bayesian Quality Prior & Acclaim Calibration
"""

import math
import numpy as np
import pytest
from services.quality_service import (
    compute_bayesian_quality_score,
    estimate_catalogue_mean,
    apply_quality_prior_additive,
    apply_quality_prior_log_odds,
    batch_apply_quality_prior,
    DEFAULT_CATALOGUE_MEAN,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_QUALITY_WEIGHT
)


def test_bayesian_quality_formula_basic():
    # R_i = 8.0, v_i = 250, C = 7.0, m = 250
    # Q_i = (250 / 500) * 8.0 + (250 / 500) * 7.0 = 4.0 + 3.5 = 7.5
    q = compute_bayesian_quality_score(r_i=8.0, v_i=250, c=7.0, m=250.0)
    assert abs(q - 7.5) < 1e-3


def test_bayesian_quality_low_vote_shrinkage():
    # Obscure film with 5 votes of 10.0 must shrink heavily toward catalogue mean C = 6.9
    # Q_i = (5 / 255) * 10.0 + (250 / 255) * 6.9 = 0.196 + 6.765 = 6.961
    q = compute_bayesian_quality_score(r_i=10.0, v_i=5, c=6.9, m=250.0)
    assert q < 7.1
    assert q > 6.9


def test_bayesian_quality_high_vote_preservation():
    # Established blockbuster with 25,000 votes of 7.4 retains observed rating
    # Q_i = (25000 / 25250) * 7.4 + (250 / 25250) * 6.9 = 7.395
    q = compute_bayesian_quality_score(r_i=7.4, v_i=25000, c=6.9, m=250.0)
    assert abs(q - 7.4) < 0.05


def test_bayesian_quality_missing_or_zero_votes():
    # Zero votes -> entirely catalogue mean
    assert compute_bayesian_quality_score(r_i=8.5, v_i=0, c=6.9) == 6.9
    assert compute_bayesian_quality_score(r_i=8.5, v_i=None, c=6.9) == 6.9
    # Missing rating -> catalogue mean
    assert compute_bayesian_quality_score(r_i=None, v_i=1000, c=6.9) == 6.9
    assert compute_bayesian_quality_score(r_i=0.0, v_i=1000, c=6.9) == 6.9


def test_bayesian_quality_safe_boundary_and_types():
    # Extreme ratings clamped to [1.0, 10.0]
    q_high = compute_bayesian_quality_score(r_i=15.0, v_i=1000, c=7.0)
    assert q_high <= 10.0

    q_low = compute_bayesian_quality_score(r_i=-2.0, v_i=1000, c=7.0)
    assert q_low == 7.0  # treated as missing/invalid

    # String numeric inputs
    q_str = compute_bayesian_quality_score(r_i="7.8", v_i="500", c="6.8", m="250")
    assert 7.0 <= q_str <= 7.8


def test_estimate_catalogue_mean():
    # Trims extreme outliers
    items = [
        {"vote_average": 7.0},
        {"vote_average": 7.2},
        {"vote_average": 6.8},
        {"vote_average": 7.1},
        {"vote_average": 6.9},
        {"vote_average": 7.3},
        {"vote_average": 1.0},   # low outlier
        {"vote_average": 10.0},  # high outlier
    ]
    c = estimate_catalogue_mean(items)
    assert 6.8 <= c <= 7.3

    # Fallback on sparse items
    assert estimate_catalogue_mean([{"vote_average": 8.0}], fallback_c=6.9) == 6.9


def test_apply_quality_prior_additive():
    # High quality film (Q = 8.9, C = 6.9) -> delta_i = +0.20
    # shift = 0.08 * 1.0 * 0.20 = +0.016
    score, delta = apply_quality_prior_additive(base_score=0.60, q_i=8.9, c=6.9, alpha=0.08, veto_factor=1.0)
    assert abs(delta - 0.016) < 1e-3
    assert abs(score - 0.616) < 1e-3

    # Low quality film (Q = 4.9, C = 6.9) -> delta_i = -0.20
    # shift = 0.08 * 1.0 * (-0.20) = -0.016
    score_low, delta_low = apply_quality_prior_additive(base_score=0.60, q_i=4.9, c=6.9, alpha=0.08, veto_factor=1.0)
    assert delta_low < 0
    assert score_low < 0.60


def test_veto_gate_blocks_quality_boost():
    # If a film is vetoed (veto_factor = 0.0), even a 10/10 masterpiece receives ZERO delta
    score, delta = apply_quality_prior_additive(base_score=0.0, q_i=9.8, c=6.9, alpha=0.08, veto_factor=0.0)
    assert delta == 0.0
    assert score == 0.0


def test_personal_match_preservation_over_popular_blockbuster():
    """
    Core user requirement:
    'It should also be weak enough that a popular film does not outrank a strong personal match.'
    """
    # Film A: Strong personal taste match (base affinity 0.72), average TMDB rating (6.8, 150 votes)
    # Film B: Mediocre personal match (base affinity 0.52), popular blockbuster (8.6, 25,000 votes)
    q_a = compute_bayesian_quality_score(r_i=6.8, v_i=150, c=6.9, m=250.0)
    q_b = compute_bayesian_quality_score(r_i=8.6, v_i=25000, c=6.9, m=250.0)

    score_a, delta_a = apply_quality_prior_additive(base_score=0.72, q_i=q_a, c=6.9, alpha=0.08, veto_factor=1.0)
    score_b, delta_b = apply_quality_prior_additive(base_score=0.52, q_i=q_b, c=6.9, alpha=0.08, veto_factor=1.0)

    # Film A must decisively outrank Film B despite Film B's blockbuster acclaim
    assert score_a > score_b
    assert (score_a - score_b) > 0.15


def test_apply_quality_prior_log_odds():
    # Probability in log-odds space
    prob, shift = apply_quality_prior_log_odds(base_prob=0.70, q_i=8.5, c=6.9, gamma=0.18, veto_factor=1.0)
    assert prob > 0.70
    assert shift > 0.0

    # Vetoed item logit shift is 0
    prob_vetoed, shift_vetoed = apply_quality_prior_log_odds(base_prob=0.50, q_i=9.0, c=6.9, gamma=0.18, veto_factor=0.0)
    assert shift_vetoed == 0.0
    assert prob_vetoed == 0.50


def test_batch_apply_quality_prior():
    pool = [
        # Watched item (should not be modified by acclaim prior)
        {"title": "My Favorite", "is_watched": True, "rating": 5, "vote_average": 8.5, "vote_count": 5000},
        # Unwatched masterpiece with high votes
        {"title": "Masterpiece", "is_watched": False, "rating": 0, "vote_average": 8.8, "vote_count": 4000},
        # Unwatched niche item with 4 votes of 9.5 (must shrink to catalogue mean)
        {"title": "Inflated Niche", "is_watched": False, "rating": 0, "vote_average": 9.5, "vote_count": 4},
        # Curated masterwork without explicit votes (receives canon proxy)
        {"title": "Curated Classic", "is_watched": False, "rating": 0, "rating_score": 8.7, "canon_tier": "palme_dor_festival", "source": "cinephile_corpus"},
        # Low quality candidate
        {"title": "Flop", "is_watched": False, "rating": 0, "vote_average": 4.2, "vote_count": 3000}
    ]
    base_scores = np.array([0.80, 0.65, 0.65, 0.65, 0.65], dtype=np.float32)
    veto_factors = np.array([1.0, 1.0, 1.0, 1.0, 1.0], dtype=np.float32)

    adj_scores, diags, meta = batch_apply_quality_prior(
        pool=pool,
        candidate_vetoed_scores=base_scores,
        veto_factors=veto_factors,
        m=250.0,
        alpha=0.08,
        mode="additive"
    )

    assert len(adj_scores) == 5
    # 1. Watched item is unchanged
    assert adj_scores[0] == 0.80
    assert diags[0]["is_applicable"] is False

    # 2. Masterpiece with 4000 votes receives genuine boost
    assert adj_scores[1] > 0.65
    assert diags[1]["bayesian_quality"] > 8.5

    # 3. Inflated niche item with 4 votes gets shrunk close to catalogue mean, delta is tiny
    cat_mean = meta["catalogue_mean"]
    assert abs(diags[2]["bayesian_quality"] - cat_mean) < 0.15

    # 4. Curated masterwork received proxy votes and maintains high acclaim
    assert diags[3]["is_curated_proxy"] is True
    assert diags[3]["bayesian_quality"] > 8.4
    assert adj_scores[3] > 0.65

    # 5. Flop receives negative delta
    assert adj_scores[4] < 0.65
    assert diags[4]["delta"] < 0.0

    # 6. Telemetry metadata is populated
    assert "catalogue_mean" in meta
    assert meta["evaluated_candidates"] == 4
    assert meta["max_quality_boost"] > 0.0
    assert meta["max_quality_penalty"] < 0.0
