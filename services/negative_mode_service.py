"""
services/negative_mode_service.py — Multi-Mode Negative Preference Engine & Feature-Level Veto System

Models dislikes as multiple distinct negative modes (clusters) instead of a single
coarse centroid:
    neg_risk(i) = max_k [ q_k * cos(h_i, c_k^-) ]
where q_k represents confidence in negative cluster k.

Also distinguishes:
1. "Not for me" (taste/aesthetic mismatch) from "Low quality" (execution failure)
2. Abandoned films (visceral walkout/DNF) from completed low-rated films
3. Explicit dislikes from weak implicit signals
4. Dislike of genre from dislike of execution (via positive counter-evidence)
5. Feature-level vetoes (director, genre, semantic, quality) vs global centroid penalty
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Tuple, Optional, Set
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans

logger = logging.getLogger(__name__)

# Dislike classification types
DISLIKE_TASTE_MISMATCH = "TASTE_MISMATCH"    # "Not for me" (high consensus, low user rating)
DISLIKE_LOW_QUALITY = "LOW_QUALITY"          # "Low quality" (low consensus, low user rating)
DISLIKE_HYBRID = "HYBRID_NEGATIVE"           # Intermediate / unclassified

# Evidence source types
EVIDENCE_EXPLICIT_RATING = "explicit_rating"
EVIDENCE_CARD_REJECT = "card_reject"
EVIDENCE_ABANDONED = "abandoned"
EVIDENCE_IMPLICIT_DECAY = "implicit_decay"


@dataclass
class NegativeItemProfile:
    """Represents a classified negative item with calibrated evidence weights."""
    item_id: str
    title: str
    year: str
    director: str
    genres: List[str]
    user_rating: float
    tmdb_rating: Optional[float]
    dislike_type: str
    is_abandoned: bool
    evidence_source: str
    evidence_weight: float
    confidence: float
    pool_index: int


@dataclass
class NegativeMode:
    """Represents a single negative cluster (aversion mode)."""
    mode_id: int
    label: str
    centroid: np.ndarray
    confidence: float
    dislike_type: str
    member_indices: List[int]
    titles: List[str]
    dominant_genres: List[str]
    dominant_directors: List[str]
    cohesion: float
    is_taste_mismatch: bool = False
    is_low_quality: bool = False


@dataclass
class AversionProfile:
    """Catalog-level aversions with positive counter-evidence checking."""
    confirmed_genre_aversions: Dict[str, float]  # genre -> aversion confidence
    loved_genres: Set[str]                       # genres user loves (immune to genre veto)
    confirmed_director_aversions: Dict[str, float]  # director -> aversion confidence
    loved_directors: Set[str]


def _normalize_str(val: Any) -> str:
    if not val:
        return ""
    return str(val).strip().lower()


def _parse_genres(genre_val: Any) -> List[str]:
    if not genre_val:
        return []
    if isinstance(genre_val, list):
        return [str(g).strip() for g in genre_val if str(g).strip()]
    return [g.strip() for g in str(genre_val).split(",") if g.strip()]


def classify_negative_item(
    item: Dict[str, Any],
    pool_index: int,
    user_movie: Optional[Dict[str, Any]] = None
) -> NegativeItemProfile:
    """
    Classifies a negative item into 'TASTE_MISMATCH' ("Not for me") vs
    'LOW_QUALITY' ("Execution failure"), calibrating evidence weights and
    abandonment multipliers.
    """
    title = str(item.get("title") or "Untitled")
    year = str(item.get("year") or item.get("p_year") or "")
    director = str(item.get("director") or "Unknown")
    genres = _parse_genres(item.get("genre"))
    
    # 1. User rating
    raw_rating = item.get("rating")
    try:
        u_rating = float(raw_rating) if raw_rating is not None else 1.0
        if u_rating > 5.0:
            u_rating /= 2.0  # Normalize 10-scale to 5-scale
    except (ValueError, TypeError):
        u_rating = 1.0

    # 2. Consensus TMDB rating
    raw_tmdb = item.get("vote_average") or item.get("rating_score")
    if raw_tmdb is None and user_movie:
        raw_tmdb = user_movie.get("vote_average") or user_movie.get("rating_score")
    
    tmdb_rating = None
    if raw_tmdb is not None:
        try:
            tmdb_val = float(raw_tmdb)
            if tmdb_val > 0.0:
                tmdb_rating = tmdb_val
        except (ValueError, TypeError):
            pass

    # 3. Abandoned / DNF check
    # Check item status, flags, or explicit marks
    is_abandoned = False
    status_str = _normalize_str(item.get("status") or (user_movie.get("status") if user_movie else ""))
    if "abandon" in status_str or "drop" in status_str or "dnf" in status_str:
        is_abandoned = True
    elif item.get("is_abandoned") or (user_movie and user_movie.get("is_abandoned")):
        is_abandoned = True
    elif item.get("completed") is False or (user_movie and user_movie.get("completed") is False):
        is_abandoned = True

    # 4. Evidence source determination
    source = item.get("source") or "user_log"
    if item.get("is_card_reject"):
        evidence_source = EVIDENCE_CARD_REJECT
    elif is_abandoned:
        evidence_source = EVIDENCE_ABANDONED
    elif item.get("is_implicit"):
        evidence_source = EVIDENCE_IMPLICIT_DECAY
    else:
        evidence_source = EVIDENCE_EXPLICIT_RATING

    # 5. Distinguish "Not for me" (Taste Mismatch) from "Low quality"
    # Benchmark: TMDB >= 6.8 is consensus solid/acclaimed; TMDB <= 5.8 is consensus mediocre/poor.
    if tmdb_rating is not None:
        if tmdb_rating >= 6.8 or (tmdb_rating - (u_rating * 2.0) >= 3.0):
            dislike_type = DISLIKE_TASTE_MISMATCH
        elif tmdb_rating <= 5.8:
            dislike_type = DISLIKE_LOW_QUALITY
        else:
            dislike_type = DISLIKE_HYBRID
    else:
        # Fallback when no global consensus: if user gave 1 star, lean taste mismatch
        dislike_type = DISLIKE_TASTE_MISMATCH if u_rating <= 1.5 else DISLIKE_HYBRID

    # 6. Weight and Confidence calibration
    # Abandoned films get a 1.3x boost as hard visceral early repulsors
    abandon_mult = 1.30 if is_abandoned else 1.0

    if evidence_source == EVIDENCE_EXPLICIT_RATING:
        if u_rating <= 1.0:
            base_w = 1.75
            base_c = 1.0
        elif u_rating <= 2.0:
            base_w = 1.20
            base_c = 0.85
        else:
            base_w = 0.90
            base_c = 0.65
    elif evidence_source == EVIDENCE_CARD_REJECT:
        base_w = 1.15
        base_c = 0.80
    elif evidence_source == EVIDENCE_ABANDONED:
        base_w = 1.60
        base_c = 0.95
    else:  # Implicit decay / skip
        base_w = 0.40
        base_c = 0.35

    evidence_weight = float(base_w * abandon_mult)
    confidence = float(np.clip(base_c * (1.1 if is_abandoned else 1.0), 0.20, 1.0))

    return NegativeItemProfile(
        item_id=str(item.get("id") or pool_index),
        title=title,
        year=year,
        director=director,
        genres=genres,
        user_rating=u_rating,
        tmdb_rating=tmdb_rating,
        dislike_type=dislike_type,
        is_abandoned=is_abandoned,
        evidence_source=evidence_source,
        evidence_weight=evidence_weight,
        confidence=confidence,
        pool_index=pool_index
    )


def extract_genre_and_director_aversions(
    pool: List[Dict[str, Any]],
    neg_profiles: List[NegativeItemProfile]
) -> AversionProfile:
    """
    Cross-references negative items against the user's positive catalog (ratings >= 4.0).
    Resolves Dislike of Genre vs Dislike of Execution:
    - If user has >= 2 positive films in Genre G and positive ratio > 65%, G is a
      'loved_genre' and immune to genre-level vetoes.
    - If user has 0 positive films in Genre G and >= 1 negative film, G is a
      confirmed systemic genre aversion.
    """
    pos_genres: Dict[str, int] = {}
    pos_directors: Dict[str, int] = {}

    for item in pool:
        if item.get("is_watched") and item.get("rating", 0) >= 4:
            for g in _parse_genres(item.get("genre")):
                g_norm = _normalize_str(g)
                if g_norm and g_norm != "cinema":
                    pos_genres[g_norm] = pos_genres.get(g_norm, 0) + 1
            
            d_norm = _normalize_str(item.get("director"))
            if d_norm and d_norm not in ["unknown", "n/a", "none"]:
                pos_directors[d_norm] = pos_directors.get(d_norm, 0) + 1

    neg_genres: Dict[str, float] = {}
    neg_directors: Dict[str, float] = {}

    for prof in neg_profiles:
        # Only taste mismatches or explicit 1-2 star ratings define genre aversions
        w = prof.evidence_weight if prof.dislike_type != DISLIKE_LOW_QUALITY else prof.evidence_weight * 0.35
        for g in prof.genres:
            g_norm = _normalize_str(g)
            if g_norm and g_norm != "cinema":
                neg_genres[g_norm] = neg_genres.get(g_norm, 0.0) + w

        d_norm = _normalize_str(prof.director)
        if d_norm and d_norm not in ["unknown", "n/a", "none"]:
            neg_directors[d_norm] = neg_directors.get(d_norm, 0.0) + prof.evidence_weight

    # Categorize Genres
    loved_genres: Set[str] = set()
    confirmed_genre_aversions: Dict[str, float] = {}

    all_genres = set(pos_genres.keys()) | set(neg_genres.keys())
    for g in all_genres:
        n_pos = pos_genres.get(g, 0)
        n_neg = neg_genres.get(g, 0.0)

        if n_pos >= 2 and n_pos > n_neg:
            loved_genres.add(g)
        elif n_pos == 0 and n_neg >= 0.8:
            # Confirmed aversion: 0 positive films and meaningful negative weight
            conf = float(np.clip(0.50 + 0.20 * n_neg, 0.50, 0.95))
            confirmed_genre_aversions[g] = conf
        elif n_neg >= 2.5 and (n_neg / (n_pos + n_neg + 1e-5)) >= 0.70:
            # Heavy negative skew despite 1 isolated positive rating
            conf = float(np.clip(0.40 + 0.15 * n_neg, 0.40, 0.85))
            confirmed_genre_aversions[g] = conf

    # Categorize Directors
    loved_directors: Set[str] = set()
    confirmed_director_aversions: Dict[str, float] = {}

    all_directors = set(pos_directors.keys()) | set(neg_directors.keys())
    for d in all_directors:
        n_pos = pos_directors.get(d, 0)
        n_neg = neg_directors.get(d, 0.0)

        if n_pos >= 1:
            loved_directors.add(d)
        elif n_pos == 0 and n_neg >= 0.9:
            conf = float(np.clip(0.60 + 0.20 * n_neg, 0.60, 0.98))
            confirmed_director_aversions[d] = conf

    return AversionProfile(
        confirmed_genre_aversions=confirmed_genre_aversions,
        loved_genres=loved_genres,
        confirmed_director_aversions=confirmed_director_aversions,
        loved_directors=loved_directors
    )


def cluster_negative_modes(
    neg_profiles: List[NegativeItemProfile],
    hybrid_matrix: np.ndarray,
    random_state: int = 42
) -> List[NegativeMode]:
    """
    Clusters negative items into multiple distinct negative modes (clusters).
    Computes mode centroid c_k^- and mode confidence q_k based on:
    - Support & weight density of cluster
    - Average evidence confidence
    - Intra-cluster cohesion
    """
    if not neg_profiles:
        return []

    n_items = len(neg_profiles)
    neg_pool_indices = [p.pool_index for p in neg_profiles]
    sub_matrix = hybrid_matrix[neg_pool_indices].copy()
    
    # Ensure L2 normalization
    norms = np.linalg.norm(sub_matrix, axis=1, keepdims=True) + 1e-9
    sub_matrix /= norms

    # 1. Single negative item
    if n_items == 1:
        p0 = neg_profiles[0]
        label = f"Dislike: {p0.title}" if not p0.genres else f"Aversion: {p0.genres[0]}"
        return [NegativeMode(
            mode_id=0,
            label=label,
            centroid=sub_matrix[0],
            confidence=p0.confidence,
            dislike_type=p0.dislike_type,
            member_indices=[p0.pool_index],
            titles=[p0.title],
            dominant_genres=p0.genres[:2],
            dominant_directors=[p0.director] if p0.director != "Unknown" else [],
            cohesion=1.0,
            is_taste_mismatch=(p0.dislike_type == DISLIKE_TASTE_MISMATCH),
            is_low_quality=(p0.dislike_type == DISLIKE_LOW_QUALITY)
        )]

    # 2. Small set: 2 to 3 items
    # Check pairwise cosine similarity to determine if items represent the same mode or distinct modes
    if n_items in (2, 3):
        sim_mat = cosine_similarity(sub_matrix)
        # Average off-diagonal similarity
        off_diag = [sim_mat[i, j] for i in range(n_items) for j in range(i + 1, n_items)]
        mean_sim = float(np.mean(off_diag)) if off_diag else 0.0

        if mean_sim < 0.45:
            # Distinct modes for each item! Do NOT blur them into a single centroid
            modes = []
            for m_idx, prof in enumerate(neg_profiles):
                lbl = prof.genres[0] if prof.genres else prof.title
                modes.append(NegativeMode(
                    mode_id=m_idx,
                    label=f"Aversion Mode {m_idx + 1}: {lbl}",
                    centroid=sub_matrix[m_idx],
                    confidence=prof.confidence,
                    dislike_type=prof.dislike_type,
                    member_indices=[prof.pool_index],
                    titles=[prof.title],
                    dominant_genres=prof.genres[:2],
                    dominant_directors=[prof.director] if prof.director != "Unknown" else [],
                    cohesion=1.0,
                    is_taste_mismatch=(prof.dislike_type == DISLIKE_TASTE_MISMATCH),
                    is_low_quality=(prof.dislike_type == DISLIKE_LOW_QUALITY)
                ))
            return modes

    # 3. Multiple items: Cluster with KMeans
    n_modes = min(5, max(2, n_items // 3))
    if n_modes > n_items:
        n_modes = n_items

    try:
        km = KMeans(n_clusters=n_modes, random_state=random_state, n_init=10).fit(sub_matrix)
        cluster_labels = km.labels_
    except Exception as e:
        logger.warning(f"KMeans negative mode clustering fallback: {e}")
        cluster_labels = np.zeros(n_items, dtype=int)
        n_modes = 1

    modes: List[NegativeMode] = []
    for k in range(n_modes):
        member_sub_indices = [i for i, lbl in enumerate(cluster_labels) if lbl == k]
        if not member_sub_indices:
            continue

        cluster_profs = [neg_profiles[i] for i in member_sub_indices]
        cluster_vecs = sub_matrix[member_sub_indices]
        cluster_weights = np.array([p.evidence_weight for p in cluster_profs], dtype=np.float32)
        total_w = float(np.sum(cluster_weights))
        if total_w > 0:
            cluster_weights /= total_w

        # Weighted centroid
        c_k = np.sum(cluster_vecs * cluster_weights[:, np.newaxis], axis=0)
        c_k /= (np.linalg.norm(c_k) + 1e-9)

        # Intra-cluster cohesion (mean cosine similarity to centroid)
        cohesion = float(np.mean(cosine_similarity(cluster_vecs, c_k.reshape(1, -1)).flatten()))

        # Support confidence: 1 - exp(-0.75 * total_raw_weight)
        raw_weight_sum = sum(p.evidence_weight for p in cluster_profs)
        conf_support = 1.0 - math.exp(-0.75 * raw_weight_sum)

        # Mean evidence confidence of members
        mean_evidence_conf = float(np.mean([p.confidence for p in cluster_profs]))

        # Final mode confidence q_k in [0.20, 1.0]
        q_k = float(np.clip(conf_support * mean_evidence_conf * max(0.65, cohesion), 0.20, 1.0))

        # Determine dominant dislike type in cluster
        types = [p.dislike_type for p in cluster_profs]
        taste_cnt = types.count(DISLIKE_TASTE_MISMATCH)
        qual_cnt = types.count(DISLIKE_LOW_QUALITY)
        if taste_cnt > qual_cnt:
            dom_type = DISLIKE_TASTE_MISMATCH
        elif qual_cnt > taste_cnt:
            dom_type = DISLIKE_LOW_QUALITY
        else:
            dom_type = DISLIKE_HYBRID

        # Extract dominant genres & directors
        genre_freq: Dict[str, int] = {}
        for p in cluster_profs:
            for g in p.genres:
                genre_freq[g] = genre_freq.get(g, 0) + 1
        dom_genres = [g for g, _ in sorted(genre_freq.items(), key=lambda x: x[1], reverse=True)[:3]]

        dir_freq: Dict[str, int] = {}
        for p in cluster_profs:
            if p.director and p.director != "Unknown":
                dir_freq[p.director] = dir_freq.get(p.director, 0) + 1
        dom_dirs = [d for d, _ in sorted(dir_freq.items(), key=lambda x: x[1], reverse=True)[:2]]

        titles = [p.title for p in cluster_profs]

        # Readable label
        if dom_genres:
            label = f"Mode {k + 1}: {', '.join(dom_genres)}"
        elif dom_dirs:
            label = f"Mode {k + 1}: {dom_dirs[0]} Style"
        else:
            label = f"Mode {k + 1}: {titles[0]}"

        modes.append(NegativeMode(
            mode_id=k,
            label=label,
            centroid=c_k,
            confidence=q_k,
            dislike_type=dom_type,
            member_indices=[p.pool_index for p in cluster_profs],
            titles=titles,
            dominant_genres=dom_genres,
            dominant_directors=dom_dirs,
            cohesion=cohesion,
            is_taste_mismatch=(dom_type == DISLIKE_TASTE_MISMATCH),
            is_low_quality=(dom_type == DISLIKE_LOW_QUALITY)
        ))

    return modes


def compute_multi_mode_negative_risk(
    hybrid_matrix: np.ndarray,
    negative_modes: List[NegativeMode]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Computes multi-mode negative risk for all items:
        neg_risk(i) = max_k [ q_k * cos(h_i, c_k^-) ]
    
    Returns:
    - neg_risk: array of shape (N,) containing max risk per item
    - closest_mode_idx: array of shape (N,) containing the index of the closest negative mode
    - mode_sim_matrix: matrix of shape (N, K) of unweighted cosine similarities to each mode
    """
    n_samples = hybrid_matrix.shape[0]
    if not negative_modes:
        return (
            np.zeros(n_samples, dtype=np.float32),
            np.full(n_samples, -1, dtype=int),
            np.zeros((n_samples, 0), dtype=np.float32)
        )

    centroids = np.array([m.centroid for m in negative_modes], dtype=np.float32)  # K x D
    q_weights = np.array([m.confidence for m in negative_modes], dtype=np.float32) # K

    # Cosine similarities N x K
    sim_matrix = cosine_similarity(hybrid_matrix, centroids)  # N x K
    sim_matrix = np.clip(sim_matrix, 0.0, 1.0)

    # Weighted risk per mode: N x K
    weighted_risks = sim_matrix * q_weights[np.newaxis, :]

    closest_mode_idx = np.argmax(weighted_risks, axis=1)
    neg_risk = np.max(weighted_risks, axis=1).astype(np.float32)

    return neg_risk, closest_mode_idx, sim_matrix.astype(np.float32)


