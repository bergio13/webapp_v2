"""
test_cosmos_service.py — Unit & Integration tests for Cinephile Cosmos Service
"""

import pytest
import numpy as np
from services.cosmos_service import (
    build_taste_cosmos_data,
    get_probe_recommendations,
    _extract_feature_vector,
    _generate_sector_label
)


def test_extract_feature_vector():
    movie = {
        "movie": "Solaris",
        "p_year": 1972,
        "director": "Andrei Tarkovsky",
        "genre": "Sci-Fi, Drama",
        "tags": "philosophical, atmospheric, space",
        "tv_show": 0
    }
    director_indexer = {"andreitarkovsky": 1}
    vec = _extract_feature_vector(movie, director_indexer)
    assert len(vec) > 30
    assert not any(pytest.approx(x) is None for x in vec)


def test_generate_sector_label():
    items = [
        {"title": "Blade Runner 2049", "genre": "Sci-Fi, Adventure", "year": 2017, "director": "Denis Villeneuve", "tags": "cyberpunk, futuristic"},
        {"title": "Ghost in the Shell", "genre": "Animation, Sci-Fi", "year": 1995, "director": "Mamoru Oshii", "tags": "anime, cyberpunk"}
    ]
    label = _generate_sector_label(items, 0, set(), is_macro=False)
    assert "name" in label
    assert "code" in label
    assert "color" in label


def test_build_taste_cosmos_data_mocked(monkeypatch):
    # Mock get_movies to return sample user history
    sample_movies = [
        {"id": 1, "movie": "Blade Runner", "p_year": 1982, "director": "Ridley Scott", "genre": "Sci-Fi, Thriller", "rating": 5, "poster": "http://example.com/br.jpg", "tv_show": 0, "cinema": 0, "rewatch": 0},
        {"id": 2, "movie": "Alien", "p_year": 1979, "director": "Ridley Scott", "genre": "Sci-Fi, Horror", "rating": 5, "poster": "http://example.com/alien.jpg", "tv_show": 0, "cinema": 0, "rewatch": 0},
        {"id": 3, "movie": "Chungking Express", "p_year": 1994, "director": "Wong Kar-wai", "genre": "Drama, Romance", "rating": 4, "poster": "http://example.com/ce.jpg", "tv_show": 0, "cinema": 0, "rewatch": 0},
        {"id": 4, "movie": "In the Mood for Love", "p_year": 2000, "director": "Wong Kar-wai", "genre": "Drama, Romance", "rating": 5, "poster": "http://example.com/itmfl.jpg", "tv_show": 0, "cinema": 0, "rewatch": 0},
    ]
    monkeypatch.setattr("services.cosmos_service.get_movies", lambda uid: sample_movies)
    monkeypatch.setattr("services.cosmos_service.get_friends", lambda uid: [])
    monkeypatch.setattr("services.cosmos_service.get_or_create_personal_watchlist", lambda uid: None)
    monkeypatch.setattr("services.cosmos_service.get_watchlist_items", lambda wid: [])
    monkeypatch.setattr("services.tmdb_service.get_recommendations_for_title", lambda *a, **k: [])
    monkeypatch.setattr("services.tmdb_service.get_director_filmography", lambda *a, **k: [])
    monkeypatch.setattr("services.cosmos_service.batch_get_movie_crafts", lambda movies: {})

    result = build_taste_cosmos_data(user_id=999, force_refresh=True)

    assert result["success"] is True
    assert len(result["stars"]) >= len(sample_movies)
    assert len(result["sectors"]) >= 1
    assert "stats" in result
    assert result["stats"]["watched_stars"] >= 4

    # Verify each star has coordinates and valid metadata
    assert "calibration" in result["stats"]
    for star in result["stars"]:
        assert "x" in star and isinstance(star["x"], float)
        assert "y" in star and isinstance(star["y"], float)
        assert "title" in star
        assert "match_pct" in star
        assert "match_score" in star
        assert 50 <= star["match_score"] <= 100
        assert "calibrated_prob" in star
        assert 0.0 <= star["calibrated_prob"] <= 1.0
        assert "calibration_meta" in star


