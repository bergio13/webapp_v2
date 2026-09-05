"""
services/quality_service.py — Bayesian Quality Prior & Acclaim Calibration Engine

Calculates a Bayesian quality estimate incorporating item rating and vote count:
    Q_i = (v_i / (v_i + m)) * R_i + (m / (v_i + m)) * C

Where:
- R_i: item average consensus rating (TMDB vote_average or curated rating_score in [1.0, 10.0])
- v_i: vote count (TMDB vote_count or calibrated canon proxy)
- C: catalogue mean rating across candidate pool
- m: confidence threshold (minimum votes to trust item rating over catalogue prior)

Applies the quality prior additively (or in log-odds space) to candidate affinity:
    net_score_i = max(0.0, s_vetoed_i + alpha * v_fac_i * ((Q_i - C) / 10.0))

Multiplication is avoided to prevent heteroskedastic amplification of score variance.
The prior weight alpha is calibrated to be gentle enough that a popular film never outranks
a strong personal match.
"""

import math
import logging
from typing import Dict, List, Any, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Canonical domain defaults
DEFAULT_CATALOGUE_MEAN = 6.9
DEFAULT_CONFIDENCE_THRESHOLD = 250.0  # m
DEFAULT_QUALITY_WEIGHT = 0.08         # alpha for additive space
DEFAULT_LOG_ODDS_WEIGHT = 0.18        # gamma for log-odds space
CANON_CONSENSUS_VOTE_PROXY = 2000     # Proxy vote count for established curated masterworks


def compute_bayesian_quality_score(
    r_i: Optional[float],
    v_i: Optional[int],
    c: float = DEFAULT_CATALOGUE_MEAN,
    m: float = DEFAULT_CONFIDENCE_THRESHOLD
) -> float:
    """
    Computes Bayesian shrinkage quality estimate:
        Q_i = (v_i / (v_i + m)) * R_i + (m / (v_i + m)) * C

    Parameters:
    - r_i: item consensus rating in [1.0, 10.0]
    - v_i: item vote count >= 0
    - c: catalogue baseline mean
    - m: confidence threshold > 0

    Returns:
    - Q_i bounded in [1.0, 10.0]
    """
    try:
        r_val = float(r_i) if r_i is not None else None
    except (ValueError, TypeError):
        r_val = None

    try:
        v_val = max(0.0, float(v_i)) if v_i is not None else 0.0
    except (ValueError, TypeError):
        v_val = 0.0

    m_val = max(1.0, float(m))
    try:
        c_val = float(c)
    except (ValueError, TypeError):
        c_val = DEFAULT_CATALOGUE_MEAN
    c_val = float(np.clip(c_val, 1.0, 10.0))

    # If rating is missing or vote count is zero, shrink entirely to catalogue mean C
    if r_val is None or r_val <= 0.0 or v_val <= 0.0:
        return round(c_val, 3)

    r_clamped = float(np.clip(r_val, 1.0, 10.0))

    # Bayesian shrinkage formula
    weight_item = v_val / (v_val + m_val)
    weight_prior = m_val / (v_val + m_val)

    q_i = weight_item * r_clamped + weight_prior * c_val
    return round(float(np.clip(q_i, 1.0, 10.0)), 3)


def estimate_catalogue_mean(
    items: List[Dict[str, Any]],
    fallback_c: float = DEFAULT_CATALOGUE_MEAN
) -> float:
    """
    Estimates the empirical catalogue mean C across candidate items with valid ratings.
    Uses trimmed mean (excluding bottom/top 5%) if sufficient items exist.
    """
    valid_ratings = []
    for it in items:
        r = it.get("vote_average") or it.get("rating_score")
        if r is not None:
            try:
                rf = float(r)
                if 1.0 <= rf <= 10.0:
                    valid_ratings.append(rf)
            except (ValueError, TypeError):
                pass

    if len(valid_ratings) < 6:
        return float(fallback_c)

    arr = np.array(valid_ratings, dtype=np.float32)
    # Trim extreme 5% outliers on both tails
    low_p, high_p = np.percentile(arr, [5, 95])
    trimmed = arr[(arr >= low_p) & (arr <= high_p)]

    if len(trimmed) > 0:
        mean_c = float(np.mean(trimmed))
    else:
        mean_c = float(np.mean(arr))

    # Bound mean in reasonable cinematic range [6.0, 7.8]
    return round(float(np.clip(mean_c, 6.0, 7.8)), 3)


