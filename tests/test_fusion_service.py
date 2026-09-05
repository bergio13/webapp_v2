"""
test_fusion_service.py — Unit tests for Training-Free Adaptive Fusion Engine
"""

import pytest
import numpy as np
from services.fusion_service import (
    DEFAULT_PRIORS,
    MIN_CONFIDENCE_FLOOR,
    LOW_EVIDENCE_THRESHOLD,
    compute_structured_confidence,
    compute_semantic_confidence,
    compute_graph_confidence,
    renormalize_adaptive_weights,
    catalogue_robust_normalize,
    compute_cross_modal_agreement,
    execute_adaptive_fusion,
)


def test_structured_confidence_complete():
    item = {
        "title": "Dune: Part Two",
        "year": "2024",
        "director": "Denis Villeneuve",
        "genre": "Sci-Fi, Adventure",
        "tags": "spice, desert, messiah",
        "craft": {
            "director": "Denis Villeneuve",
            "cinematographer": "Greig Fraser",
            "composer": "Hans Zimmer",
            "screenwriter": "Jon Spaihts",
            "lead_actors": "Timothée Chalamet, Zendaya",
            "studios": "Legendary Pictures, Warner Bros."
        }
    }
    c_s = compute_structured_confidence(item)
    assert 0.95 <= c_s <= 1.0


def test_structured_confidence_sparse():
    # Only generic genre, no director or craft
    item = {
        "title": "Mystery Film",
        "year": "1999",
        "director": "Unknown",
        "genre": "Cinema",
        "tags": ""
    }
    c_s = compute_structured_confidence(item)
    # Generic genre (0.12) + valid year (0.15) = 0.27
    assert 0.20 <= c_s <= 0.35


def test_structured_confidence_floor():
    # Empty metadata
    item = {
        "title": "Blank",
        "year": "invalid",
        "director": "",
        "genre": "",
        "tags": ""
    }
    c_s = compute_structured_confidence(item)
    assert c_s == pytest.approx(MIN_CONFIDENCE_FLOOR)


def test_semantic_confidence_levels():
    # 1. Full synopsis + keywords
    item_rich = {
        "overview": "A complex deep space journey where astronauts confront existential dread and temporal paradoxes across distant star systems.",
        "tags": "sci-fi, space, philosophical"
    }
    assert compute_semantic_confidence(item_rich) == pytest.approx(1.0)

    # 2. Standard synopsis only
    item_med = {
        "overview": "A young detective investigates a string of rainy murders in downtown.",
        "tags": ""
    }
    assert compute_semantic_confidence(item_med) == pytest.approx(0.8)

    # 3. Short description
    item_short = {
        "overview": "Dark thriller.",
        "frontier_desc": "Noir investigation"
    }
    assert compute_semantic_confidence(item_short) == pytest.approx(0.5)

    # 4. Title / Genre only
    item_sparse = {
        "overview": "",
        "tags": ""
    }
    assert compute_semantic_confidence(item_sparse) == pytest.approx(0.2)

    # 5. Invalid embedding
    assert compute_semantic_confidence(item_rich, has_valid_embedding=False) == pytest.approx(MIN_CONFIDENCE_FLOOR)


def test_graph_confidence_dynamics():
    # 1. Cold start / isolated node
    c_g_isolated = compute_graph_confidence(
        node_degree=0,
        useful_edges=0,
        has_fav_connection=False,
        user_history_len=20
    )
    assert c_g_isolated == pytest.approx(MIN_CONFIDENCE_FLOOR)

    # 2. Well connected with direct craft bridge to user favorite
    c_g_connected = compute_graph_confidence(
        node_degree=6,
        useful_edges=5,
        has_fav_connection=True,
        user_history_len=25
    )
    assert c_g_connected >= 0.85

    # 3. Mega-hub node (degree = 50) penalized by hub dampener
    c_g_hub = compute_graph_confidence(
        node_degree=50,
        useful_edges=5,
        has_fav_connection=True,
        user_history_len=25
    )
    assert c_g_hub < c_g_connected

    # 4. Short user history dampening
    c_g_short_user = compute_graph_confidence(
        node_degree=6,
        useful_edges=5,
        has_fav_connection=True,
        user_history_len=1
    )
    assert c_g_short_user < c_g_connected