def test_negative_gravity_repulsor(monkeypatch):
    # Test user with 1-star low rating creating cosmic void
    sample_movies = [
        {"id": 1, "movie": "Blade Runner", "p_year": 1982, "director": "Ridley Scott", "genre": "Sci-Fi", "rating": 5, "poster": "", "tv_show": 0},
        {"id": 2, "movie": "Bad Horror Movie", "p_year": 2010, "director": "Unknown", "genre": "Horror", "rating": 1, "poster": "", "tv_show": 0},
    ]
    monkeypatch.setattr("services.cosmos_service.get_movies", lambda uid: sample_movies)
    monkeypatch.setattr("services.cosmos_service.get_friends", lambda uid: [])
    monkeypatch.setattr("services.cosmos_service.get_or_create_personal_watchlist", lambda uid: None)
    monkeypatch.setattr("services.cosmos_service.get_watchlist_items", lambda wid: [])
    monkeypatch.setattr("services.tmdb_service.get_recommendations_for_title", lambda *a, **k: [])
    monkeypatch.setattr("services.tmdb_service.get_director_filmography", lambda *a, **k: [])
    monkeypatch.setattr("services.cosmos_service.batch_get_movie_crafts", lambda movies: {})

    galaxy = build_taste_cosmos_data(user_id=888, force_refresh=True)
    assert galaxy["success"] is True
    
    # Check void repulsor category
    void_stars = [s for s in galaxy["stars"] if s.get("category") == "void_repulsor"]
    assert len(void_stars) == 1
    assert void_stars[0]["title"] == "Bad Horror Movie"


def test_probe_recommendations(monkeypatch):
    sample_movies = [
        {"id": 1, "movie": "Blade Runner", "p_year": 1982, "director": "Ridley Scott", "genre": "Sci-Fi", "rating": 5, "poster": "", "tv_show": 0}
    ]
    monkeypatch.setattr("services.cosmos_service.get_movies", lambda uid: sample_movies)
    monkeypatch.setattr("services.cosmos_service.get_friends", lambda uid: [])
    monkeypatch.setattr("services.cosmos_service.get_or_create_personal_watchlist", lambda uid: None)
    monkeypatch.setattr("services.cosmos_service.get_watchlist_items", lambda wid: [])
    monkeypatch.setattr("services.tmdb_service.get_recommendations_for_title", lambda *a, **k: [])
    monkeypatch.setattr("services.tmdb_service.get_director_filmography", lambda *a, **k: [])

    probe = get_probe_recommendations(target_x=100.0, target_y=100.0, user_id=999, limit=4)
    assert probe["success"] is True
    assert len(probe["recommendations"]) <= 4


def test_semantic_embedding_service_and_cache():
    from services.embedding_service import compute_semantic_embeddings
    movies = [
        {"title": "Ghost in the Shell", "p_year": 1995, "director": "Mamoru Oshii", "genre": "Animation, Sci-Fi", "overview": "A cyborg policewoman hunts a hacker."},
        {"title": "Amelie", "p_year": 2001, "director": "Jean-Pierre Jeunet", "genre": "Comedy, Romance", "overview": "An innocent and naive girl in Paris decides to help those around her."}
    ]
    vecs = compute_semantic_embeddings(movies)
    assert vecs.shape == (2, 384)
    assert not any(pytest.approx(x) is None for x in vecs.flatten())

    # Verify SQLite cached retrieval is identical
    vecs_cached = compute_semantic_embeddings(movies)
    assert np.allclose(vecs, vecs_cached, atol=1e-5)