def evaluate_feature_level_veto(
    item: Dict[str, Any],
    candidate_vector: np.ndarray,
    negative_modes: List[NegativeMode],
    mode_sims: np.ndarray,
    aversions: AversionProfile
) -> Tuple[float, bool, Dict[str, Any]]:
    """
    Evaluates multi-tiered feature-level veto gates for candidate item:
    1. Director Veto Gate
    2. Genre Aversion Veto Gate (immune if genre is in loved_genres)
    3. Semantic Taste Mismatch Veto Gate
    4. Execution Quality Gate

    Returns:
    - veto_factor: multiplier in [0.10, 1.0]
    - is_vetoed: True if veto_factor < 0.50
    - diagnostics: explanation of active vetoes and closest negative mode
    """
    if not negative_modes:
        return 1.0, False, {
            "veto_factor": 1.0,
            "is_vetoed": False,
            "closest_mode": None,
            "reasons": []
        }

    reasons: List[str] = []
    v_dir = 1.0
    v_genre = 1.0
    v_sem = 1.0
    v_qual = 1.0

    director_norm = _normalize_str(item.get("director"))
    item_genres = [_normalize_str(g) for g in _parse_genres(item.get("genre"))]

    # 1. Director Veto Gate
    if director_norm in aversions.confirmed_director_aversions:
        conf = aversions.confirmed_director_aversions[director_norm]
        v_dir = max(0.15, 1.0 - 0.85 * conf)
        reasons.append(f"Director Aversion: {item.get('director')}")

    # 2. Genre Aversion Veto Gate (with positive counter-evidence protection)
    active_genre_aversion = None
    max_g_conf = 0.0
    for g in item_genres:
        if g in aversions.loved_genres:
            # Protected by loved genre!
            active_genre_aversion = None
            max_g_conf = 0.0
            break
        if g in aversions.confirmed_genre_aversions:
            g_conf = aversions.confirmed_genre_aversions[g]
            if g_conf > max_g_conf:
                max_g_conf = g_conf
                active_genre_aversion = g

    if active_genre_aversion:
        v_genre = max(0.20, 1.0 - 0.80 * max_g_conf)
        reasons.append(f"Genre Aversion: {active_genre_aversion.title()}")

    # 3. Semantic Taste Mismatch Veto Gate
    # Check similarity against "TASTE_MISMATCH" modes
    for m_idx, mode in enumerate(negative_modes):
        if mode.is_taste_mismatch and mode.confidence >= 0.60:
            sim = float(mode_sims[m_idx])
            # Threshold: >= 0.65 similarity to an aesthetic mismatch mode triggers exponential veto
            if sim >= 0.65:
                excess = (sim - 0.65) / 0.35
                gate = math.exp(-2.8 * excess * mode.confidence)
                v_sem = min(v_sem, max(0.15, gate))
                reasons.append(f"Taste Mismatch: {mode.label} (sim={sim:.2f})")

    # 4. Execution Quality Gate
    # Low quality negative modes only penalize candidates with low consensus quality
    for m_idx, mode in enumerate(negative_modes):
        if mode.is_low_quality:
            sim = float(mode_sims[m_idx])
            if sim >= 0.50:
                raw_cand_r = item.get("vote_average") or item.get("rating_score")
                try:
                    c_rating = float(raw_cand_r) if raw_cand_r is not None else 6.0
                except (ValueError, TypeError):
                    c_rating = 6.0

                if c_rating < 6.0:
                    v_qual = min(v_qual, 0.40)
                    reasons.append(f"Execution Quality Risk: TMDB {c_rating:.1f} in {mode.label}")
                elif c_rating < 7.2:
                    # Mild interpolation
                    qual_factor = 0.40 + 0.60 * ((c_rating - 6.0) / 1.2)
                    v_qual = min(v_qual, qual_factor)
                # If c_rating >= 7.2: masterpiece passes freely! v_qual remains 1.0

    # Unified Veto Factor
    unified_veto = float(min(v_dir, v_genre, v_sem, v_qual))
    is_vetoed = bool(unified_veto < 0.50)

    # Closest mode details
    best_m_idx = int(np.argmax(mode_sims)) if len(mode_sims) > 0 else 0
    closest_mode = negative_modes[best_m_idx] if best_m_idx < len(negative_modes) else None

    diagnostics = {
        "veto_factor": round(unified_veto, 3),
        "is_vetoed": is_vetoed,
        "director_gate": round(v_dir, 3),
        "genre_gate": round(v_genre, 3),
        "semantic_gate": round(v_sem, 3),
        "quality_gate": round(v_qual, 3),
        "closest_mode_id": closest_mode.mode_id if closest_mode else None,
        "closest_mode_label": closest_mode.label if closest_mode else None,
        "closest_mode_confidence": round(closest_mode.confidence, 3) if closest_mode else 0.0,
        "reasons": reasons
    }

    return unified_veto, is_vetoed, diagnostics


