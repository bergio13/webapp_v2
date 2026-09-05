"""
tests/test_negative_mode_service.py — Unit and integration tests for
Multi-Mode Negative Preference Engine & Feature-Level Veto System
"""

import pytest
import numpy as np
from services.negative_mode_service import (
    classify_negative_item,
    extract_genre_and_director_aversions,
    cluster_negative_modes,
    compute_multi_mode_negative_risk,
    evaluate_feature_level_veto,
    execute_negative_mode_pipeline,
    DISLIKE_TASTE_MISMATCH,
    DISLIKE_LOW_QUALITY,
    DISLIKE_HYBRID,
    EVIDENCE_EXPLICIT_RATING,
    EVIDENCE_ABANDONED,
    EVIDENCE_CARD_REJECT,
    EVIDENCE_IMPLICIT_DECAY,
)


def test_classify_taste_mismatch_vs_low_quality():
    # 1. Acclaimed film rated 1-star -> TASTE_MISMATCH ("Not for me")
    midsommar = {
        "title": "Midsommar",
        "p_year": 2019,
        "director": "Ari Aster",
        "genre": "Horror, Mystery",
        "rating": 1,
        "vote_average": 7.1
    }
    prof_taste = classify_negative_item(midsommar, pool_index=0)
    assert prof_taste.dislike_type == DISLIKE_TASTE_MISMATCH
    assert prof_taste.confidence >= 0.85
    assert prof_taste.is_abandoned is False

    # 2. Shoddy film rated 1-star -> LOW_QUALITY ("Execution failure")
    sharknado = {
        "title": "Sharknado 4",
        "p_year": 2016,
        "director": "Anthony C. Ferrante",
        "genre": "Comedy, Sci-Fi",
        "rating": 1,
        "vote_average": 4.1
    }
    prof_qual = classify_negative_item(sharknado, pool_index=1)
    assert prof_qual.dislike_type == DISLIKE_LOW_QUALITY


def test_classify_abandoned_and_evidence_sources():
    # Abandoned / DNF film gets 1.3x weight boost
    abandoned_movie = {
        "title": "Unbearable Movie",
        "p_year": 2022,
        "director": "Unknown",
        "genre": "Comedy",
        "rating": 1,
        "status": "abandoned after 20 mins"
    }
    prof = classify_negative_item(abandoned_movie, pool_index=2)
    assert prof.is_abandoned is True
    assert prof.evidence_source == EVIDENCE_ABANDONED
    assert prof.evidence_weight >= 1.9  # 1.75 * 1.30 = ~2.27

    # Card reject
    reject_item = {
        "title": "Swapped Card",
        "p_year": 2020,
        "director": "Director X",
        "genre": "Action",
        "is_card_reject": True
    }
    prof_rej = classify_negative_item(reject_item, pool_index=3)
    assert prof_rej.evidence_source == EVIDENCE_CARD_REJECT
    assert prof_rej.confidence == 0.80

    # Implicit decay
    implicit_item = {
        "title": "Stale Movie",
        "p_year": 2015,
        "genre": "Drama",
        "is_implicit": True
    }
    prof_imp = classify_negative_item(implicit_item, pool_index=4)
    assert prof_imp.evidence_source == EVIDENCE_IMPLICIT_DECAY
    assert prof_imp.confidence <= 0.40


def test_positive_counter_evidence_protects_loved_genres():
    # User has 4 Sci-Fi masterpieces (5★) and 1 terrible Sci-Fi movie (1★)
    # User has 0 Musical films (5★) and 2 terrible Musical films (1★)
    pool = [
        {"id": 1, "title": "Blade Runner", "director": "Ridley Scott", "genre": "Sci-Fi", "rating": 5, "is_watched": True},
        {"id": 2, "title": "2001: A Space Odyssey", "director": "Stanley Kubrick", "genre": "Sci-Fi", "rating": 5, "is_watched": True},
        {"id": 3, "title": "Solaris", "director": "Andrei Tarkovsky", "genre": "Sci-Fi", "rating": 5, "is_watched": True},
        {"id": 4, "title": "Arrival", "director": "Denis Villeneuve", "genre": "Sci-Fi", "rating": 5, "is_watched": True},
        # 1-star bad sci-fi
        {"id": 5, "title": "Battlefield Earth", "director": "Roger Christian", "genre": "Sci-Fi", "rating": 1, "is_watched": True, "vote_average": 3.2},
        # 1-star musicals
        {"id": 6, "title": "Cats", "director": "Tom Hooper", "genre": "Musical", "rating": 1, "is_watched": True, "vote_average": 3.0},
        {"id": 7, "title": "From Justin to Kelly", "director": "Robert Iscove", "genre": "Musical", "rating": 1, "is_watched": True, "vote_average": 2.5}
    ]

    neg_profiles = [
        classify_negative_item(pool[4], pool_index=4),
        classify_negative_item(pool[5], pool_index=5),
        classify_negative_item(pool[6], pool_index=6)
    ]

    aversions = extract_genre_and_director_aversions(pool, neg_profiles)

    # Sci-Fi must be in loved_genres and NOT in confirmed_genre_aversions
    assert "sci-fi" in aversions.loved_genres
    assert "sci-fi" not in aversions.confirmed_genre_aversions

    # Musical must be a confirmed genre aversion
    assert "musical" in aversions.confirmed_genre_aversions
    assert aversions.confirmed_genre_aversions["musical"] >= 0.70

    # Roger Christian must be in confirmed director aversions, Denis Villeneuve in loved_directors
    assert "roger christian" in aversions.confirmed_director_aversions