def test_multi_modal_centroids(monkeypatch):
    # Test user with 2 distinct taste modes (Cyberpunk Anime vs Romance Drama)
    sample_movies = [
        # Mode A (Anime / Sci-Fi)
        {"id": 1, "movie": "Ghost in the Shell", "p_year": 1995, "director": "Mamoru Oshii", "genre": "Animation, Sci-Fi", "rating": 5, "poster": "", "tv_show": 0},
        {"id": 2, "movie": "Akira", "p_year": 1988, "director": "Katsuhiro Otomo", "genre": "Animation, Sci-Fi", "rating": 5, "poster": "", "tv_show": 0},
        {"id": 3, "movie": "Neon Genesis Evangelion", "p_year": 1997, "director": "Hideaki Anno", "genre": "Animation, Sci-Fi", "rating": 5, "poster": "", "tv_show": 0},
        {"id": 4, "movie": "Perfect Blue", "p_year": 1997, "director": "Satoshi Kon", "genre": "Animation, Thriller", "rating": 5, "poster": "", "tv_show": 0},
        # Mode B (French / Romance Drama)
        {"id": 5, "movie": "Portrait of a Lady on Fire", "p_year": 2019, "director": "Celine Sciamma", "genre": "Drama, Romance", "rating": 5, "poster": "", "tv_show": 0},
        {"id": 6, "movie": "Amelie", "p_year": 2001, "director": "Jean-Pierre Jeunet", "genre": "Comedy, Romance", "rating": 5, "poster": "", "tv_show": 0},
        {"id": 7, "movie": "La La Land", "p_year": 2016, "director": "Damien Chazelle", "genre": "Drama, Romance", "rating": 5, "poster": "", "tv_show": 0},
        {"id": 8, "movie": "Before Sunrise", "p_year": 1995, "director": "Richard Linklater", "genre": "Drama, Romance", "rating": 5, "poster": "", "tv_show": 0},
    ]
    monkeypatch.setattr("services.cosmos_service.get_movies", lambda uid: sample_movies)
    monkeypatch.setattr("services.cosmos_service.get_friends", lambda uid: [])
    monkeypatch.setattr("services.cosmos_service.get_or_create_personal_watchlist", lambda uid: None)
    monkeypatch.setattr("services.cosmos_service.get_watchlist_items", lambda wid: [])
    monkeypatch.setattr("services.tmdb_service.get_recommendations_for_title", lambda *a, **k: [])
    monkeypatch.setattr("services.tmdb_service.get_director_filmography", lambda *a, **k: [])
    monkeypatch.setattr("services.cosmos_service.batch_get_movie_crafts", lambda movies: {})

    galaxy = build_taste_cosmos_data(user_id=777, force_refresh=True)
    assert galaxy["success"] is True
    
    # Both pure Anime and pure Romance masterworks should score high match percentages (>80%)
    for star in galaxy["stars"][:8]:
        assert star["match_pct"] >= 80


def test_craft_service_and_cache():
    from services.craft_service import store_cached_craft_credit, _normalize_key, get_cached_craft_credit
    sample_craft = {
        "movie_key": _normalize_key("Blade Runner 2049", 2017),
        "tmdb_id": 335984,
        "title": "Blade Runner 2049",
        "year": "2017",
        "director": "Denis Villeneuve",
        "cinematographer": "Roger Deakins",
        "composer": "Hans Zimmer, Benjamin Wallfisch",
        "screenwriter": "Hampton Fancher, Michael Green",
        "editor": "Joe Walker",
        "lead_actors": "Ryan Gosling, Harrison Ford",
        "studios": "Alcon Entertainment, Columbia Pictures"
    }
    store_cached_craft_credit(sample_craft)

    # Test SQLite cache lookup
    cached = get_cached_craft_credit(_normalize_key("Blade Runner 2049", 2017))
    assert cached is not None
    assert cached["cinematographer"] == "Roger Deakins"
    assert cached["director"] == "Denis Villeneuve"
    assert "Hans Zimmer" in cached["composer"]


def test_lightgcn_knowledge_graph():
    from services.graph_service import build_and_run_lightgcn
    sample_movies = [
        {"id": 101, "title": "Sicario", "year": 2015, "director": "Denis Villeneuve", "genre": "Crime, Drama", "rating": 5, "is_watched": True},
        {"id": 102, "title": "Arrival", "year": 2016, "director": "Denis Villeneuve", "genre": "Sci-Fi, Drama", "rating": 0, "is_watched": False},
        {"id": 103, "title": "Random Unrelated", "year": 2020, "director": "Nobody", "genre": "Comedy", "rating": 0, "is_watched": False}
    ]
    crafts = {
        "sicario_2015": {"director": "Denis Villeneuve", "cinematographer": "Roger Deakins", "composer": "Johann Johannsson"},
        "arrival_2016": {"director": "Denis Villeneuve", "cinematographer": "Bradford Young", "composer": "Johann Johannsson"},
        "randomunrelated_2020": {"director": "Nobody", "cinematographer": "Unknown", "composer": "Unknown"}
    }
    embs, affinities, explanations = build_and_run_lightgcn(sample_movies, crafts, user_id=15)
    assert embs.shape == (3, 64)
    # Arrival shares both Denis Villeneuve and Johann Johannsson with 5-star Sicario
    assert affinities[1] > affinities[2]
    assert "Denis Villeneuve" in explanations.get("102", "") or "Johann" in explanations.get("102", "")


