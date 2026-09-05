"""
tests/test_positive_mode_service.py — Unit tests for Multi-Mode Positive Preference Engine
and Temperature-Controlled Soft Aggregation
"""

import math
from datetime import date, timedelta
import pytest
import numpy as np

from services.positive_mode_service import (
    PositiveItemProfile,
    PositiveMode,
    calculate_item_recency,
    classify_positive_item,
    cluster_positive_modes,
    compute_soft_positive_mode_affinity,
    execute_positive_mode_pipeline,
    DEFAULT_POSITIVE_TEMPERATURE,
    RECENCY_FLOOR
)


def test_calculate_item_recency_exponential_decay():
    today = date(2026, 9, 1)
    
    # 0 days ago -> 1.0
    r0 = calculate_item_recency(viewing_date=today, reference_date=today)
    assert pytest.approx(r0, abs=1e-3) == 1.0

    # 365 days ago -> ~0.50 (half-life)
    r365 = calculate_item_recency(viewing_date=today - timedelta(days=365), reference_date=today)
    assert pytest.approx(r365, abs=0.02) == 0.50

    # 5 years ago -> should not drop below RECENCY_FLOOR (0.35)
    r_old = calculate_item_recency(viewing_date=today - timedelta(days=365 * 5), reference_date=today)
    assert r_old >= RECENCY_FLOOR
    assert pytest.approx(r_old, abs=1e-3) == RECENCY_FLOOR


def test_classify_positive_item_strength_and_rewatch():
    # 5-star rewatch
    item_5_rewatch = {
        "id": "m1",
        "movie": "Blade Runner",
        "p_year": 1982,
        "director": "Ridley Scott",
        "genre": "Sci-Fi, Cyberpunk",
        "rating": 5,
        "rewatch": 1,
        "v_date": "2026-08-15"
    }
    prof_5 = classify_positive_item(item_5_rewatch, pool_index=0)
    assert prof_5.user_rating == 5.0
    assert prof_5.is_rewatch is True
    # 1.5 (for 5-star) * 1.3 (for rewatch) = 1.95
    assert pytest.approx(prof_5.strength_weight, abs=1e-3) == 1.95
    assert prof_5.recency_weight > 0.90

    # 4-star first watch
    item_4 = {
        "id": "m2",
        "movie": "Arrival",
        "p_year": 2016,
        "director": "Denis Villeneuve",
        "genre": "Sci-Fi",
        "rating": 4,
        "rewatch": 0
    }
    prof_4 = classify_positive_item(item_4, pool_index=1)
    assert pytest.approx(prof_4.strength_weight, abs=1e-3) == 1.0


def test_single_mode_reduction_identity():
    # When K = 1, pos(i) MUST exactly equal cosine similarity s_{i,1}
    np.random.seed(42)
    dim = 16
    n_samples = 5
    matrix = np.random.randn(n_samples, dim).astype(np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)

    c = np.random.randn(dim).astype(np.float32)
    c /= np.linalg.norm(c)

    single_mode = PositiveMode(
        mode_id=0,
        label="Single Pillar",
        centroid=c,
        weight=1.0,
        member_indices=[0],
        titles=["Title 1"],
        dominant_genres=["Sci-Fi"],
        dominant_directors=["Director"],
        cohesion=1.0,
        recency_score=1.0,
        strength_score=1.0,
        size=1
    )

    soft_scores, sim_mat, responsibilities, dominant_indices = compute_soft_positive_mode_affinity(
        matrix=matrix,
        positive_modes=[single_mode],
        tau=0.15
    )

    expected_sim = np.dot(matrix, c)
    assert np.allclose(soft_scores, expected_sim, atol=1e-5)
    assert np.all(responsibilities == 1.0)
    assert np.all(dominant_indices == 0)


def test_soft_max_mathematical_equivalence_to_raw_formula():
    # Compare numerically stable Log-Sum-Exp to raw formula in double precision
    np.random.seed(123)
    K = 3
    dim = 8
    n_samples = 4
    tau = 0.20

    cand = np.random.randn(n_samples, dim).astype(np.float32)
    cand /= np.linalg.norm(cand, axis=1, keepdims=True)

    modes = []
    pi_raw = [0.5, 0.3, 0.2]
    for k in range(K):
        c = np.random.randn(dim).astype(np.float32)
        c /= np.linalg.norm(c)
        modes.append(PositiveMode(
            mode_id=k,
            label=f"Mode {k}",
            centroid=c,
            weight=pi_raw[k],
            member_indices=[k],
            titles=[f"Title {k}"],
            dominant_genres=["Drama"],
            dominant_directors=["Director"],
            cohesion=0.9,
            recency_score=1.0,
            strength_score=1.0,
            size=1
        ))

    soft_scores, sim_mat, resp, dom = compute_soft_positive_mode_affinity(
        matrix=cand,
        positive_modes=modes,
        tau=tau
    )

    # Compute raw math: tau * log sum_k pi_k exp(s_ik / tau)
    for i in range(n_samples):
        s_i = sim_mat[i]
        raw_val = tau * math.log(sum(pi_raw[k] * math.exp(s_i[k] / tau) for k in range(K)))
        assert pytest.approx(soft_scores[i], abs=1e-5) == raw_val