def apply_quality_prior_additive(
    base_score: float,
    q_i: float,
    c: float = DEFAULT_CATALOGUE_MEAN,
    alpha: float = DEFAULT_QUALITY_WEIGHT,
    veto_factor: float = 1.0
) -> Tuple[float, float]:
    """
    Applies the Bayesian quality prior additively:
        delta_i = (Q_i - C) / 10.0
        score_adj = max(0.0, base_score + alpha * veto_factor * delta_i)

    Parameters:
    - base_score: personalized net affinity in [0, 1]
    - q_i: Bayesian quality score in [1, 10]
    - c: catalogue baseline mean
    - alpha: prior weight (e.g. 0.08)
    - veto_factor: gate factor in [0, 1]; zero for vetoed items

    Returns:
    - (adjusted_score, delta)
    """
    delta_i = (q_i - c) / 10.0
    v_fac = float(np.clip(veto_factor, 0.0, 1.0))
    shift = float(alpha * v_fac * delta_i)
    adjusted = max(0.0, float(base_score + shift))
    return round(adjusted, 4), round(shift, 4)


def apply_quality_prior_log_odds(
    base_prob: float,
    q_i: float,
    c: float = DEFAULT_CATALOGUE_MEAN,
    gamma: float = DEFAULT_LOG_ODDS_WEIGHT,
    veto_factor: float = 1.0,
    sigma_c: float = 1.2
) -> Tuple[float, float]:
    """
    Applies the Bayesian quality prior in log-odds (logit) space:
        logit = log(p / (1 - p))
        logit_shift = gamma * veto_factor * ((Q_i - C) / sigma_C)
        updated_prob = 1 / (1 + exp(-(logit + logit_shift)))

    Parameters:
    - base_prob: calibrated probability in (0, 1)
    - q_i: Bayesian quality score in [1, 10]
    - c: catalogue baseline mean
    - gamma: log-odds weight (default 0.18)
    - veto_factor: gate factor in [0, 1]
    - sigma_c: standard deviation of quality scores (default 1.2)

    Returns:
    - (updated_prob, logit_shift)
    """
    p_clamped = float(np.clip(base_prob, 0.01, 0.99))
    logit = math.log(p_clamped / (1.0 - p_clamped))

    v_fac = float(np.clip(veto_factor, 0.0, 1.0))
    sigma = max(0.5, float(sigma_c))
    logit_shift = float(gamma * v_fac * ((q_i - c) / sigma))

    new_logit = float(np.clip(logit + logit_shift, -15.0, 15.0))
    updated_prob = 1.0 / (1.0 + math.exp(-new_logit))

    return round(float(updated_prob), 4), round(logit_shift, 4)