def test_cinephile_corpus_service():
    from services.corpus_service import get_all_curated_films
    films = get_all_curated_films()
    assert len(films) >= 50
    titles = [f["title"] for f in films]
    assert "Tokyo Story" in titles
    assert "Vertigo" in titles
    assert "Seven Samurai" in titles
    assert "In the Mood for Love" in titles


def test_3tier_frontier_distribution(monkeypatch):
    from services.cosmos_service import _fetch_autonomous_candidates
    sample_movies = [
        {"id": 1, "movie": "Blade Runner", "p_year": 1982, "director": "Ridley Scott", "genre": "Sci-Fi, Thriller", "rating": 5},
        {"id": 2, "movie": "Amelie", "p_year": 2001, "director": "Jean-Pierre Jeunet", "genre": "Comedy, Romance", "rating": 5}
    ]
    monkeypatch.setattr("services.cosmos_service.get_friends", lambda uid: [])
    monkeypatch.setattr("services.tmdb_service.get_recommendations_for_title", lambda *a, **k: [])

    candidates = _fetch_autonomous_candidates(user_id=123, user_movies=sample_movies)
    assert len(candidates) >= 30
    
    # Verify all 3 tiers exist in the candidate pool
    frontier_types = set(c.get("frontier_type") for c in candidates)
    assert "resonator" in frontier_types
    assert "crossover" in frontier_types
    assert "quantum_frontier" in frontier_types


def test_stratified_seed_extraction():
    from services.cosmos_service import _get_stratified_seed_items
    sample_movies = [
        {"movie": f"SciFi Movie {i}", "p_year": 2000 + i, "director": "Ridley Scott", "genre": "Sci-Fi", "rating": 5, "rewatch": 1, "tv_show": 0}
        for i in range(5)
    ] + [
        {"movie": f"Noir Film {i}", "p_year": 1990 + i, "director": "David Fincher", "genre": "Crime, Thriller", "rating": 4, "rewatch": 0, "tv_show": 0}
        for i in range(5)
    ] + [
        {"movie": "Severance", "p_year": 2022, "director": "Ben Stiller", "genre": "Drama, Sci-Fi", "rating": 5, "rewatch": 0, "tv_show": 1}
    ]

    seeds = _get_stratified_seed_items(sample_movies)
    assert len(seeds) >= 5
    titles = [s[0] for s in seeds]
    assert "Severance" in titles
    # Check is_tv flag
    sev_item = next(s for s in seeds if s[0] == "Severance")
    assert sev_item[2] is True


def test_sqlite_recommendations_cache():
    from services.tmdb_service import get_cached_recommendations, save_cached_recommendations
    test_recs = [
        {"title": "Test Rec 1", "year": "2020", "director": "Test Dir", "genre": "Sci-Fi", "poster": "http://example.com/p.jpg", "tv_show": 0}
    ]
    save_cached_recommendations("Test Seed Title XYZ", 2021, False, test_recs)
    cached = get_cached_recommendations("Test Seed Title XYZ", 2021, False)
    assert cached is not None
    assert len(cached) == 1
    assert cached[0]["title"] == "Test Rec 1"


def test_candidates_instant_execution_speed(monkeypatch):
    import time
    from services.cosmos_service import _fetch_autonomous_candidates
    sample_movies = [
        {"id": i, "movie": f"Film {i}", "p_year": 2000 + i, "director": "Auteur", "genre": "Drama", "rating": 5}
        for i in range(20)
    ]
    monkeypatch.setattr("services.cosmos_service.get_friends", lambda uid: [])

    t0 = time.time()
    candidates = _fetch_autonomous_candidates(user_id=123, user_movies=sample_movies)
    elapsed = time.time() - t0

    assert len(candidates) > 0
    # Candidate fetching should be instantaneous (< 0.6s on cold test run)
    assert elapsed < 0.60


