"""
services/calibration_service.py — Probabilistic Calibration & Match Score Engine

Calibrates raw affinity / recommendation scores into true probabilistic estimates:
    P(positive interaction | raw_score)

Provides:
1. Platt Scaling (logistic calibration with strict monotonicity constraints).
2. Isotonic Regression (non-parametric monotonic step calibration).
3. Empirical Bayes Prior Shrinkage (stabilizes small user-history cold-start estimates).
4. Stratified Calibration Evaluation across:
   - User-History Size Tiers (sparse <10, moderate 10-34, rich 35+)
   - Catalogue Segments (Macro Archetype Realms, popularity tiers)
5. Evaluation metrics: Brier Score, Expected Calibration Error (ECE), Reliability Bins.
6. Honest Match Score mapping [50, 99] replacing uncalibrated percentage heuristics.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Tuple, Optional, Union
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

logger = logging.getLogger(__name__)

# Default global prior for positive interaction in catalogue (P(rating >= 4.0))
DEFAULT_GLOBAL_POSITIVE_PRIOR = 0.58

# Minimum samples needed for pure personalized calibration vs prior shrinkage
MIN_SAMPLES_FOR_PLATT = 6
MIN_SAMPLES_FOR_ISOTONIC = 30
BAYES_SHRINKAGE_PSEUDO_COUNT = 12.0  # N_0 shrinkage strength


@dataclass
class CalibrationMetrics:
    """Evaluation metrics for calibrated probabilities against observed ground truth."""
    brier_score: float
    brier_skill_score: float
    expected_calibration_error: float
    sample_count: int
    positive_rate: float
    mean_predicted_prob: float
    reliability_bins: List[Dict[str, float]] = field(default_factory=list)


@dataclass
class StratifiedEvaluationReport:
    """Full evaluation report stratified by history size and catalogue segments."""
    overall_metrics: CalibrationMetrics
    by_history_tier: Dict[str, CalibrationMetrics]
    by_catalogue_segment: Dict[str, CalibrationMetrics]
    uncalibrated_brier: float
    brier_reduction_pct: float


def classify_interaction_label(rating: Optional[float], is_negative_or_abandoned: bool = False) -> Optional[int]:
    """
    Classifies a user interaction into a binary positive label Y in {0, 1}:
    - Y = 1: user rating >= 4.0
    - Y = 0: user rating <= 2.5, or item was abandoned/rejected
    - Neutral ratings (3.0, 3.5) return None (held out from hard binary calibration fit).
    """
    if is_negative_or_abandoned:
        return 0
    if rating is None:
        return None
    try:
        r = float(rating)
    except (ValueError, TypeError):
        return None

    if r >= 4.0:
        return 1
    elif r <= 2.5:
        return 0
    return None


class PlattCalibrator:
    """
    Parametric Platt Scaling (Logistic Calibration):
        P(Y = 1 | s) = 1 / (1 + exp(-(A * s + B)))
    Enforces A >= 0.05 so ranking order is strictly monotonic with raw scores.
    """

    def __init__(self, regularized: bool = True, c_val: float = 1.0):
        self.a: float = 3.5
        self.b: float = -1.8
        self.is_fitted: bool = False
        self.regularized = regularized
        self.c_val = c_val

    def fit(self, raw_scores: np.ndarray, y_true: np.ndarray) -> "PlattCalibrator":
        """Fits logistic curve to raw scores and binary labels."""
        s = np.asarray(raw_scores, dtype=np.float64).flatten()
        y = np.asarray(y_true, dtype=np.int32).flatten()

        if len(s) < MIN_SAMPLES_FOR_PLATT or len(np.unique(y)) < 2:
            # Fallback to reasonable cinematic domain defaults
            pos_rate = float(np.mean(y)) if len(y) > 0 else DEFAULT_GLOBAL_POSITIVE_PRIOR
            pos_rate = np.clip(pos_rate, 0.20, 0.85)
            # Center sigmoid around median score
            med_s = float(np.median(s)) if len(s) > 0 else 0.5
            self.a = 3.5
            self.b = -self.a * med_s + math.log(pos_rate / (1.0 - pos_rate + 1e-9))
            self.is_fitted = True
            return self

        # Fit using L2-regularized logistic regression
        clf = LogisticRegression(C=self.c_val, max_iter=300, solver="lbfgs")
        clf.fit(s.reshape(-1, 1), y)

        coef = float(clf.coef_[0][0])
        intercept = float(clf.intercept_[0])

        # Enforce monotonicity: higher raw affinity must never decrease probability of enjoyment
        if coef < 0.05:
            coef = 1.0  # gentle positive slope default
            # re-estimate intercept to match empirical positive rate
            pos_rate = np.clip(float(np.mean(y)), 0.15, 0.85)
            intercept = -coef * float(np.median(s)) + math.log(pos_rate / (1.0 - pos_rate + 1e-9))

        self.a = coef
        self.b = intercept
        self.is_fitted = True
        return self

    def predict_proba(self, raw_scores: np.ndarray) -> np.ndarray:
        """Transforms raw affinity scores to calibrated probabilities in (0, 1)."""
        s = np.asarray(raw_scores, dtype=np.float64)
        logits = self.a * s + self.b
        # Numerically stable sigmoid
        logits = np.clip(logits, -25.0, 25.0)
        return (1.0 / (1.0 + np.exp(-logits))).astype(np.float32)


class IsotonicCalibrator:
    """
    Non-parametric Isotonic Regression calibrator.
    Guarantees monotonicity: P(Y=1 | s_i) <= P(Y=1 | s_j) for s_i <= s_j.
    """

    def __init__(self, y_min: float = 0.02, y_max: float = 0.98):
        self.y_min = y_min
        self.y_max = y_max
        self.ir = IsotonicRegression(y_min=y_min, y_max=y_max, out_of_bounds="clip", increasing=True)
        self.is_fitted = False
        self.fallback_platt: Optional[PlattCalibrator] = None

    def fit(self, raw_scores: np.ndarray, y_true: np.ndarray) -> "IsotonicCalibrator":
        s = np.asarray(raw_scores, dtype=np.float64).flatten()
        y = np.asarray(y_true, dtype=np.float64).flatten()

        if len(s) < MIN_SAMPLES_FOR_ISOTONIC or len(np.unique(y)) < 2:
            # When samples are sparse, isotonic regression yields step plateaus.
            # Smoothly fallback to Platt scaling
            self.fallback_platt = PlattCalibrator().fit(s, y)
            self.is_fitted = True
            return self

        try:
            self.ir.fit(s, y)
            self.is_fitted = True
            self.fallback_platt = None
        except Exception as e:
            logger.warning(f"Isotonic regression fit failed: {e}. Falling back to Platt.")
            self.fallback_platt = PlattCalibrator().fit(s, y)
            self.is_fitted = True

        return self

    def predict_proba(self, raw_scores: np.ndarray) -> np.ndarray:
        if self.fallback_platt is not None:
            return self.fallback_platt.predict_proba(raw_scores)

        s = np.asarray(raw_scores, dtype=np.float64)
        probs = self.ir.predict(s)
        return np.clip(probs, self.y_min, self.y_max).astype(np.float32)


def apply_empirical_bayes_shrinkage(
    probs: np.ndarray,
    n_user_history: int,
    segment_prior: float = DEFAULT_GLOBAL_POSITIVE_PRIOR,
    pseudo_count: float = BAYES_SHRINKAGE_PSEUDO_COUNT
) -> np.ndarray:
    """
    Stabilizes calibrated probabilities on small user histories by shrinking
    towards the segment prior p_0:
        P_shrunk = (N / (N + N_0)) * P_cal + (N_0 / (N + N_0)) * p_0
    """
    probs_arr = np.asarray(probs, dtype=np.float32)
    n = max(0, int(n_user_history))
    shrink_weight = float(n / (n + pseudo_count))
    shrunk = shrink_weight * probs_arr + (1.0 - shrink_weight) * segment_prior
    return np.clip(shrunk, 0.01, 0.99).astype(np.float32)


def compute_brier_score(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Computes the Brier score: mean squared error of predicted probabilities."""
    y = np.asarray(y_true, dtype=np.float64).flatten()
    p = np.asarray(y_prob, dtype=np.float64).flatten()
    if len(y) == 0:
        return 0.0
    return float(np.mean((p - y) ** 2))


def compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 5) -> Tuple[float, List[Dict[str, float]]]:
    """
    Computes Expected Calibration Error (ECE) and reliability bin statistics.
    Divides prediction space into n_bins equal-width bins.
    """
    y = np.asarray(y_true, dtype=np.float64).flatten()
    p = np.asarray(y_prob, dtype=np.float64).flatten()
    n = len(y)
    if n == 0:
        return 0.0, []

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    bins_info = []

    for i in range(n_bins):
        low, high = bin_edges[i], bin_edges[i + 1]
        # Include high boundary on last bin
        if i == n_bins - 1:
            mask = (p >= low) & (p <= high)
        else:
            mask = (p >= low) & (p < high)

        bin_count = int(np.sum(mask))
        if bin_count > 0:
            bin_acc = float(np.mean(y[mask]))
            bin_conf = float(np.mean(p[mask]))
            bin_error = abs(bin_acc - bin_conf)
            ece += (bin_count / n) * bin_error
            bins_info.append({
                "bin_index": i,
                "range_min": round(float(low), 3),
                "range_max": round(float(high), 3),
                "count": bin_count,
                "accuracy": round(bin_acc, 4),
                "confidence": round(bin_conf, 4),
                "gap": round(bin_error, 4)
            })
        else:
            bins_info.append({
                "bin_index": i,
                "range_min": round(float(low), 3),
                "range_max": round(float(high), 3),
                "count": 0,
                "accuracy": 0.0,
                "confidence": round((low + high) / 2.0, 3),
                "gap": 0.0
            })

    return float(ece), bins_info