def batch_apply_quality_prior(
    pool: List[Dict[str, Any]],
    candidate_vetoed_scores: np.ndarray,
    veto_factors: np.ndarray,
    m: float = DEFAULT_CONFIDENCE_THRESHOLD,
    alpha: float = DEFAULT_QUALITY_WEIGHT,
    mode: str = "additive",
    default_c: float = DEFAULT_CATALOGUE_MEAN
) -> Tuple[np.ndarray, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Vectorized execution of Bayesian quality prior across a candidate pool:
    1. Determines empirical catalogue mean C across candidate items.
    2. Computes Q_i for unwatched candidates using vote-count Bayesian shrinkage.
    3. Modulates net score additively (or in log-odds space) scaled by veto factor.
    4. Generates per-item diagnostics and telemetry summary metadata.

    Returns:
    - adjusted_scores: np.ndarray of shape (N,)
    - quality_diagnostics: list of dicts with per-item prior details
    - summary_meta: summary telemetry dict
    """
    n_samples = len(pool)
    if n_samples == 0:
        return np.zeros(0, dtype=np.float32), [], {}

    scores_arr = np.asarray(candidate_vetoed_scores, dtype=np.float32)
    veto_arr = np.asarray(veto_factors, dtype=np.float32)

    # 1. Estimate catalogue mean C from candidate pool
    cat_mean = estimate_catalogue_mean(pool, fallback_c=default_c)

    adjusted_scores = np.zeros(n_samples, dtype=np.float32)
    diagnostics: List[Dict[str, Any]] = []

    q_scores = []
    deltas = []

    for idx in range(n_samples):
        item = pool[idx]
        base_s = float(scores_arr[idx])
        v_fac = float(veto_arr[idx])

        # Watched items are anchored by actual user rating and do not receive acclaim prior
        if item.get("is_watched"):
            adjusted_scores[idx] = base_s
            diagnostics.append({
                "is_applicable": False,
                "reason": "watched_user_item",
                "vote_average": None,
                "vote_count": None,
                "bayesian_quality": None,
                "catalogue_mean": cat_mean,
                "delta": 0.0
            })
            continue

        # Extract vote_average (or curated rating_score)
        raw_r = item.get("vote_average") or item.get("rating_score")
        try:
            r_num = float(raw_r) if raw_r is not None else None
        except (ValueError, TypeError):
            r_num = None

        # Extract vote_count
        raw_v = item.get("vote_count")
        try:
            v_num = int(raw_v) if raw_v is not None else None
        except (ValueError, TypeError):
            v_num = None

        # Established curated masterworks receive high-confidence proxy count if unpopulated
        is_curated = (
            item.get("source") in ["cinephile_corpus", "landmark_canon", "auteur_canon"] or
            bool(item.get("canon_tier"))
        )
        if (v_num is None or v_num <= 0) and is_curated and r_num and r_num >= 7.5:
            v_num = CANON_CONSENSUS_VOTE_PROXY

        # Compute Bayesian estimate Q_i
        q_i = compute_bayesian_quality_score(r_i=r_num, v_i=v_num, c=cat_mean, m=m)
        q_scores.append(q_i)

        if mode == "additive":
            adj_s, delta = apply_quality_prior_additive(
                base_score=base_s,
                q_i=q_i,
                c=cat_mean,
                alpha=alpha,
                veto_factor=v_fac
            )
        else:
            adj_s, delta = apply_quality_prior_log_odds(
                base_prob=base_s,
                q_i=q_i,
                c=cat_mean,
                gamma=DEFAULT_LOG_ODDS_WEIGHT,
                veto_factor=v_fac
            )

        adjusted_scores[idx] = adj_s
        deltas.append(delta)

        diagnostics.append({
            "is_applicable": True,
            "vote_average": round(r_num, 1) if r_num is not None else None,
            "vote_count": v_num,
            "bayesian_quality": q_i,
            "catalogue_mean": cat_mean,
            "confidence_threshold": m,
            "delta": delta,
            "mode": mode,
            "is_curated_proxy": bool(is_curated and (raw_v is None or raw_v <= 0))
        })

    summary_meta = {
        "catalogue_mean": cat_mean,
        "confidence_threshold": m,
        "prior_weight": alpha,
        "mode": mode,
        "evaluated_candidates": len(q_scores),
        "mean_bayesian_quality": round(float(np.mean(q_scores)), 3) if q_scores else cat_mean,
        "mean_quality_delta": round(float(np.mean(deltas)), 4) if deltas else 0.0,
        "max_quality_boost": round(float(np.max(deltas)), 4) if deltas else 0.0,
        "max_quality_penalty": round(float(np.min(deltas)), 4) if deltas else 0.0
    }

    return adjusted_scores, diagnostics, summary_meta