def test_adaptive_weights_renormalization_user_example():
    """
    Test exact user example from specification:
    c = (0.9, 1.0, 0.1)
    priors = (0.55, 0.30, 0.15)
    p * c = (0.495, 0.300, 0.015)
    w ≈ (0.611, 0.370, 0.019)
    """
    w, total_c = renormalize_adaptive_weights(0.9, 1.0, 0.1, priors=DEFAULT_PRIORS)
    assert pytest.approx(w[0], abs=0.01) == 0.61
    assert pytest.approx(w[1], abs=0.01) == 0.37
    assert pytest.approx(w[2], abs=0.01) == 0.02
    assert pytest.approx(np.sum(w)) == 1.0

    # Well-connected example: c = (0.9, 0.9, 1.0)
    w_conn, _ = renormalize_adaptive_weights(0.9, 0.9, 1.0, priors=DEFAULT_PRIORS)
    assert pytest.approx(w_conn[0], abs=0.02) == 0.54
    assert pytest.approx(w_conn[1], abs=0.02) == 0.29
    assert pytest.approx(w_conn[2], abs=0.02) == 0.17
    assert pytest.approx(np.sum(w_conn)) == 1.0


def test_confidence_floor_and_fallback():
    # If all confidences are below fallback threshold, revert to default priors
    w_fall, total_c = renormalize_adaptive_weights(0.01, 0.01, 0.01, priors=DEFAULT_PRIORS)
    assert np.allclose(w_fall, DEFAULT_PRIORS)


def test_catalogue_robust_normalize():
    # Median should map to ~0.5 under sigmoid
    scores = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9], dtype=np.float32)
    norm = catalogue_robust_normalize(scores)
    
    median_idx = 4  # score = 0.5
    assert pytest.approx(norm[median_idx], abs=0.05) == 0.50
    # Values should be strictly in [0, 1]
    assert np.all(norm >= 0.0) and np.all(norm <= 1.0)
    # Monotonicity preserved
    assert np.all(np.diff(norm) > 0)


def test_cross_modal_agreement():
    # Perfect agreement
    res_agree = compute_cross_modal_agreement(0.8, 0.8, 0.8)
    assert res_agree["agreement"] == pytest.approx(1.0)
    assert res_agree["is_exploratory"] is False

    # High disagreement (e.g. S=0.9, E=0.85, G=0.1)
    res_disagree = compute_cross_modal_agreement(0.9, 0.85, 0.1)
    assert res_disagree["variance"] > 0.05
    assert res_disagree["is_exploratory"] is True
    assert res_disagree["agreement"] < 0.60


def test_execute_adaptive_fusion_end_to_end():
    n = 5
    items = [
        {"id": f"m_{i}", "title": f"Movie {i}", "year": 2020 + i, "director": "Director A", "genre": "Drama", "overview": "A dramatic story." * 5, "tags": "deep, drama"}
        for i in range(n)
    ]
    raw_s = np.array([0.6, 0.7, 0.8, 0.5, 0.9], dtype=np.float32)
    raw_e = np.array([0.5, 0.8, 0.7, 0.4, 0.85], dtype=np.float32)
    raw_g = np.array([0.1, 0.9, 0.0, 0.3, 0.8], dtype=np.float32)

    struct_norm = np.random.randn(n, 79).astype(np.float32)
    struct_norm /= np.linalg.norm(struct_norm, axis=1, keepdims=True)
    semantic_norm = np.random.randn(n, 384).astype(np.float32)
    semantic_norm /= np.linalg.norm(semantic_norm, axis=1, keepdims=True)
    graph_embs = np.random.randn(n, 64).astype(np.float32)
    graph_embs /= np.linalg.norm(graph_embs, axis=1, keepdims=True)

    node_stats = {
        f"m_{i}": {"degree": 4, "useful_edges": 3 if i != 2 else 0, "has_fav_connection": (i % 2 == 1), "has_diffusion": True}
        for i in range(n)
    }

    fused_scores, hybrid_matrix, diags = execute_adaptive_fusion(
        items=items,
        raw_s_scores=raw_s,
        raw_e_scores=raw_e,
        raw_g_scores=raw_g,
        struct_norm=struct_norm,
        semantic_norm=semantic_norm,
        graph_embs=graph_embs,
        graph_node_stats=node_stats,
        crafts_by_key={},
        user_history_len=12
    )

    assert len(fused_scores) == n
    assert hybrid_matrix.shape == (n, 79 + 384 + 64)
    # Check hybrid matrix unit norm
    norms = np.linalg.norm(hybrid_matrix, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4)

    assert len(diags) == n
    for d in diags:
        assert "confidence" in d
        assert "effective_weights" in d
        assert "agreement_score" in d
        assert "is_exploratory" in d
        assert "low_evidence" in d
        weights_sum = sum(d["effective_weights"].values())
        assert pytest.approx(weights_sum, abs=1e-3) == 1.0

    # m_2 had 0 useful edges in graph -> graph weight should be minimal
    assert diags[2]["effective_weights"]["graph"] < 0.05