def evaluate_calibration(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 5) -> CalibrationMetrics:
    """Evaluates calibration quality against ground truth."""
    y = np.asarray(y_true, dtype=np.float64).flatten()
    p = np.asarray(y_prob, dtype=np.float64).flatten()
    n = len(y)
    if n == 0:
        return CalibrationMetrics(0.0, 0.0, 0.0, 0, 0.0, 0.0, [])

    brier = compute_brier_score(y, p)
    base_rate = float(np.mean(y))
    brier_ref = base_rate * (1.0 - base_rate)
    brier_skill = 1.0 - (brier / (brier_ref + 1e-9)) if brier_ref > 1e-6 else 0.0
    ece, bins_info = compute_ece(y, p, n_bins=n_bins)

    return CalibrationMetrics(
        brier_score=round(brier, 4),
        brier_skill_score=round(brier_skill, 4),
        expected_calibration_error=round(ece, 4),
        sample_count=n,
        positive_rate=round(base_rate, 4),
        mean_predicted_prob=round(float(np.mean(p)), 4),
        reliability_bins=bins_info
    )


def classify_history_tier(history_len: int) -> str:
    """Classifies user history into volume tiers."""
    if history_len < 10:
        return "sparse"
    elif history_len < 35:
        return "moderate"
    return "rich"


def map_to_match_score(
    calibrated_prob: float,
    raw_net: float,
    min_score: int = 50,
    max_score: int = 99
) -> int:
    """
    Honest, non-deceptive Match Score mapping:
    Combines calibrated probability (70% weight) with raw relative affinity ranking (30% weight)
    into a clean integer index [50, 99].
    Crucially, this is labeled as 'Match Score' rather than a percentage.
    """
    prob = float(np.clip(calibrated_prob, 0.0, 1.0))
    net = float(np.clip(raw_net, 0.0, 1.0))

    # Base score is anchored by calibrated probability:
    # prob = 0.50 -> ~74 score
    # prob = 0.90 -> ~93 score
    # prob = 0.20 -> ~56 score
    score_from_prob = 50.0 + 49.0 * prob
    score_from_net = 50.0 + 49.0 * net

    blended = 0.70 * score_from_prob + 0.30 * score_from_net
    return int(np.clip(round(blended), min_score, max_score))


def generate_stratified_calibration_report(
    eval_records: List[Dict[str, Any]],
    n_bins: int = 5
) -> StratifiedEvaluationReport:
    """
    Generates a full stratified calibration evaluation report:
    Evaluates Brier score and ECE broken down by:
    1. Overall
    2. User-history tier (sparse, moderate, rich)
    3. Catalogue segment (Macro Realm, e.g. Sci-Fi, Arthouse, Animation)
    Also computes the uncalibrated linear heuristic baseline (70 + 29*net)/100 for comparison.
    """
    if not eval_records:
        empty = CalibrationMetrics(0.0, 0.0, 0.0, 0, 0.0, 0.0, [])
        return StratifiedEvaluationReport(empty, {}, {}, 0.0, 0.0)

    y_all = []
    p_all = []
    p_uncal_all = []

    history_groups: Dict[str, Tuple[List[int], List[float]]] = {"sparse": ([], []), "moderate": ([], []), "rich": ([], [])}
    segment_groups: Dict[str, Tuple[List[int], List[float]]] = {}

    for rec in eval_records:
        y = int(rec["y_true"])
        p = float(rec["calibrated_prob"])
        raw_net = float(rec.get("raw_net", 0.5))
        # Uncalibrated linear heuristic clamped to [0.55, 0.99]
        p_uncal = np.clip((70.0 + 29.0 * raw_net) / 100.0, 0.55, 0.99)

        y_all.append(y)
        p_all.append(p)
        p_uncal_all.append(p_uncal)

        h_tier = str(rec.get("history_tier") or classify_history_tier(rec.get("history_len", 20)))
        if h_tier not in history_groups:
            history_groups[h_tier] = ([], [])
        history_groups[h_tier][0].append(y)
        history_groups[h_tier][1].append(p)

        seg = str(rec.get("catalogue_segment") or "General")
        if seg not in segment_groups:
            segment_groups[seg] = ([], [])
        segment_groups[seg][0].append(y)
        segment_groups[seg][1].append(p)

    overall_metrics = evaluate_calibration(np.array(y_all), np.array(p_all), n_bins=n_bins)
    uncal_brier = compute_brier_score(np.array(y_all), np.array(p_uncal_all))

    brier_reduction = (uncal_brier - overall_metrics.brier_score) / (uncal_brier + 1e-9) * 100.0

    by_history: Dict[str, CalibrationMetrics] = {}
    for tier, (ys, ps) in history_groups.items():
        if len(ys) > 0:
            by_history[tier] = evaluate_calibration(np.array(ys), np.array(ps), n_bins=n_bins)

    by_segment: Dict[str, CalibrationMetrics] = {}
    for seg, (ys, ps) in segment_groups.items():
        if len(ys) > 0:
            by_segment[seg] = evaluate_calibration(np.array(ys), np.array(ps), n_bins=n_bins)

    return StratifiedEvaluationReport(
        overall_metrics=overall_metrics,
        by_history_tier=by_history,
        by_catalogue_segment=by_segment,
        uncalibrated_brier=round(uncal_brier, 4),
        brier_reduction_pct=round(brier_reduction, 2)
    )