def test_temperature_asymptotics():
    # As tau -> 0, pos(i) -> max_k s_ik
    # As tau -> inf, pos(i) -> sum_k pi_k s_ik
    np.random.seed(99)
    dim = 4
    matrix = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)

    c1 = np.array([0.9, 0.1, 0.0, 0.0], dtype=np.float32); c1 /= np.linalg.norm(c1)
    c2 = np.array([0.3, 0.9, 0.0, 0.0], dtype=np.float32); c2 /= np.linalg.norm(c2)

    modes = [
        PositiveMode(0, "M1", c1, 0.6, [0], ["T1"], ["Sci-Fi"], ["D1"], 1.0, 1.0, 1.0, 1),
        PositiveMode(1, "M2", c2, 0.4, [1], ["T2"], ["Crime"], ["D2"], 1.0, 1.0, 1.0, 1)
    ]

    s1 = float(np.dot(matrix[0], c1))
    s2 = float(np.dot(matrix[0], c2))

    # Low tau -> hard max
    scores_low, _, _, _ = compute_soft_positive_mode_affinity(matrix, modes, tau=0.00001)
    assert pytest.approx(scores_low[0], abs=1e-4) == max(s1, s2)

    # High tau -> weighted average
    scores_high, _, _, _ = compute_soft_positive_mode_affinity(matrix, modes, tau=1000.0)
    expected_weighted_avg = 0.6 * s1 + 0.4 * s2
    assert pytest.approx(scores_high[0], abs=1e-4) == expected_weighted_avg


def test_multimodal_harmony_beats_narrow_single_mode_outlier():
    """
    CRITICAL BEHAVIORAL TEST:
    Candidate A matches Mode 1 strongly (0.80) but conflicts with Mode 2 (0.15).
    Candidate B matches both Mode 1 (0.70) and Mode 2 (0.70) (harmonizes multi-modal tastes).
    
    Under hard max:
        max(A) = 0.80 > max(B) = 0.70 (Candidate A wins erroneously).
    Under soft max (tau=0.15, pi = [0.5, 0.5]):
        Candidate B achieves pos(B) = 0.700 > pos(A) = 0.698!
        Candidate B wins because multi-modal taste is preserved.
    """
    dim = 3
    c1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    c2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    modes = [
        PositiveMode(0, "Sci-Fi", c1, 0.5, [0], ["Blade Runner"], ["Sci-Fi"], ["Ridley Scott"], 1.0, 1.0, 1.0, 1),
        PositiveMode(1, "Romance", c2, 0.5, [1], ["In the Mood for Love"], ["Drama"], ["Wong Kar-wai"], 1.0, 1.0, 1.0, 1),
    ]

    # Construct exact unit vectors in 3D:
    # Cand A: dot(x_A, c1) = 0.80, dot(x_A, c2) = 0.15
    z_A = math.sqrt(max(0.0, 1.0 - 0.80**2 - 0.15**2))
    cand_A = np.array([0.80, 0.15, z_A], dtype=np.float32)
    cand_A /= np.linalg.norm(cand_A)

    # Cand B: dot(x_B, c1) = 0.70, dot(x_B, c2) = 0.70
    z_B = math.sqrt(max(0.0, 1.0 - 0.70**2 - 0.70**2))
    cand_B = np.array([0.70, 0.70, z_B], dtype=np.float32)
    cand_B /= np.linalg.norm(cand_B)

    matrix = np.stack([cand_A, cand_B], axis=0)

    scores, sim_mat, resp, _ = compute_soft_positive_mode_affinity(matrix, modes, tau=0.15)

    score_A = scores[0]
    score_B = scores[1]

    # Verify raw cosine similarities
    assert pytest.approx(sim_mat[0, 0], abs=1e-3) == 0.80
    assert pytest.approx(sim_mat[0, 1], abs=1e-3) == 0.15
    assert pytest.approx(sim_mat[1, 0], abs=1e-3) == 0.70
    assert pytest.approx(sim_mat[1, 1], abs=1e-3) == 0.70

    # Under hard max: Cand A would win (0.80 > 0.70)
    assert np.max(sim_mat[0]) > np.max(sim_mat[1])

    # Cand B harmonizes across both positive modes and MUST outscore narrow outlier Cand A
    assert score_B > score_A
    assert resp[0, 0] > 0.90  # Cand A overwhelmingly attributed to Mode 0
    assert pytest.approx(resp[1, 0], abs=0.01) == 0.50  # Cand B equally attributed to both