def test_cluster_multiple_distinct_negative_modes():
    # 2 completely distinct negative items (Slapstick Comedy vs Torture Horror)
    # They should NOT be collapsed into 1 centroid!
    prof1 = classify_negative_item({
        "title": "Grown Ups 2",
        "genre": "Comedy",
        "director": "Dennis Dugan",
        "rating": 1,
        "vote_average": 5.4
    }, pool_index=0)

    prof2 = classify_negative_item({
        "title": "Saw 3D",
        "genre": "Horror",
        "director": "Kevin Greutert",
        "rating": 1,
        "vote_average": 5.5
    }, pool_index=1)

    # Orthogonal vectors for Comedy vs Horror
    hybrid_matrix = np.array([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0]
    ], dtype=np.float32)

    modes = cluster_negative_modes([prof1, prof2], hybrid_matrix)
    assert len(modes) == 2
    assert modes[0].mode_id == 0
    assert modes[1].mode_id == 1

    # Verify centroids preserve the distinct modes
    assert np.allclose(modes[0].centroid, [1.0, 0.0, 0.0, 0.0], atol=1e-3)
    assert np.allclose(modes[1].centroid, [0.0, 1.0, 0.0, 0.0], atol=1e-3)


def test_compute_multi_mode_negative_risk():
    # Setup 2 negative modes
    # Mode 0 at [1, 0], confidence 0.9
    # Mode 1 at [0, 1], confidence 0.7
    from services.negative_mode_service import NegativeMode

    mode0 = NegativeMode(
        mode_id=0, label="Mode 0", centroid=np.array([1.0, 0.0], dtype=np.float32),
        confidence=0.90, dislike_type=DISLIKE_TASTE_MISMATCH, member_indices=[0],
        titles=["Film A"], dominant_genres=["Horror"], dominant_directors=[], cohesion=1.0
    )
    mode1 = NegativeMode(
        mode_id=1, label="Mode 1", centroid=np.array([0.0, 1.0], dtype=np.float32),
        confidence=0.70, dislike_type=DISLIKE_LOW_QUALITY, member_indices=[1],
        titles=["Film B"], dominant_genres=["Comedy"], dominant_directors=[], cohesion=1.0
    )

    # Candidate 0 aligns with Mode 0: [1, 0] -> risk should be 0.90 * 1.0 = 0.90
    # Candidate 1 aligns with Mode 1: [0, 1] -> risk should be 0.70 * 1.0 = 0.70
    # Candidate 2 aligns with neither: [-1, 0] -> risk should be 0.0
    candidates = np.array([
        [1.0, 0.0],
        [0.0, 1.0],
        [-1.0, 0.0]
    ], dtype=np.float32)

    neg_risk, closest_modes, sim_mat = compute_multi_mode_negative_risk(candidates, [mode0, mode1])

    assert pytest.approx(neg_risk[0], abs=1e-3) == 0.90
    assert closest_modes[0] == 0

    assert pytest.approx(neg_risk[1], abs=1e-3) == 0.70
    assert closest_modes[1] == 1

    assert pytest.approx(neg_risk[2], abs=1e-3) == 0.0


