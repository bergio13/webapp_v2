"""
services/positive_mode_service.py — Multi-Mode Positive Preference Engine with Soft Mode Aggregation

Models user positive tastes as multiple distinct affinity modes (clusters)
and aggregates candidate similarity using a temperature-controlled soft maximum:
    pos(i) = tau * log sum_k [ pi_k * exp(s_ik / tau) ]

Where:
- pi_k: normalized weight of taste mode k, combining taste mass (ratings, rewatches),
        temporal recency (viewing dates), and internal cluster cohesion.
- tau: temperature parameter controlling interpolation between hard maximum (tau -> 0)
       and weighted average (tau -> inf).
- s_ik: cosine similarity between candidate item i and positive mode centroid k.

Uses the numerically stable Log-Sum-Exp formulation to prevent overflow/underflow:
    pos(i) = m_i + tau * log sum_k [ pi_k * exp((s_ik - m_i) / tau) ]
where m_i = max_k s_ik.
"""

import math
import logging
from datetime import date, datetime
from dataclasses import dataclass, field
from typing import Dict, List, Any, Tuple, Optional, Set
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans

logger = logging.getLogger(__name__)

# Default temperature for cosine similarity spaces (where typical matches range in [0.3, 0.85])
DEFAULT_POSITIVE_TEMPERATURE = 0.15

# Recency decay settings
RECENCY_HALF_LIFE_DAYS = 365.0  # 1-year half-life for viewing date decay
RECENCY_FLOOR = 0.35            # Evergreen favorites retain at least 35% recency weight


@dataclass
class PositiveItemProfile:
    """Represents a classified positive item with calibrated taste signals."""
    item_id: str
    title: str
    year: str
    director: str
    genres: List[str]
    user_rating: float
    is_rewatch: bool
    viewing_date: Optional[date]
    recency_weight: float
    strength_weight: float
    pool_index: int


@dataclass
class PositiveMode:
    """Represents a single positive taste pillar (cluster)."""
    mode_id: int
    label: str
    centroid: np.ndarray
    weight: float              # pi_k: normalized prior weight, sum_k pi_k == 1.0
    member_indices: List[int]
    titles: List[str]
    dominant_genres: List[str]
    dominant_directors: List[str]
    cohesion: float            # mean cosine similarity of members to centroid
    recency_score: float       # mean recency factor of member items
    strength_score: float      # total rating mass of member items
    size: int