def calibrate_scores(
    candidate_net_scores: np.ndarray,
    user_raw_movies: Optional[List[Dict[str, Any]]] = None,
    pool_items: Optional[List[Dict[str, Any]]] = None,
    preferred_method: str = "auto"
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """
    End-to-end score calibration pipeline:
    1. Extracts ground truth interaction labels from user history.
    2. Determines history tier (sparse, moderate, rich).
    3. Selects optimal calibration algorithm (Platt vs Isotonic).
    4. Fits calibrator with empirical Bayes prior shrinkage.
    5. Transforms candidate raw net scores to calibrated probabilities in [0.05, 0.98].
    6. Maps calibrated probabilities and relative net scores to honest Match Scores in [50, 99].
    7. Returns (calibrated_probs, match_scores, calibration_meta).
    """
    n_samples = len(candidate_net_scores)
    if n_samples == 0:
        return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.int32), {}

    net_arr = np.asarray(candidate_net_scores, dtype=np.float32)
    user_history_len = len(user_raw_movies) if user_raw_movies else 0
    history_tier = classify_history_tier(user_history_len)

    # Extract ground truth history pairs
    hist_scores = []
    hist_labels = []

    if user_raw_movies:
        for m in user_raw_movies:
            r = m.get("rating")
            is_neg = bool(m.get("is_abandoned") or m.get("disliked"))
            lbl = classify_interaction_label(r, is_negative_or_abandoned=is_neg)
            if lbl is not None:
                # Estimate proxy score from rating (ratings 1-5 map to ~ [0.1, 0.95])
                proxy_score = float(np.clip((float(r or 3.0) - 1.0) / 4.0, 0.0, 1.0))
                hist_scores.append(proxy_score)
                hist_labels.append(lbl)

    # Determine method
    n_labels = len(hist_labels)
    if preferred_method == "isotonic" or (preferred_method == "auto" and n_labels >= MIN_SAMPLES_FOR_ISOTONIC):
        calibrator_type = "isotonic"
        calibrator = IsotonicCalibrator()
    else:
        calibrator_type = "platt"
        calibrator = PlattCalibrator()

    # Fit
    if n_labels >= MIN_SAMPLES_FOR_PLATT and len(np.unique(hist_labels)) >= 2:
        calibrator.fit(np.array(hist_scores), np.array(hist_labels))
        is_personalized = True
    else:
        # Cold start / sparse fallback: default cinematic calibrated sigmoid
        calibrator.fit(np.array([0.2, 0.4, 0.6, 0.8]), np.array([0, 0, 1, 1]))
        is_personalized = False

    raw_probs = calibrator.predict_proba(net_arr)

    # Apply Empirical Bayes Shrinkage based on user history length
    segment_prior = float(np.mean(hist_labels)) if n_labels >= 4 else DEFAULT_GLOBAL_POSITIVE_PRIOR
    calibrated_probs = apply_empirical_bayes_shrinkage(
        probs=raw_probs,
        n_user_history=user_history_len,
        segment_prior=segment_prior,
        pseudo_count=BAYES_SHRINKAGE_PSEUDO_COUNT
    )

    # Map to honest Match Scores [50, 99]
    match_scores = np.zeros(n_samples, dtype=np.int32)
    for i in range(n_samples):
        match_scores[i] = map_to_match_score(calibrated_probs[i], net_arr[i])

    meta = {
        "calibrator_type": calibrator_type,
        "is_personalized": is_personalized,
        "history_tier": history_tier,
        "history_count": user_history_len,
        "training_samples": n_labels,
        "segment_prior": round(segment_prior, 3),
        "mean_calibrated_prob": round(float(np.mean(calibrated_probs)), 3)
    }

    return calibrated_probs, match_scores, meta