def test_feature_level_veto_gates():
    from services.negative_mode_service import AversionProfile, NegativeMode

    aversions = AversionProfile(
        confirmed_genre_aversions={"musical": 0.85},
        loved_genres={"sci-fi"},
        confirmed_director_aversions={"uwe boll": 0.95},
        loved_directors={"denis villeneuve"}
    )

    taste_mode = NegativeMode(
        mode_id=0, label="Torture Horror", centroid=np.array([1.0, 0.0], dtype=np.float32),
        confidence=0.90, dislike_type=DISLIKE_TASTE_MISMATCH, member_indices=[0],
        titles=["Hostel"], dominant_genres=["Horror"], dominant_directors=[], cohesion=1.0,
        is_taste_mismatch=True
    )
    qual_mode = NegativeMode(
        mode_id=1, label="Cheap Comedy", centroid=np.array([0.0, 1.0], dtype=np.float32),
        confidence=0.80, dislike_type=DISLIKE_LOW_QUALITY, member_indices=[1],
        titles=["Movie 43"], dominant_genres=["Comedy"], dominant_directors=[], cohesion=1.0,
        is_low_quality=True
    )
    modes = [taste_mode, qual_mode]

    # Test 1: Candidate with disliked director gets Director Veto
    cand_director = {"title": "Alone in the Dark", "director": "Uwe Boll", "genre": "Action"}
    v_fac, is_vet, diag = evaluate_feature_level_veto(
        cand_director, np.array([0.0, 0.0]), modes, np.array([0.1, 0.1]), aversions
    )
    assert is_vet is True
    assert v_fac <= 0.25
    assert any("Director Aversion" in r for r in diag["reasons"])

    # Test 2: Candidate in confirmed genre aversion gets Genre Veto
    cand_musical = {"title": "Les Miserables", "director": "Tom Hooper", "genre": "Musical"}
    v_fac, is_vet, diag = evaluate_feature_level_veto(
        cand_musical, np.array([0.0, 0.0]), modes, np.array([0.1, 0.1]), aversions
    )
    assert is_vet is True
    assert v_fac <= 0.35
    assert any("Genre Aversion: Musical" in r for r in diag["reasons"])

    # Test 3: Candidate in loved genre (Sci-Fi) is PROTECTED even if paired with minor negative
    cand_scifi = {"title": "Dune: Part Two", "director": "Denis Villeneuve", "genre": "Sci-Fi"}
    v_fac, is_vet, diag = evaluate_feature_level_veto(
        cand_scifi, np.array([0.0, 0.0]), modes, np.array([0.1, 0.1]), aversions
    )
    assert is_vet is False
    assert v_fac == 1.0

    # Test 4: Low Quality candidate with low TMDB rating gets Quality Gate Veto
    cand_bad_comedy = {"title": "Disaster Movie", "director": "Aaron Seltzer", "genre": "Comedy", "vote_average": 2.1}
    v_fac, is_vet, diag = evaluate_feature_level_veto(
        cand_bad_comedy, np.array([0.0, 1.0]), modes, np.array([0.0, 0.85]), aversions
    )
    assert is_vet is True
    assert v_fac <= 0.40
    assert any("Execution Quality Risk" in r for r in diag["reasons"])

    # Test 5: Masterpiece candidate in the same space bypasses Quality Gate!
    cand_masterpiece_comedy = {"title": "Some Like It Hot", "director": "Billy Wilder", "genre": "Comedy", "vote_average": 8.2}
    v_fac, is_vet, diag = evaluate_feature_level_veto(
        cand_masterpiece_comedy, np.array([0.0, 1.0]), modes, np.array([0.0, 0.70]), aversions
    )
    assert is_vet is False
    assert v_fac == 1.0


def test_full_negative_pipeline_execution():
    pool = [
        # User watched positive
        {"id": 1, "title": "Inception", "director": "Christopher Nolan", "genre": "Sci-Fi, Action", "rating": 5, "is_watched": True},
        {"id": 2, "title": "Interstellar", "director": "Christopher Nolan", "genre": "Sci-Fi, Drama", "rating": 5, "is_watched": True},
        # User watched negative: 1 Taste Mismatch (Midsommar), 1 Low Quality (Disaster Movie)
        {"id": 3, "title": "Midsommar", "director": "Ari Aster", "genre": "Horror", "rating": 1, "is_watched": True, "vote_average": 7.1, "category": "void_repulsor"},
        {"id": 4, "title": "Disaster Movie", "director": "Jason Friedberg", "genre": "Comedy", "rating": 1, "is_watched": True, "vote_average": 2.1, "category": "void_repulsor"},
        # Candidate A: High Sci-Fi match (should score low negative risk)
        {"id": 5, "title": "Tenet", "director": "Christopher Nolan", "genre": "Sci-Fi, Action", "rating": 0, "is_watched": False, "vote_average": 7.5},
        # Candidate B: Horror like Midsommar (should trigger taste mismatch risk)
        {"id": 6, "title": "Hereditary", "director": "Ari Aster", "genre": "Horror", "rating": 0, "is_watched": False, "vote_average": 7.3},
    ]

    # Create synthetic 4D hybrid matrix
    # Dim 0: Sci-Fi, Dim 1: Horror, Dim 2: Comedy, Dim 3: Drama
    hybrid_matrix = np.array([
        [0.9, 0.1, 0.0, 0.1],  # Inception
        [0.9, 0.0, 0.0, 0.4],  # Interstellar
        [0.0, 0.95, 0.0, 0.1], # Midsommar (Horror)
        [0.0, 0.0, 0.95, 0.0], # Disaster Movie (Comedy)
        [0.9, 0.1, 0.0, 0.1],  # Tenet (Sci-Fi)
        [0.0, 0.95, 0.0, 0.1], # Hereditary (Horror)
    ], dtype=np.float32)
    hybrid_matrix /= (np.linalg.norm(hybrid_matrix, axis=1, keepdims=True) + 1e-9)

    neg_risks, veto_factors, diagnostics, modes = execute_negative_mode_pipeline(pool, hybrid_matrix)

    assert len(modes) == 2  # Horror vs Comedy
    # Tenet must have low negative risk
    assert neg_risks[4] < 0.20
    assert veto_factors[4] == 1.0

    # Hereditary aligns with Midsommar horror mode -> high negative risk
    assert neg_risks[5] >= 0.70
    assert diagnostics[5]["is_vetoed"] is True
