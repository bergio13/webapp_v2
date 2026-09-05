"""
tests/test_calibration_service.py — Unit & Integration Tests for Probabilistic Calibration Engine
"""

import math
import pytest
import numpy as np

from services.calibration_service import (
    PlattCalibrator,
    IsotonicCalibrator,
    apply_empirical_bayes_shrinkage,
    compute_brier_score,
    compute_ece,
    evaluate_calibration,
    classify_history_tier,
    map_to_match_score,
    generate_stratified_calibration_report,
    calibrate_scores,
    classify_interaction_label,
    DEFAULT_GLOBAL_POSITIVE_PRIOR,
)


def test_classify_interaction_label():
    assert classify_interaction_label(5.0) == 1
    assert classify_interaction_label(4.0) == 1
    assert classify_interaction_label(2.0) == 0
    assert classify_interaction_label(1.0) == 0
    assert classify_interaction_label(2.5) == 0
    assert classify_interaction_label(3.0) is None  # Neutral held out
    assert classify_interaction_label(3.5) is None
    assert classify_interaction_label(None) is None
    assert classify_interaction_label(4.0, is_negative_or_abandoned=True) == 0


def test_platt_calibrator_fit_and_monotonicity():
    # Generate synthetic scores with positive correlation to positive interaction
    np.random.seed(42)
    s = np.linspace(0.1, 0.9, 30)
    # Higher scores have higher chance of Y=1
    y = (s + np.random.normal(0, 0.15, size=len(s)) > 0.50).astype(int)

    calibrator = PlattCalibrator().fit(s, y)
    assert calibrator.is_fitted
    assert calibrator.a > 0  # Strictly positive slope

    test_scores = np.array([0.1, 0.3, 0.5, 0.7, 0.9])
    probs = calibrator.predict_proba(test_scores)

    # Monotonicity test
    for i in range(len(probs) - 1):
        assert probs[i] < probs[i + 1], f"Monotonicity failed at index {i}: {probs[i]} >= {probs[i+1]}"

    # Bounds test
    assert np.all(probs > 0.0) and np.all(probs < 1.0)


def test_platt_calibrator_fallback_sparse():
    # Only 3 samples
    s = np.array([0.3, 0.5, 0.8])
    y = np.array([0, 1, 1])

    calibrator = PlattCalibrator().fit(s, y)
    assert calibrator.is_fitted
    probs = calibrator.predict_proba(np.array([0.2, 0.8]))
    assert probs[0] < probs[1]
    assert 0.05 < probs[0] < 0.95


def test_isotonic_calibrator_fit_and_monotonicity():
    np.random.seed(123)
    s = np.linspace(0.05, 0.95, 50)
    y = (s + np.random.normal(0, 0.1, size=50) > 0.45).astype(int)

    iso = IsotonicCalibrator(y_min=0.05, y_max=0.95).fit(s, y)
    assert iso.is_fitted
    assert iso.fallback_platt is None

    test_s = np.array([0.1, 0.25, 0.5, 0.75, 0.9])
    probs = iso.predict_proba(test_s)

    # Non-decreasing monotonicity
    for i in range(len(probs) - 1):
        assert probs[i] <= probs[i + 1]

    assert np.all(probs >= 0.05) and np.all(probs <= 0.95)


def test_isotonic_calibrator_sparse_fallback_to_platt():
    # Too few samples (< 30) triggers Platt fallback
    s = np.array([0.2, 0.4, 0.7, 0.85])
    y = np.array([0, 0, 1, 1])

    iso = IsotonicCalibrator().fit(s, y)
    assert iso.is_fitted
    assert iso.fallback_platt is not None  # Successfully used Platt fallback
    probs = iso.predict_proba(np.array([0.1, 0.9]))
    assert probs[0] < probs[1]


def test_empirical_bayes_shrinkage():
    raw_probs = np.array([0.90, 0.10], dtype=np.float32)
    prior = 0.55

    # Sparse history (N = 2): shrinkage should pull heavily towards prior 0.55
    sparse_shrunk = apply_empirical_bayes_shrinkage(raw_probs, n_user_history=2, segment_prior=prior, pseudo_count=12.0)
    assert abs(sparse_shrunk[0] - prior) < abs(raw_probs[0] - prior)
    assert abs(sparse_shrunk[0] - 0.55) < 0.20  # pulled close to 0.55

    # Rich history (N = 100): shrinkage should barely alter the calibrated probabilities
    rich_shrunk = apply_empirical_bayes_shrinkage(raw_probs, n_user_history=100, segment_prior=prior, pseudo_count=12.0)
    assert abs(rich_shrunk[0] - raw_probs[0]) < 0.06