def _parse_date(val: Any) -> Optional[date]:
    """Safely extracts a datetime.date from strings, dates, or datetimes."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    try:
        s = str(val).strip()[:10]
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def calculate_item_recency(
    viewing_date: Optional[date],
    reference_date: Optional[date] = None,
    rank_in_history: Optional[int] = None,
    total_history_len: Optional[int] = None
) -> float:
    """
    Computes a recency weight in [RECENCY_FLOOR, 1.0].
    If viewing_date is present, uses exponential decay:
        recency = max(RECENCY_FLOOR, exp(- delta_days / (HALF_LIFE / ln(2))))
    Otherwise falls back to rank-based decay if rank is provided, or 1.0.
    """
    if viewing_date:
        ref = reference_date or date.today()
        try:
            delta_days = max(0, (ref - viewing_date).days)
            # decay lambda = ln(2) / half_life
            decay_rate = math.log(2.0) / max(1.0, RECENCY_HALF_LIFE_DAYS)
            decay = math.exp(-decay_rate * delta_days)
            return float(np.clip(max(RECENCY_FLOOR, decay), RECENCY_FLOOR, 1.0))
        except Exception:
            pass

    if rank_in_history is not None and total_history_len and total_history_len > 1:
        # Rank 0 is most recent
        rel_pos = rank_in_history / float(total_history_len)
        decay = math.exp(-1.5 * rel_pos)
        return float(np.clip(max(RECENCY_FLOOR, decay), RECENCY_FLOOR, 1.0))

    return 1.0


def classify_positive_item(
    item: Dict[str, Any],
    pool_index: int,
    rank_in_history: Optional[int] = None,
    total_history_len: Optional[int] = None,
    reference_date: Optional[date] = None
) -> PositiveItemProfile:
    """Extracts calibrated strength and recency weights for a positive item."""
    title = str(item.get("title") or item.get("movie") or "Untitled")
    year = str(item.get("year") or item.get("p_year") or "")
    director = str(item.get("director") or "Unknown")
    genre_str = str(item.get("genre") or "")
    genres = [g.strip().lower() for g in genre_str.replace("/", ",").split(",") if g.strip()]

    raw_rating = float(item.get("rating") or 4.0)
    is_rewatch = bool(item.get("rewatch") or item.get("is_rewatch"))
    v_date = _parse_date(item.get("v_date") or item.get("viewing_date"))

    # Strength weight: 5★ = 1.5, 4★ = 1.0, rewatch gives 1.3x multiplier
    base_strength = 1.5 if raw_rating >= 4.8 else 1.0
    rewatch_mult = 1.3 if is_rewatch else 1.0
    strength_weight = base_strength * rewatch_mult

    recency_weight = calculate_item_recency(
        viewing_date=v_date,
        reference_date=reference_date,
        rank_in_history=rank_in_history,
        total_history_len=total_history_len
    )

    return PositiveItemProfile(
        item_id=str(item.get("id", pool_index)),
        title=title,
        year=year,
        director=director,
        genres=genres,
        user_rating=raw_rating,
        is_rewatch=is_rewatch,
        viewing_date=v_date,
        recency_weight=recency_weight,
        strength_weight=strength_weight,
        pool_index=pool_index
    )


def _generate_mode_label(titles: List[str], dominant_genres: List[str], dominant_directors: List[str]) -> str:
    """Generates an intuitive descriptive label for a positive taste mode."""
    parts = []
    if dominant_genres:
        parts.append("/".join([g.title() for g in dominant_genres[:2]]))
    if dominant_directors:
        parts.append(f"feat. {dominant_directors[0]}")
    if not parts and titles:
        parts.append(f"Taste of {titles[0]}")
    return " · ".join(parts) if parts else "Positive Taste Mode"


def cluster_positive_modes(
    pos_profiles: List[PositiveItemProfile],
    semantic_matrix: np.ndarray,
    random_state: int = 42
) -> List[PositiveMode]:
    """
    Clusters positive favorites into distinct positive taste modes:
    - If 0 items: returns empty list
    - If 1-3 items: single centroid mode
    - If >= 4 items: adaptive KMeans clustering with deterministic seed
    Computes mode weights pi_k based on rating mass, temporal recency, and cohesion.
    """
    n_pos = len(pos_profiles)
    if n_pos == 0:
        return []

    pool_indices = [p.pool_index for p in pos_profiles]
    sub_matrix = semantic_matrix[pool_indices]  # n_pos x D

    # 1. Single mode fallback for sparse favorites
    if n_pos < 4:
        weights = np.array([p.strength_weight * p.recency_weight for p in pos_profiles], dtype=np.float32)
        w_sum = float(np.sum(weights))
        weights = weights / (w_sum + 1e-9)

        centroid = np.sum(sub_matrix * weights[:, np.newaxis], axis=0)
        centroid /= (np.linalg.norm(centroid) + 1e-9)

        sims = cosine_similarity(sub_matrix, centroid.reshape(1, -1)).flatten()
        cohesion = float(np.mean(sims)) if len(sims) > 0 else 1.0

        all_genres: Dict[str, int] = {}
        all_directors: Dict[str, int] = {}
        for p in pos_profiles:
            for g in p.genres:
                all_genres[g] = all_genres.get(g, 0) + 1
            if p.director and p.director.lower() not in ["unknown", "none", ""]:
                all_directors[p.director] = all_directors.get(p.director, 0) + 1

        top_genres = [g for g, _ in sorted(all_genres.items(), key=lambda x: x[1], reverse=True)[:3]]
        top_directors = [d for d, _ in sorted(all_directors.items(), key=lambda x: x[1], reverse=True)[:2]]
        titles = [p.title for p in pos_profiles]

        mode = PositiveMode(
            mode_id=0,
            label=_generate_mode_label(titles, top_genres, top_directors),
            centroid=centroid.astype(np.float32),
            weight=1.0,
            member_indices=pool_indices,
            titles=titles,
            dominant_genres=top_genres,
            dominant_directors=top_directors,
            cohesion=cohesion,
            recency_score=float(np.mean([p.recency_weight for p in pos_profiles])),
            strength_score=float(np.sum([p.strength_weight for p in pos_profiles])),
            size=n_pos
        )
        return [mode]

    # 2. Multi-mode clustering for >= 4 favorites
    n_modes = max(2, min(5, n_pos // 6))
    try:
        km = KMeans(n_clusters=n_modes, random_state=random_state, n_init=10).fit(sub_matrix)
        cluster_labels = km.labels_
    except Exception as e:
        logger.warning(f"KMeans positive mode clustering fallback to single mode: {e}")
        return cluster_positive_modes(pos_profiles[:3], semantic_matrix, random_state=random_state)

    raw_modes: List[PositiveMode] = []
    unnorm_weights: List[float] = []

    for m_id in range(n_modes):
        member_mask = (cluster_labels == m_id)
        sub_items = [pos_profiles[i] for i, mask in enumerate(member_mask) if mask]
        if not sub_items:
            continue

        sub_pool_indices = [p.pool_index for p in sub_items]
        sub_vecs = semantic_matrix[sub_pool_indices]

        item_weights = np.array([p.strength_weight * p.recency_weight for p in sub_items], dtype=np.float32)
        norm_item_weights = item_weights / (np.sum(item_weights) + 1e-9)

        c_vec = np.sum(sub_vecs * norm_item_weights[:, np.newaxis], axis=0)
        c_vec /= (np.linalg.norm(c_vec) + 1e-9)

        sims = cosine_similarity(sub_vecs, c_vec.reshape(1, -1)).flatten()
        cohesion = float(np.mean(sims)) if len(sims) > 0 else 1.0

        all_genres: Dict[str, int] = {}
        all_directors: Dict[str, int] = {}
        for p in sub_items:
            for g in p.genres:
                all_genres[g] = all_genres.get(g, 0) + 1
            if p.director and p.director.lower() not in ["unknown", "none", ""]:
                all_directors[p.director] = all_directors.get(p.director, 0) + 1

        top_genres = [g for g, _ in sorted(all_genres.items(), key=lambda x: x[1], reverse=True)[:3]]
        top_directors = [d for d, _ in sorted(all_directors.items(), key=lambda x: x[1], reverse=True)[:2]]
        titles = [p.title for p in sub_items]

        mass = float(np.sum([p.strength_weight for p in sub_items]))
        avg_recency = float(np.mean([p.recency_weight for p in sub_items]))

        # Mode weight pi_k formulation:
        # proportional to taste mass * recency * cohesion modulation
        cohesion_factor = 0.6 + 0.4 * max(0.0, min(1.0, cohesion))
        unnorm_pi = mass * avg_recency * cohesion_factor
        unnorm_weights.append(unnorm_pi)

        mode = PositiveMode(
            mode_id=len(raw_modes),
            label=_generate_mode_label(titles, top_genres, top_directors),
            centroid=c_vec.astype(np.float32),
            weight=1.0,  # will be normalized next
            member_indices=sub_pool_indices,
            titles=titles,
            dominant_genres=top_genres,
            dominant_directors=top_directors,
            cohesion=cohesion,
            recency_score=avg_recency,
            strength_score=mass,
            size=len(sub_items)
        )
        raw_modes.append(mode)

    if not raw_modes:
        return []

    # Normalize weights so sum(pi_k) == 1.0
    total_w = sum(unnorm_weights)
    if total_w > 1e-9:
        for idx, m in enumerate(raw_modes):
            m.weight = float(unnorm_weights[idx] / total_w)
    else:
        eq_w = 1.0 / len(raw_modes)
        for m in raw_modes:
            m.weight = eq_w

    return raw_modes


def compute_soft_positive_mode_affinity(
    matrix: np.ndarray,
    positive_modes: List[PositiveMode],
    tau: float = DEFAULT_POSITIVE_TEMPERATURE
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Computes temperature-controlled soft positive-mode aggregation:
        pos(i) = tau * log sum_k [ pi_k * exp(s_ik / tau) ]

    Implemented via numerically stable Log-Sum-Exp:
        m_i = max_k s_ik
        pos(i) = m_i + tau * log sum_k [ pi_k * exp((s_ik - m_i) / tau) ]

    Parameters:
    - matrix: candidate embedding matrix (N x D)
    - positive_modes: list of PositiveMode objects with centroids and weights pi_k
    - tau: temperature parameter > 0 (defaults to 0.15)

    Returns:
    - soft_scores: array of shape (N,) containing aggregated positive similarity
    - mode_sim_matrix: array of shape (N, K) with raw cosine similarities to each centroid
    - mode_responsibilities: array of shape (N, K) with softmax attribution P(k | i)
    - dominant_mode_indices: array of shape (N,) with argmax mode index
    """
    n_samples = matrix.shape[0]
    if not positive_modes:
        return (
            np.zeros(n_samples, dtype=np.float32),
            np.zeros((n_samples, 0), dtype=np.float32),
            np.zeros((n_samples, 0), dtype=np.float32),
            np.full(n_samples, -1, dtype=int)
        )

    centroids = np.array([m.centroid for m in positive_modes], dtype=np.float32)  # K x D
    pi_weights = np.array([m.weight for m in positive_modes], dtype=np.float32)   # K

    # Normalize pi_weights to ensure sum == 1.0
    pi_sum = float(np.sum(pi_weights))
    if pi_sum > 1e-9:
        pi_weights = pi_weights / pi_sum
    else:
        pi_weights = np.full(len(positive_modes), 1.0 / len(positive_modes), dtype=np.float32)

    # 1. Cosine similarity matrix S: N x K
    sim_matrix = cosine_similarity(matrix, centroids)  # N x K
    sim_matrix = np.clip(sim_matrix, -1.0, 1.0).astype(np.float32)

    # Single mode reduction: K = 1
    if len(positive_modes) == 1:
        s_single = sim_matrix[:, 0]
        responsibilities = np.ones((n_samples, 1), dtype=np.float32)
        dominant_indices = np.zeros(n_samples, dtype=int)
        return s_single, sim_matrix, responsibilities, dominant_indices

    # Asymptotic temperature guardrails
    if tau <= 1e-4:
        # tau -> 0+: hard maximum
        soft_scores = np.max(sim_matrix, axis=1)
        dominant_indices = np.argmax(sim_matrix, axis=1)
        responsibilities = np.zeros_like(sim_matrix)
        for i in range(n_samples):
            responsibilities[i, dominant_indices[i]] = 1.0
        return soft_scores.astype(np.float32), sim_matrix, responsibilities, dominant_indices

    if tau >= 100.0:
        # tau -> inf: weighted average
        soft_scores = np.sum(sim_matrix * pi_weights[np.newaxis, :], axis=1)
        dominant_indices = np.argmax(sim_matrix, axis=1)
        responsibilities = np.repeat(pi_weights[np.newaxis, :], n_samples, axis=0)
        return soft_scores.astype(np.float32), sim_matrix, responsibilities, dominant_indices

    # 2. Numerically stable Log-Sum-Exp
    m_i = np.max(sim_matrix, axis=1, keepdims=True)  # N x 1
    shifted_scaled = (sim_matrix - m_i) / tau         # N x K, all values <= 0

    # exp is strictly in (0, 1]
    exp_shifted = np.exp(shifted_scaled)              # N x K

    # Weighted sum: sum_k pi_k * exp((s_ik - m_i) / tau)
    weighted_sum = np.sum(exp_shifted * pi_weights[np.newaxis, :], axis=1, keepdims=True)  # N x 1
    weighted_sum = np.maximum(weighted_sum, 1e-12)

    # pos(i) = m_i + tau * log(weighted_sum)
    soft_scores = (m_i + tau * np.log(weighted_sum)).flatten().astype(np.float32)

    # Softmax mode responsibilities: P(k | i) = pi_k * exp(...) / weighted_sum
    responsibilities = (exp_shifted * pi_weights[np.newaxis, :] / weighted_sum).astype(np.float32)
    dominant_indices = np.argmax(responsibilities, axis=1)

    return soft_scores, sim_matrix, responsibilities, dominant_indices


