"""
services/fusion_service.py — Training-Free Adaptive Multi-Modal Fusion Engine

Dynamically recalibrates fusion weights (Structured S, Semantic E, Graph G)
based on per-item confidence signals, catalogue-level robust normalization (Median/IQR),
and agreement-aware exploration metrics.
"""

import math
import logging
from typing import Dict, List, Any, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Canonical modality priors: 55% Structured, 30% Semantic, 15% Graph
DEFAULT_PRIORS = np.array([0.55, 0.30, 0.15], dtype=np.float32)

# Safety constraints & thresholds
MIN_CONFIDENCE_FLOOR = 0.05
TOTAL_CONFIDENCE_FALLBACK_THRESHOLD = 0.10
LOW_EVIDENCE_THRESHOLD = 0.35
EXPLORATORY_VARIANCE_THRESHOLD = 0.045  # Disagreement threshold for cross-modal discoveries


def compute_structured_confidence(
    item: Dict[str, Any], 
    craft_data: Optional[Dict[str, Any]] = None
) -> float:
    """
    Calculates structured metadata confidence c_s in [0.05, 1.0] based on
    field completeness and cinematic importance:
    - Director (valid, non-empty): 0.30
    - Genre (specific, not generic 'Cinema'): 0.30 (or 0.12 if generic)
    - Release Year (valid integer > 1888): 0.15
    - Tags / Moods / Themes: 0.15
    - Craft metadata (DoP, Composer, Screenwriter, Cast, Studio): 0.10
    """
    craft = craft_data or item.get("craft") or {}
    score = 0.0

    # 1. Director check (0.30)
    director = str(craft.get("director") or item.get("director") or "").strip().lower()
    if director and director not in ["unknown", "n/a", "none", "", "null"]:
        score += 0.30

    # 2. Genre check (0.30)
    genre = str(item.get("genre") or "").strip().lower()
    if genre and genre not in ["unknown", "n/a", "none", "", "null"]:
        if genre != "cinema":
            score += 0.30
        else:
            score += 0.12  # Partial credit for generic fallback

    # 3. Release Year check (0.15)
    yr_val = item.get("year") or item.get("p_year")
    try:
        yr = int(str(yr_val)[:4])
        if 1888 <= yr <= 2035:
            score += 0.15
    except (ValueError, TypeError):
        pass

    # 4. Tags / Keywords / Atmospheric descriptors (0.15)
    tags = str(item.get("tags") or item.get("frontier_desc") or "").strip()
    if len(tags) >= 5:
        score += 0.15
    elif len(tags) > 0:
        score += 0.08

    # 5. Craft Credits completeness (0.10)
    has_craft = any([
        craft.get("cinematographer"),
        craft.get("composer"),
        craft.get("screenwriter"),
        craft.get("lead_actors"),
        craft.get("studios")
    ])
    if has_craft:
        score += 0.10

    return float(np.clip(score, MIN_CONFIDENCE_FLOOR, 1.0))


def compute_semantic_confidence(
    item: Dict[str, Any], 
    has_valid_embedding: bool = True
) -> float:
    """
    Calculates semantic embedding confidence c_e in [0.05, 1.0] based on
    textual coverage and embedding validity:
    - full synopsis + keywords = 1.0
    - synopsis only = 0.8
    - short description = 0.5
    - title/genre only = 0.2
    """
    if not has_valid_embedding:
        return MIN_CONFIDENCE_FLOOR

    overview = str(item.get("overview") or "").strip()
    tags = str(item.get("tags") or "").strip()
    frontier_desc = str(item.get("frontier_desc") or "").strip()

    ov_len = len(overview)
    tags_len = len(tags)

    if ov_len >= 120 and tags_len >= 5:
        coverage = 1.0
    elif ov_len >= 40:
        coverage = 0.8
    elif ov_len >= 10 or len(frontier_desc) >= 10:
        coverage = 0.5
    else:
        coverage = 0.2

    return float(np.clip(coverage, MIN_CONFIDENCE_FLOOR, 1.0))


def compute_graph_confidence(
    node_degree: int,
    useful_edges: int,
    has_fav_connection: bool,
    user_history_len: int,
    target_edges: int = 5,
    has_diffusion: bool = True
) -> float:
    """
    Calculates graph confidence c_g in [0.05, 1.0] based on neighborhood support,
    direct craft connectivity to user favorites, user history length, and hub suppression:
    c_g = min(1, log(1 + n_useful) / log(1 + n_target)) * c_connectivity * c_user * c_hub
    """
    if useful_edges <= 0:
        return MIN_CONFIDENCE_FLOOR

    # 1. Useful edge support ratio
    log_useful = math.log(1.0 + useful_edges)
    log_target = math.log(1.0 + max(1, target_edges))
    edge_ratio = min(1.0, log_useful / log_target)

    # 2. Connectivity factor
    if has_fav_connection:
        c_connectivity = 1.0
    elif has_diffusion:
        c_connectivity = 0.55
    else:
        c_connectivity = 0.15

    # 3. User history length dampener
    # Users with < 8 watches have sparse graphs, reducing graph trust
    c_user = max(0.30, min(1.0, math.log(1.0 + user_history_len) / math.log(1.0 + 8.0)))

    # 4. Hub dampening penalty for extreme-degree nodes (suppresses popularity leakage)
    if node_degree > 16:
        c_hub = math.sqrt(16.0 / float(node_degree))
    else:
        c_hub = 1.0

    # 5. Penalty for single weak craft connection
    weak_penalty = 0.5 if useful_edges <= 1 else 1.0

    raw_cg = edge_ratio * c_connectivity * c_user * c_hub * weak_penalty
    return float(np.clip(raw_cg, MIN_CONFIDENCE_FLOOR, 1.0))