def test_brier_score_and_ece():
    y_true = np.array([1, 1, 0, 0])
    # Perfect predictions
    p_perfect = np.array([0.99, 0.98, 0.02, 0.01])
    brier_perf = compute_brier_score(y_true, p_perfect)
    assert brier_perf < 0.01

    ece_perf, bins = compute_ece(y_true, p_perfect, n_bins=5)
    assert ece_perf < 0.05
    assert len(bins) == 5

    # Worst predictions
    p_worst = np.array([0.01, 0.02, 0.98, 0.99])
    brier_worst = compute_brier_score(y_true, p_worst)
    assert brier_worst > 0.90


def test_map_to_match_score():
    # High probability, high net
    high_score = map_to_match_score(calibrated_prob=0.92, raw_net=0.85)
    assert isinstance(high_score, int)
    assert 90 <= high_score <= 99

    # Low probability, low net
    low_score = map_to_match_score(calibrated_prob=0.15, raw_net=0.10)
    assert isinstance(low_score, int)
    assert 50 <= low_score <= 65

    # Boundary checks
    assert map_to_match_score(1.0, 1.0) == 99
    assert map_to_match_score(0.0, 0.0) == 50


def test_classify_history_tier():
    assert classify_history_tier(5) == "sparse"
    assert classify_history_tier(9) == "sparse"
    assert classify_history_tier(10) == "moderate"
    assert classify_history_tier(34) == "moderate"
    assert classify_history_tier(35) == "rich"
    assert classify_history_tier(100) == "rich"


def test_generate_stratified_calibration_report():
    # Generate 60 test records stratified by history tier and macro realm
    np.random.seed(42)
    records = []
    realms = ["Sci-Fi", "Arthouse & Drama", "Noir & Crime"]
    history_tiers = ["sparse", "moderate", "rich"]

    for i in range(90):
        h_tier = history_tiers[i % 3]
        seg = realms[i % 3]
        raw_net = float(np.random.uniform(0.1, 0.9))
        y = 1 if (raw_net + np.random.normal(0, 0.15) > 0.5) else 0

        # Simulate calibrated probability
        cal_prob = float(np.clip(raw_net + (0.1 if y == 1 else -0.1), 0.05, 0.95))

        records.append({
            "y_true": y,
            "calibrated_prob": cal_prob,
            "raw_net": raw_net,
            "history_tier": h_tier,
            "catalogue_segment": seg
        })

    report = generate_stratified_calibration_report(records, n_bins=5)
    assert report.overall_metrics.sample_count == 90
    assert report.overall_metrics.brier_score >= 0.0
    assert report.overall_metrics.expected_calibration_error >= 0.0

    # Verify history tier breakdown
    for tier in ["sparse", "moderate", "rich"]:
        assert tier in report.by_history_tier
        assert report.by_history_tier[tier].sample_count == 30

    # Verify catalogue segment breakdown
    for seg in realms:
        assert seg in report.by_catalogue_segment
        assert report.by_catalogue_segment[seg].sample_count == 30

    # Calibrated Brier score should outperform uncalibrated heuristic
    assert report.uncalibrated_brier > 0.0
    assert report.brier_reduction_pct > 0.0


def test_calibrate_scores_end_to_end():
    candidate_net_scores = np.array([0.15, 0.35, 0.55, 0.75, 0.92], dtype=np.float32)
    user_raw_movies = [
        {"id": 1, "movie": "Film A", "rating": 5.0},
        {"id": 2, "movie": "Film B", "rating": 4.5},
        {"id": 3, "movie": "Film C", "rating": 4.0},
        {"id": 4, "movie": "Film D", "rating": 2.0},
        {"id": 5, "movie": "Film E", "rating": 1.5},
        {"id": 6, "movie": "Film F", "rating": 2.0},
        {"id": 7, "movie": "Film G", "rating": 5.0},
        {"id": 8, "movie": "Film H", "rating": 4.0},
    ]

    probs, scores, meta = calibrate_scores(
        candidate_net_scores=candidate_net_scores,
        user_raw_movies=user_raw_movies,
        preferred_method="auto"
    )

    assert len(probs) == len(candidate_net_scores)
    assert len(scores) == len(candidate_net_scores)
    assert meta["is_personalized"] is True
    assert meta["history_count"] == 8
    assert meta["history_tier"] == "sparse"

    # Monotonicity check on output probabilities and match scores
    for i in range(len(probs) - 1):
        assert probs[i] <= probs[i + 1]
        assert scores[i] <= scores[i + 1]

    # Scores within [50, 99]
    assert all(50 <= s <= 99 for s in scores)