def execute_negative_mode_pipeline(
    pool: List[Dict[str, Any]],
    hybrid_matrix: np.ndarray,
    user_raw_movies: Optional[List[Dict[str, Any]]] = None
) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, Any]], List[NegativeMode]]:
    """
    Full end-to-end execution pipeline for negative preference modeling:
    1. Extracts and classifies all negative items in pool
    2. Builds positive counter-evidence & aversion profile
    3. Clusters negative items into distinct negative modes
    4. Computes multi-mode negative risk neg_risk(i) = max_k [ q_k * cos(h_i, c_k^-) ]
    5. Evaluates feature-level veto gates for every candidate
    
    Returns:
    - neg_risks: array of shape (N,)
    - veto_factors: array of shape (N,)
    - veto_diagnostics: list of length N with diagnostics per star
    - negative_modes: list of NegativeMode objects
    """
    n_samples = len(pool)
    user_movies_by_title_year: Dict[str, Dict[str, Any]] = {}
    if user_raw_movies:
        for m in user_raw_movies:
            t = _normalize_str(m.get("movie") or "")
            y = str(m.get("p_year") or "").strip()
            user_movies_by_title_year[f"{t}_{y}"] = m
            user_movies_by_title_year[t] = m

    # 1. Identify negative items in pool
    neg_profiles: List[NegativeItemProfile] = []
    for idx, it in enumerate(pool):
        is_neg = (
            it.get("category") == "void_repulsor" or
            (it.get("is_watched") and it.get("rating", 0) <= 2) or
            it.get("is_card_reject") or
            it.get("is_abandoned")
        )
        if is_neg:
            t = _normalize_str(it.get("title") or "")
            y = str(it.get("year") or "").strip()
            matched_user_m = user_movies_by_title_year.get(f"{t}_{y}") or user_movies_by_title_year.get(t)
            prof = classify_negative_item(it, pool_index=idx, user_movie=matched_user_m)
            neg_profiles.append(prof)

    # 2. Extract positive counter-evidence and aversions
    aversions = extract_genre_and_director_aversions(pool, neg_profiles)

    # 3. Cluster into negative modes
    negative_modes = cluster_negative_modes(neg_profiles, hybrid_matrix)

    # 4. Multi-mode negative risk
    neg_risks, closest_modes, sim_matrix = compute_multi_mode_negative_risk(hybrid_matrix, negative_modes)

    # 5. Feature-level veto evaluation for every item in pool
    veto_factors = np.ones(n_samples, dtype=np.float32)
    veto_diagnostics: List[Dict[str, Any]] = []

    for idx, item in enumerate(pool):
        if not negative_modes:
            veto_diagnostics.append({
                "veto_factor": 1.0,
                "is_vetoed": False,
                "reasons": []
            })
            continue

        v_factor, is_vet, diag = evaluate_feature_level_veto(
            item=item,
            candidate_vector=hybrid_matrix[idx],
            negative_modes=negative_modes,
            mode_sims=sim_matrix[idx],
            aversions=aversions
        )
        veto_factors[idx] = v_factor
        veto_diagnostics.append(diag)

    logger.info(
        f"[NEGATIVE MODES] Formed {len(negative_modes)} aversion modes from {len(neg_profiles)} negative items. "
        f"Genre Aversions: {list(aversions.confirmed_genre_aversions.keys())} | "
        f"Protected Loved Genres: {list(aversions.loved_genres)}"
    )

    return neg_risks, veto_factors, veto_diagnostics, negative_modes