def renormalize_adaptive_weights(
    c_s: float,
    c_e: float,
    c_g: float,
    priors: np.ndarray = DEFAULT_PRIORS
) -> Tuple[np.ndarray, float]:
    """
    Renormalizes modality weights:
    w_m = (p_m * c_m) / (sum_j p_j * c_j + eps)
    
    Returns:
      (effective_weights, total_confidence)
    """
    c = np.array([c_s, c_e, c_g], dtype=np.float32)
    c = np.clip(c, MIN_CONFIDENCE_FLOOR, 1.0)

    p_dot_c = priors * c
    total_conf = float(np.sum(p_dot_c))

    if total_conf < TOTAL_CONFIDENCE_FALLBACK_THRESHOLD:
        # Fall back to default priors when overall confidence is negligible
        return priors.copy(), total_conf

    weights = p_dot_c / (total_conf + 1e-9)
    # Ensure exact sum to 1.0
    weights = weights / np.sum(weights)
    return weights, total_conf


def catalogue_robust_normalize(
    scores: np.ndarray,
    realm_labels: Optional[np.ndarray] = None
) -> np.ndarray:
    """
    Catalogue-level robust normalization:
    z_m = (x_m - median(x_m)) / (IQR(x_m) + eps)
    Then map through sigmoid sigma(z_m) to put on a bounded [0, 1] scale.
    Computed globally across catalogue pool (or per realm if realm size >= 25).
    """
    scores_arr = np.asarray(scores, dtype=np.float32).copy()
    n_samples = len(scores_arr)
    if n_samples == 0:
        return scores_arr

    norm_scores = np.zeros(n_samples, dtype=np.float32)

    # Check if per-realm normalization is feasible
    can_use_realm = False
    if realm_labels is not None and len(realm_labels) == n_samples:
        unique_labels, counts = np.unique(realm_labels, return_counts=True)
        if all(cnt >= 25 for cnt in counts):
            can_use_realm = True

    if can_use_realm:
        for r_id in np.unique(realm_labels):
            mask = (realm_labels == r_id)
            sub_scores = scores_arr[mask]
            q75, q25 = np.percentile(sub_scores, [75, 25])
            iqr = max(float(q75 - q25), 1e-4)
            med = float(np.median(sub_scores))
            z = np.clip((sub_scores - med) / iqr, -35.0, 35.0)
            norm_scores[mask] = 1.0 / (1.0 + np.exp(-z))
    else:
        q75, q25 = np.percentile(scores_arr, [75, 25])
        iqr = max(float(q75 - q25), 1e-4)
        med = float(np.median(scores_arr))
        z = np.clip((scores_arr - med) / iqr, -35.0, 35.0)
        norm_scores = 1.0 / (1.0 + np.exp(-z))

    return norm_scores


def compute_cross_modal_agreement(
    s_norm: float,
    e_norm: float,
    g_norm: float
) -> Dict[str, Any]:
    """
    Evaluates modality agreement:
    A_i = 1 - Var(S_i, E_i, G_i) / 0.125
    When disagreement is high, marks item as exploratory.
    """
    vals = np.array([s_norm, e_norm, g_norm], dtype=np.float32)
    mu = float(np.mean(vals))
    variance = float(np.mean((vals - mu) ** 2))

    # Agreement score in [0.0, 1.0]
    # Maximum possible variance of 3 numbers in [0, 1] is 0.25, typical divergence is <= 0.125
    agreement = max(0.0, min(1.0, 1.0 - (variance / 0.125)))
    is_exploratory = bool(variance > EXPLORATORY_VARIANCE_THRESHOLD)

    return {
        "agreement": round(agreement, 3),
        "variance": round(variance, 4),
        "is_exploratory": is_exploratory
    }