def execute_positive_mode_pipeline(
    pool: List[Dict[str, Any]],
    semantic_norm: np.ndarray,
    user_raw_movies: Optional[List[Dict[str, Any]]] = None,
    tau: float = DEFAULT_POSITIVE_TEMPERATURE,
    random_state: int = 42
) -> Tuple[np.ndarray, List[PositiveMode], np.ndarray, np.ndarray]:
    """
    End-to-end positive mode pipeline:
    1. Extracts positive favorites from pool (is_watched and rating >= 4).
    2. Calibrates item strength and viewing recency (incorporating v_date).
    3. Clusters favorites into multi-modal positive taste pillars.
    4. Computes temperature-controlled soft aggregation pos(i) = tau * log sum_k pi_k exp(s_ik / tau).

    Returns:
    - soft_scores: np.ndarray (N,) containing positive semantic similarities
    - positive_modes: list of PositiveMode objects
    - responsibilities: np.ndarray (N, K)
    - dominant_indices: np.ndarray (N,)
    """
    n_samples = len(pool)
    if n_samples == 0:
        return (
            np.zeros(0, dtype=np.float32),
            [],
            np.zeros((0, 0), dtype=np.float32),
            np.zeros(0, dtype=int)
        )

    # Build history lookup for reverse chronological rank
    history_lookup: Dict[str, int] = {}
    if user_raw_movies:
        for r_idx, rm in enumerate(user_raw_movies):
            mid = str(rm.get("id") or "")
            if mid:
                history_lookup[mid] = r_idx

    pos_profiles: List[PositiveItemProfile] = []
    tot_hist = len(user_raw_movies) if user_raw_movies else len(pool)

    for idx, it in enumerate(pool):
        if not it.get("is_watched"):
            continue
        try:
            r_val = float(it.get("rating") or 0.0)
        except (ValueError, TypeError):
            r_val = 0.0

        if r_val >= 4.0:
            item_raw_id = str(it.get("id", "")).replace("watched_", "")
            rank = history_lookup.get(item_raw_id)
            prof = classify_positive_item(
                item=it,
                pool_index=idx,
                rank_in_history=rank,
                total_history_len=tot_hist
            )
            pos_profiles.append(prof)

    if not pos_profiles:
        # Fallback to mean centroid if no >= 4 star ratings exist
        user_sem_centroid = np.mean(semantic_norm, axis=0, keepdims=True)
        user_sem_centroid /= (np.linalg.norm(user_sem_centroid) + 1e-9)
        raw_scores = cosine_similarity(semantic_norm, user_sem_centroid).flatten().astype(np.float32)
        return (
            raw_scores,
            [],
            np.zeros((n_samples, 0), dtype=np.float32),
            np.full(n_samples, -1, dtype=int)
        )

    # Cluster positive modes
    positive_modes = cluster_positive_modes(
        pos_profiles=pos_profiles,
        semantic_matrix=semantic_norm,
        random_state=random_state
    )

    # Compute soft positive affinity
    soft_scores, _, responsibilities, dominant_indices = compute_soft_positive_mode_affinity(
        matrix=semantic_norm,
        positive_modes=positive_modes,
        tau=tau
    )

    logger.info(
        f"[POSITIVE MODES] Formed {len(positive_modes)} positive taste pillars from {len(pos_profiles)} favorites. "
        f"Temperature tau={tau}. Weights: {[round(m.weight, 3) for m in positive_modes]}"
    )

    return soft_scores, positive_modes, responsibilities, dominant_indices