def test_cluster_positive_modes_preserves_weights_and_labels():
    np.random.seed(42)
    dim = 16
    # 8 positive favorites: 4 Sci-Fi (items 0..3) + 4 Romance (items 4..7)
    v_scifi = np.array([1.0, 0.0] + [0.0] * (dim - 2), dtype=np.float32)
    v_rom = np.array([0.0, 1.0] + [0.0] * (dim - 2), dtype=np.float32)

    semantic_matrix = np.zeros((8, dim), dtype=np.float32)
    for i in range(4):
        noise = np.random.randn(dim) * 0.05
        semantic_matrix[i] = v_scifi + noise
        semantic_matrix[i] /= np.linalg.norm(semantic_matrix[i])
    for i in range(4, 8):
        noise = np.random.randn(dim) * 0.05
        semantic_matrix[i] = v_rom + noise
        semantic_matrix[i] /= np.linalg.norm(semantic_matrix[i])

    profiles = []
    for i in range(4):
        profiles.append(PositiveItemProfile(
            item_id=f"sf_{i}",
            title=f"Sci-Fi Movie {i}",
            year="2020",
            director="Denis Villeneuve",
            genres=["sci-fi"],
            user_rating=5.0,
            is_rewatch=True,
            viewing_date=date(2026, 8, 1),
            recency_weight=1.0,
            strength_weight=1.95,
            pool_index=i
        ))
    for i in range(4, 8):
        profiles.append(PositiveItemProfile(
            item_id=f"rom_{i}",
            title=f"Romance Movie {i}",
            year="2018",
            director="Wong Kar-wai",
            genres=["romance", "drama"],
            user_rating=4.0,
            is_rewatch=False,
            viewing_date=date(2024, 1, 1),
            recency_weight=0.5,
            strength_weight=1.0,
            pool_index=i
        ))

    modes = cluster_positive_modes(profiles, semantic_matrix, random_state=42)
    assert len(modes) >= 2

    # Weights must sum to 1.0
    total_pi = sum(m.weight for m in modes)
    assert pytest.approx(total_pi, abs=1e-5) == 1.0

    # Sci-Fi cluster had 5-star ratings, rewatches, and recent viewing -> its weight should be higher
    sf_mode = next(m for m in modes if any("sci-fi" in g for g in m.dominant_genres))
    rom_mode = next(m for m in modes if any("romance" in g or "drama" in g for g in m.dominant_genres))
    assert sf_mode.weight > rom_mode.weight


def test_execute_positive_mode_pipeline_end_to_end():
    dim = 8
    pool = [
        {"id": "w1", "movie": "Blade Runner", "rating": 5, "is_watched": True, "genre": "Sci-Fi", "director": "Ridley Scott"},
        {"id": "w2", "movie": "Alien", "rating": 5, "is_watched": True, "genre": "Sci-Fi", "director": "Ridley Scott"},
        {"id": "w3", "movie": "In the Mood for Love", "rating": 4, "is_watched": True, "genre": "Drama", "director": "Wong Kar-wai"},
        {"id": "w4", "movie": "Chungking Express", "rating": 5, "is_watched": True, "genre": "Drama", "director": "Wong Kar-wai"},
        {"id": "c1", "movie": "Solaris", "rating": 0, "is_watched": False, "genre": "Sci-Fi", "director": "Andrei Tarkovsky"},
    ]
    semantic_norm = np.random.randn(len(pool), dim).astype(np.float32)
    semantic_norm /= np.linalg.norm(semantic_norm, axis=1, keepdims=True)

    scores, modes, resp, dom = execute_positive_mode_pipeline(
        pool=pool,
        semantic_norm=semantic_norm,
        tau=0.15
    )

    assert len(scores) == len(pool)
    assert len(modes) >= 1
    assert resp.shape == (len(pool), len(modes))
    assert len(dom) == len(pool)
    # Check bounded scores
    assert np.all(scores >= -1.0) and np.all(scores <= 1.05)