def test_watchlist_year_differentiation_prevent_collision(monkeypatch):
    from services.cosmos_service import build_taste_cosmos_data

    sample_watched = [
        {"id": 1, "movie": "Blade Runner", "p_year": 1982, "director": "Ridley Scott", "genre": "Sci-Fi", "rating": 5, "poster": "", "tv_show": 0}
    ]
    sample_watchlist = [
        {"id": 45, "title": "Metropolis", "p_year": "1927", "director": "Fritz Lang", "poster": "http://img/1927.jpg"}
    ]
    candidate_recs = [
        {"title": "Metropolis", "year": "2001", "director": "Rintaro", "genre": "Animation, Sci-Fi", "poster": "http://img/2001.jpg"}
    ]

    monkeypatch.setattr("services.cosmos_service.get_movies", lambda uid: sample_watched)
    monkeypatch.setattr("services.cosmos_service._fetch_user_watchlist_safe", lambda uid: sample_watchlist)
    monkeypatch.setattr("services.cosmos_service._fetch_autonomous_candidates", lambda uid, movies: candidate_recs)

    res = build_taste_cosmos_data(user_id=999, force_refresh=True)
    stars = res.get("stars", [])

    metropolis_1927 = next((s for s in stars if s.get("title") == "Metropolis" and str(s.get("year")) == "1927"), None)
    metropolis_2001 = next((s for s in stars if s.get("title") == "Metropolis" and str(s.get("year")) == "2001"), None)

    assert metropolis_1927 is not None
    assert metropolis_1927["is_watchlist"] is True
    assert metropolis_1927["category"] == "watchlist"

    assert metropolis_2001 is not None
    # 2001 recommendation should NOT be marked as watchlist item
    assert metropolis_2001["is_watchlist"] is False
    assert metropolis_2001["category"] == "uncharted_beacon"


def test_showrunner_and_twilight_franchise_no_false_links(monkeypatch):
    from services.cosmos_service import build_taste_cosmos_data

    sample_watched = [
        {"id": 1, "movie": "The Twilight Zone", "p_year": 1959, "director": "Showrunner", "genre": "Sci-Fi", "rating": 5, "poster": "", "tv_show": 1},
        {"id": 2, "movie": "Twilight of the Gods", "p_year": 2024, "director": "Showrunner", "genre": "Animation", "rating": 4, "poster": "", "tv_show": 1},
        {"id": 3, "movie": "Severance", "p_year": 2022, "director": "Showrunner", "genre": "Sci-Fi", "rating": 5, "poster": "", "tv_show": 1}
    ]

    monkeypatch.setattr("services.cosmos_service.get_movies", lambda uid: sample_watched)
    monkeypatch.setattr("services.cosmos_service._fetch_user_watchlist_safe", lambda uid: [])
    monkeypatch.setattr("services.cosmos_service._fetch_autonomous_candidates", lambda uid, movies: [])

    res = build_taste_cosmos_data(user_id=888, force_refresh=True)
    links = res.get("links", [])

    # 1. Ensure no links have 'Directorial Lineage: Showrunner'
    for link in links:
        assert "showrunner" not in link.get("reason", "").lower()
        # 2. Ensure The Twilight Zone and Twilight of the Gods are NOT linked as Franchise Canon: Twilight
        if "twilight" in link.get("reason", "").lower():
            assert "franchise canon: twilight" not in link.get("reason", "").lower()


def test_adaptive_fusion_diagnostics_on_stars(monkeypatch):
    from services.cosmos_service import build_taste_cosmos_data

    sample_movies = [
        {"id": 1, "movie": "Blade Runner", "p_year": 1982, "director": "Ridley Scott", "genre": "Sci-Fi", "rating": 5, "poster": "", "tv_show": 0},
        {"id": 2, "movie": "Alien", "p_year": 1979, "director": "Ridley Scott", "genre": "Sci-Fi, Horror", "rating": 4, "poster": "", "tv_show": 0},
    ]
    monkeypatch.setattr("services.cosmos_service.get_movies", lambda uid: sample_movies)
    monkeypatch.setattr("services.cosmos_service.get_friends", lambda uid: [])
    monkeypatch.setattr("services.cosmos_service.get_or_create_personal_watchlist", lambda uid: None)
    monkeypatch.setattr("services.cosmos_service.get_watchlist_items", lambda wid: [])
    monkeypatch.setattr("services.tmdb_service.get_recommendations_for_title", lambda *a, **k: [])
    monkeypatch.setattr("services.tmdb_service.get_director_filmography", lambda *a, **k: [])
    monkeypatch.setattr("services.cosmos_service.batch_get_movie_crafts", lambda movies: {})

    res = build_taste_cosmos_data(user_id=777, force_refresh=True)
    stars = res.get("stars", [])
    assert len(stars) > 0

    for s in stars:
        assert "confidence" in s
        assert "effective_weights" in s
        assert "agreement_score" in s
        assert "is_exploratory" in s
        assert "low_evidence" in s

        weights = s["effective_weights"]
        assert "structured" in weights and "semantic" in weights and "graph" in weights
        total_w = weights["structured"] + weights["semantic"] + weights["graph"]
        assert pytest.approx(total_w, abs=0.02) == 1.0

        conf = s["confidence"]
        assert "structured" in conf and "semantic" in conf and "graph" in conf
        assert 0.05 <= conf["structured"] <= 1.0
        assert 0.05 <= conf["semantic"] <= 1.0
        assert 0.05 <= conf["graph"] <= 1.0