def execute_adaptive_fusion(
    items: List[Dict[str, Any]],
    raw_s_scores: np.ndarray,
    raw_e_scores: np.ndarray,
    raw_g_scores: np.ndarray,
    struct_norm: np.ndarray,
    semantic_norm: np.ndarray,
    graph_embs: np.ndarray,
    graph_node_stats: Dict[str, Dict[str, Any]],
    crafts_by_key: Dict[str, Dict[str, Any]],
    user_history_len: int,
    priors: np.ndarray = DEFAULT_PRIORS,
    realm_labels: Optional[np.ndarray] = None
) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, Any]]]:
    """
    End-to-end adaptive fusion pipeline:
    1. Robustly normalizes raw modality similarities S, E, G.
    2. Computes c_s, c_e, c_g for each item.
    3. Renormalizes weights w_s, w_e, w_g per item.
    4. Computes fused affinity score = w_s * S_norm + w_e * E_norm + w_g * G_norm.
    5. Computes cross-modal agreement and sets exploratory / low-evidence flags.
    6. Constructs adaptively weighted latent matrix H with row-wise sqrt(w_m) block scaling.

    Returns:
      (fused_scores, hybrid_matrix, diagnostics_list)
    """
    n_samples = len(items)
    if n_samples == 0:
        return np.zeros(0, dtype=np.float32), np.zeros((0, 79 + 384 + 64), dtype=np.float32), []

    # Step 1: Catalogue-Level Robust Normalization
    s_tilde = catalogue_robust_normalize(raw_s_scores, realm_labels)
    e_tilde = catalogue_robust_normalize(raw_e_scores, realm_labels)
    g_tilde = catalogue_robust_normalize(raw_g_scores, realm_labels)

    fused_scores = np.zeros(n_samples, dtype=np.float32)
    dim_s = struct_norm.shape[1] if struct_norm.ndim > 1 else 0
    dim_e = semantic_norm.shape[1] if semantic_norm.ndim > 1 else 0
    dim_g = graph_embs.shape[1] if graph_embs.ndim > 1 else 0
    total_dim = dim_s + dim_e + dim_g

    hybrid_matrix = np.zeros((n_samples, total_dim), dtype=np.float32)
    diagnostics = []

    for idx in range(n_samples):
        item = items[idx]
        item_id = str(item.get("id", idx))

        # Retrieve craft data
        from services.craft_service import _normalize_key
        item_key = _normalize_key(item.get("title") or item.get("movie") or "", item.get("p_year") or item.get("year"))
        craft = crafts_by_key.get(item_key, {})

        # 1. Structured confidence
        c_s = compute_structured_confidence(item, craft_data=craft)

        # 2. Semantic confidence
        has_embed = True
        if dim_e > 0:
            e_vec = semantic_norm[idx]
            has_embed = bool(np.linalg.norm(e_vec) > 1e-4)
        c_e = compute_semantic_confidence(item, has_valid_embedding=has_embed)

        # 3. Graph confidence
        g_stat = graph_node_stats.get(item_id, {})
        deg = g_stat.get("degree", 0)
        useful_e = g_stat.get("useful_edges", 0)
        has_fav = g_stat.get("has_fav_connection", False)
        has_diff = g_stat.get("has_diffusion", bool(raw_g_scores[idx] > 0.05))

        c_g = compute_graph_confidence(
            node_degree=deg,
            useful_edges=useful_e,
            has_fav_connection=has_fav,
            user_history_len=user_history_len,
            has_diffusion=has_diff
        )

        # 4. Weight renormalization
        weights, total_conf = renormalize_adaptive_weights(c_s, c_e, c_g, priors=priors)
        w_s, w_e, w_g = float(weights[0]), float(weights[1]), float(weights[2])

        # 5. Adaptive score fusion
        s_val = float(s_tilde[idx])
        e_val = float(e_tilde[idx])
        g_val = float(g_tilde[idx])
        score_val = w_s * s_val + w_e * e_val + w_g * g_val
        fused_scores[idx] = score_val

        # 6. Agreement & Exploration metrics
        agr_info = compute_cross_modal_agreement(s_val, e_val, g_val)
        low_evidence = bool(total_conf < LOW_EVIDENCE_THRESHOLD)

        diag = {
            "confidence": {
                "structured": round(c_s, 3),
                "semantic": round(c_e, 3),
                "graph": round(c_g, 3),
                "total": round(total_conf, 3)
            },
            "effective_weights": {
                "structured": round(w_s, 3),
                "semantic": round(w_e, 3),
                "graph": round(w_g, 3)
            },
            "agreement_score": agr_info["agreement"],
            "variance": agr_info["variance"],
            "is_exploratory": agr_info["is_exploratory"],
            "low_evidence": low_evidence,
            "normalized_modalities": {
                "structured": round(s_val, 3),
                "semantic": round(e_val, 3),
                "graph": round(g_val, 3)
            }
        }
        diagnostics.append(diag)

        # 7. Row-wise sqrt(w_m) scaled latent hybrid matrix
        # Ensures dot product in ℝ^(D_s+D_e+D_g) naturally equals the adaptively weighted linear sum!
        s_part = math.sqrt(w_s) * struct_norm[idx] if dim_s > 0 else np.zeros(0, dtype=np.float32)
        e_part = math.sqrt(w_e) * semantic_norm[idx] if dim_e > 0 else np.zeros(0, dtype=np.float32)
        g_part = math.sqrt(w_g) * graph_embs[idx] if dim_g > 0 else np.zeros(0, dtype=np.float32)

        row_vec = np.concatenate([s_part, e_part, g_part])
        row_norm = np.linalg.norm(row_vec) + 1e-9
        hybrid_matrix[idx] = row_vec / row_norm

    return fused_scores, hybrid_matrix, diagnostics