def test_multi_mode_negative_clustering_in_galaxy(monkeypatch):
    # User with 2 distinct negative modes: Slapstick comedy + Torture horror
    sample_movies = [
        {"id": 1, "movie": "Blade Runner", "p_year": 1982, "director": "Ridley Scott", "genre": "Sci-Fi", "rating": 5, "poster": "", "tv_show": 0},
        {"id": 2, "movie": "Arrival", "p_year": 2016, "director": "Denis Villeneuve", "genre": "Sci-Fi", "rating": 5, "poster": "", "tv_show": 0},
        {"id": 3, "movie": "Grown Ups 2", "p_year": 2013, "director": "Dennis Dugan", "genre": "Comedy", "rating": 1, "poster": "", "tv_show": 0, "vote_average": 5.4},
        {"id": 4, "movie": "Saw 3D", "p_year": 2010, "director": "Kevin Greutert", "genre": "Horror", "rating": 1, "poster": "", "tv_show": 0, "vote_average": 5.5},
    ]
    monkeypatch.setattr("services.cosmos_service.get_movies", lambda uid: sample_movies)
    monkeypatch.setattr("services.cosmos_service.get_friends", lambda uid: [])
    monkeypatch.setattr("services.cosmos_service.get_or_create_personal_watchlist", lambda uid: None)
    monkeypatch.setattr("services.cosmos_service.get_watchlist_items", lambda wid: [])
    monkeypatch.setattr("services.tmdb_service.get_recommendations_for_title", lambda *a, **k: [])
    monkeypatch.setattr("services.tmdb_service.get_director_filmography", lambda *a, **k: [])
    monkeypatch.setattr("services.cosmos_service.batch_get_movie_crafts", lambda movies: {})

    galaxy = build_taste_cosmos_data(user_id=1234, force_refresh=True)
    assert galaxy["success"] is True
    assert galaxy["stats"]["negative_modes_count"] >= 2

    # Check star diagnostics
    for s in galaxy["stars"]:
        assert "neg_risk" in s
        assert "veto_factor" in s
        assert "is_vetoed" in s
        assert "negative_diagnostics" in s


def test_probe_recommendations_excludes_vetoed_stars(monkeypatch):
    # Candidate with disliked director gets vetoed and must NOT be in probe recommendations
    sample_movies = [
        {"id": 1, "movie": "Blade Runner", "p_year": 1982, "director": "Ridley Scott", "genre": "Sci-Fi", "rating": 5, "poster": "", "tv_show": 0},
        {"id": 2, "movie": "Alone in the Dark", "p_year": 2005, "director": "Uwe Boll", "genre": "Action", "rating": 1, "poster": "", "tv_show": 0, "vote_average": 2.4},
    ]
    monkeypatch.setattr("services.cosmos_service.get_movies", lambda uid: sample_movies)
    monkeypatch.setattr("services.cosmos_service.get_friends", lambda uid: [])
    monkeypatch.setattr("services.cosmos_service.get_or_create_personal_watchlist", lambda uid: None)
    monkeypatch.setattr("services.cosmos_service.get_watchlist_items", lambda wid: [])
    cand_uwe = [{"title": "House of the Dead", "p_year": "2003", "director": "Uwe Boll", "genre": "Horror", "vote_average": 2.1, "poster": ""}]
    cand_good = [{"title": "Solaris", "p_year": "1972", "director": "Andrei Tarkovsky", "genre": "Sci-Fi", "vote_average": 8.0, "poster": ""}]
    monkeypatch.setattr("services.tmdb_service.get_recommendations_for_title", lambda *a, **k: cand_uwe + cand_good)
    monkeypatch.setattr("services.tmdb_service.get_director_filmography", lambda *a, **k: [])
    monkeypatch.setattr("services.cosmos_service.batch_get_movie_crafts", lambda movies: {})

    probe = get_probe_recommendations(target_x=0.0, target_y=0.0, user_id=1235, limit=6)
    assert probe["success"] is True
    rec_titles = [r["title"] for r in probe["recommendations"]]
    assert "House of the Dead" not in rec_titles


def test_multi_mode_positive_clustering_in_galaxy(monkeypatch):
    # User with favorites across two distinct aesthetic pillars:
    # 1. Cyberpunk / Atmospheric Sci-Fi
    # 2. Hong Kong Arthouse Romance / Drama
    sample_movies = [
        {"id": 1, "movie": "Blade Runner", "p_year": 1982, "director": "Ridley Scott", "genre": "Sci-Fi", "rating": 5, "poster": "", "tv_show": 0, "rewatch": 1, "v_date": "2026-08-01"},
        {"id": 2, "movie": "Alien", "p_year": 1979, "director": "Ridley Scott", "genre": "Sci-Fi", "rating": 5, "poster": "", "tv_show": 0, "rewatch": 0, "v_date": "2026-07-15"},
        {"id": 3, "movie": "In the Mood for Love", "p_year": 2000, "director": "Wong Kar-wai", "genre": "Drama, Romance", "rating": 5, "poster": "", "tv_show": 0, "rewatch": 1, "v_date": "2026-06-20"},
        {"id": 4, "movie": "Chungking Express", "p_year": 1994, "director": "Wong Kar-wai", "genre": "Drama, Romance", "rating": 4, "poster": "", "tv_show": 0, "rewatch": 0, "v_date": "2026-05-10"},
    ]
    monkeypatch.setattr("services.cosmos_service.get_movies", lambda uid: sample_movies)
    monkeypatch.setattr("services.cosmos_service.get_friends", lambda uid: [])
    monkeypatch.setattr("services.cosmos_service.get_or_create_personal_watchlist", lambda uid: None)
    monkeypatch.setattr("services.cosmos_service.get_watchlist_items", lambda wid: [])
    monkeypatch.setattr("services.tmdb_service.get_recommendations_for_title", lambda *a, **k: [])
    monkeypatch.setattr("services.tmdb_service.get_director_filmography", lambda *a, **k: [])
    monkeypatch.setattr("services.cosmos_service.batch_get_movie_crafts", lambda movies: {})

    galaxy = build_taste_cosmos_data(user_id=1236, force_refresh=True)
    assert galaxy["success"] is True
    assert "positive_modes_count" in galaxy["stats"]
    assert galaxy["stats"]["positive_modes_count"] >= 1

    pos_modes = galaxy["stats"]["positive_modes"]
    assert len(pos_modes) == galaxy["stats"]["positive_modes_count"]
    for m in pos_modes:
        assert "id" in m and "label" in m and "weight" in m and "size" in m
        assert m["weight"] > 0.0

    # Total weight should sum to ~1.0
    total_w = sum(m["weight"] for m in pos_modes)
    assert pytest.approx(total_w, abs=0.02) == 1.0

    # Check star-level positive mode attribution
    for s in galaxy["stars"]:
        assert "positive_mode_id" in s
        assert "positive_mode_label" in s


def test_affinity_score_explicit_precedence_and_calibration(monkeypatch):
    """
    Validates explicit grouping (s_pos - penalty) * veto * quality
    and presence of calibrated probability and match scores.
    """
    sample_movies = [
        {"id": 1, "movie": "Solaris", "p_year": 1972, "director": "Andrei Tarkovsky", "genre": "Sci-Fi, Drama", "rating": 5, "poster": "", "tv_show": 0, "rewatch": 1},
        {"id": 2, "movie": "Stalker", "p_year": 1979, "director": "Andrei Tarkovsky", "genre": "Sci-Fi, Drama", "rating": 5, "poster": "", "tv_show": 0, "rewatch": 0},
        {"id": 3, "movie": "The Mirror", "p_year": 1975, "director": "Andrei Tarkovsky", "genre": "Drama", "rating": 4, "poster": "", "tv_show": 0, "rewatch": 0},
        {"id": 4, "movie": "Terrible Slasher", "p_year": 2012, "director": "Bad Director", "genre": "Horror", "rating": 1, "poster": "", "tv_show": 0, "rewatch": 0},
    ]
    monkeypatch.setattr("services.cosmos_service.get_movies", lambda uid: sample_movies)
    monkeypatch.setattr("services.cosmos_service.get_friends", lambda uid: [])
    monkeypatch.setattr("services.cosmos_service.get_or_create_personal_watchlist", lambda uid: None)
    monkeypatch.setattr("services.cosmos_service.get_watchlist_items", lambda wid: [])
    monkeypatch.setattr("services.tmdb_service.get_recommendations_for_title", lambda *a, **k: [])
    monkeypatch.setattr("services.tmdb_service.get_director_filmography", lambda *a, **k: [])
    monkeypatch.setattr("services.cosmos_service.batch_get_movie_crafts", lambda movies: {})

    galaxy = build_taste_cosmos_data(user_id=1299, force_refresh=True)
    assert galaxy["success"] is True

    # 1. Verify calibration stats
    calib_stats = galaxy["stats"].get("calibration")
    assert calib_stats is not None
    assert "calibrator_type" in calib_stats
    assert "history_tier" in calib_stats

    # 2. Verify all stars receive match_score, calibrated_prob, affinity_score
    for star in galaxy["stars"]:
        assert "affinity_score" in star
        assert 0.0 <= star["affinity_score"] <= 1.0
        assert "match_score" in star
        assert 50 <= star["match_score"] <= 99
        assert "calibrated_prob" in star
        assert 0.0 <= star["calibrated_prob"] <= 1.0

        # Backwards compatible alias
        assert star["match_pct"] == star["match_score"]


def test_bayesian_quality_prior_in_galaxy(monkeypatch):
    sample_movies = [
        {"id": 1, "movie": "Blade Runner", "p_year": 1982, "director": "Ridley Scott", "genre": "Sci-Fi", "rating": 5, "poster": "", "tv_show": 0},
        {"id": 2, "movie": "2001: A Space Odyssey", "p_year": 1968, "director": "Stanley Kubrick", "genre": "Sci-Fi", "rating": 5, "poster": "", "tv_show": 0}
    ]
    monkeypatch.setattr("services.cosmos_service.get_movies", lambda uid: sample_movies)
    monkeypatch.setattr("services.cosmos_service.get_friends", lambda uid: [])
    monkeypatch.setattr("services.cosmos_service.get_or_create_personal_watchlist", lambda uid: None)
    monkeypatch.setattr("services.cosmos_service.get_watchlist_items", lambda wid: [])
    
    cand_high = {
        "title": "Stalker",
        "p_year": "1979",
        "director": "Andrei Tarkovsky",
        "genre": "Sci-Fi, Drama",
        "vote_average": 8.4,
        "vote_count": 2200,
        "poster": ""
    }
    cand_flop = {
        "title": "Epic Movie",
        "p_year": "2007",
        "director": "Jason Friedberg",
        "genre": "Comedy",
        "vote_average": 2.5,
        "vote_count": 1800,
        "poster": ""
    }
    monkeypatch.setattr("services.tmdb_service.get_cached_recommendations", lambda *a, **k: [cand_high, cand_flop])
    monkeypatch.setattr("services.tmdb_service.get_recommendations_for_title", lambda *a, **k: [cand_high, cand_flop])
    monkeypatch.setattr("services.tmdb_service.get_director_filmography", lambda *a, **k: [])
    monkeypatch.setattr("services.cosmos_service.batch_get_movie_crafts", lambda movies: {})

    galaxy = build_taste_cosmos_data(user_id=1300, force_refresh=True)
    assert galaxy["success"] is True

    # 1. Telemetry verification
    stats = galaxy["stats"]
    assert "quality_prior" in stats
    q_meta = stats["quality_prior"]
    assert "catalogue_mean" in q_meta
    assert "confidence_threshold" in q_meta
    assert q_meta["mode"] == "additive"
    assert q_meta["evaluated_candidates"] > 0

    # 2. Star verification
    stars_by_title = {s["title"]: s for s in galaxy["stars"]}
    assert "Stalker" in stars_by_title
    assert "Epic Movie" in stars_by_title

    stalker = stars_by_title["Stalker"]
    assert "quality_score" in stalker
    assert stalker["quality_score"] > 8.0
    assert stalker["quality_delta"] > 0.0
    assert stalker["quality_diagnostics"]["vote_count"] == 2200

    epic_movie = stars_by_title["Epic Movie"]
    assert epic_movie["quality_score"] < 4.0
    assert epic_movie["quality_delta"] < 0.0

    # 3. All stars have quality keys
    for s in galaxy["stars"]:
        assert "quality_score" in s
        assert "quality_delta" in s
        assert "quality_diagnostics" in s





