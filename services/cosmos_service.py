"""
cosmos_service.py — Mathematical Vector Engine & Autonomous 2D Cinephile Cosmos Service

Builds a high-dimensional vector space for movies, runs dimensionality reduction
(PCA / t-SNE / Force-Directed Repulsion) to project films into an interactive 2D star galaxy,
clusters stars into named Galactic Sectors, and calculates gravitational match scores,
wormhole geodesic trajectories, and probe recommendations without using any LLM.
"""

import os
import re
import math
import time
import logging
import random
import threading
from typing import Dict, List, Any, Optional, Tuple

import numpy as np
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity
from scipy.ndimage import gaussian_filter

from database import get_movies, get_friends, get_or_create_personal_watchlist, get_watchlist_items
import services.tmdb_service as tmdb_service
from services.embedding_service import compute_semantic_embeddings
from services.craft_service import batch_get_movie_crafts, _normalize_key
from services.graph_service import build_and_run_lightgcn
from services.fusion_service import execute_adaptive_fusion
from services.negative_mode_service import execute_negative_mode_pipeline
from services.positive_mode_service import execute_positive_mode_pipeline
from services.calibration_service import calibrate_scores
from services.quality_service import batch_apply_quality_prior

logger = logging.getLogger(__name__)

# In-memory TTL Cache for Cosmos Galaxy State per user
_GALAXY_CACHE: Dict[int, Tuple[float, Dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 1800  # 30 minutes

# Canonical Genres & Mood Tags for Vector Encoding
GENRE_FEATURES = [
    "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary",
    "Drama", "Family", "Fantasy", "History", "Horror", "Music",
    "Mystery", "Romance", "Sci-Fi", "Science Fiction", "TV Movie", "Thriller", "War", "Western"
]

MOOD_KEYWORDS = {
    "cyberpunk": ["cyberpunk", "futuristic", "ai", "virtual", "matrix", "dystopia", "dystopian", "tech", "hacker", "android", "synth"],
    "noir": ["noir", "neo-noir", "detective", "investigation", "paranoia", "conspiracy", "gritty", "underworld", "femme fatale", "cynical"],
    "psychological": ["psychological", "mindfuck", "hallucination", "madness", "identity", "memory", "illusion", "sanity", "obsessive"],
    "atmospheric": ["atmospheric", "slow burn", "meditative", "hypnotic", "moody", "poetic", "ambient", "ethereal", "visual"],
    "surreal": ["surreal", "dream", "absurd", "existential", "philosophical", "metaphor", "bizarre", "allegory", "symbolism"],
    "adrenaline": ["adrenaline", "explosive", "martial arts", "heist", "chase", "combat", "superhero", "survival", "revenge", "thrill"],
    "melancholy": ["melancholy", "grief", "heartbreak", "isolation", "loss", "nostalgia", "bittersweet", "loneliness", "tragedy"],
    "cult": ["cult classic", "midnight movie", "b-movie", "camp", "provocative", "transgressive", "unconventional", "underground"]
}

# Curated high-watermark landmark cinema & prestige television catalogue for candidate population & cold-start
CURATED_LANDMARKS = [
    {"title": "Stalker", "year": "1979", "director": "Andrei Tarkovsky", "genre": "Sci-Fi, Drama", "poster": "https://image.tmdb.org/t/p/w500/1qhOyf5C4s9ZdvY8d5JDx9DFMeT.jpg", "tv_show": 0, "tags": "philosophical, atmospheric, surreal"},
    {"title": "Blade Runner 2049", "year": "2017", "director": "Denis Villeneuve", "genre": "Sci-Fi, Mystery", "poster": "https://image.tmdb.org/t/p/w500/gajva2L0rPYkEWjzgFlBXCAVBE5.jpg", "tv_show": 0, "tags": "cyberpunk, atmospheric, noir"},
    {"title": "Severance", "year": "2022", "director": "Dan Erickson, Ben Stiller", "genre": "Drama, Mystery, Sci-Fi", "poster": "https://image.tmdb.org/t/p/w500/A09Nm1B2W44t0c7N6wLpT1d4mC4.jpg", "tv_show": 1, "tags": "cyberpunk, psychological, noir"},
    {"title": "Succession", "year": "2018", "director": "Jesse Armstrong", "genre": "Drama, Comedy", "poster": "https://image.tmdb.org/t/p/w500/7TvlKzpKk295i2dM30jWqA8x5yB.jpg", "tv_show": 1, "tags": "dialogue, satire, drama"},
    {"title": "Chernobyl", "year": "2019", "director": "Craig Mazin", "genre": "Drama, History", "poster": "https://image.tmdb.org/t/p/w500/hlLXt2tOPT6RRnjiUmoxyG1LTFi.jpg", "tv_show": 1, "tags": "atmospheric, tension, tragedy"},
    {"title": "Mindhunter", "year": "2017", "director": "David Fincher", "genre": "Crime, Drama, Thriller", "poster": "https://image.tmdb.org/t/p/w500/fbKE87mojpIETWepSbD5Qt741fp.jpg", "tv_show": 1, "tags": "noir, detective, psychological"},
    {"title": "Twin Peaks", "year": "1990", "director": "David Lynch", "genre": "Drama, Mystery, Sci-Fi", "poster": "https://image.tmdb.org/t/p/w500/lA9U00v3vdhD3yvU7N0W5tZ9n7C.jpg", "tv_show": 1, "tags": "surreal, psychological, cult"},
    {"title": "The Wire", "year": "2002", "director": "David Simon", "genre": "Crime, Drama, Thriller", "poster": "https://image.tmdb.org/t/p/w500/4lbclFySvugI51fwsyxBTOm4DqK.jpg", "tv_show": 1, "tags": "gritty, realism, crime"},
    {"title": "Cowboy Bebop", "year": "1998", "director": "Shinichirō Watanabe", "genre": "Animation, Action, Sci-Fi", "poster": "https://image.tmdb.org/t/p/w500/xDiSc5HBQ1nP147nQae329NkW7E.jpg", "tv_show": 1, "tags": "cyberpunk, cult, adrenaline"},
    {"title": "Dark", "year": "2017", "director": "Baran bo Odar", "genre": "Crime, Drama, Mystery, Sci-Fi", "poster": "https://image.tmdb.org/t/p/w500/apbrbWs8M9lyOpJYU5WXrpFbk1Z.jpg", "tv_show": 1, "tags": "psychological, sci-fi, slow burn"},
    {"title": "True Detective", "year": "2014", "director": "Cary Fukunaga", "genre": "Crime, Drama, Mystery", "poster": "https://image.tmdb.org/t/p/w500/aowr4xpLP5sRGM8st7vGQh4A6w6.jpg", "tv_show": 1, "tags": "noir, psychological, southern gothic"},
    {"title": "Shōgun", "year": "2024", "director": "Justin Marks", "genre": "Drama, History, War", "poster": "https://image.tmdb.org/t/p/w500/7O4iVfOMQmdCSxhOg1WnzG1AgYT.jpg", "tv_show": 1, "tags": "epic, historical, drama"},
    {"title": "Arcane", "year": "2021", "director": "Christian Linke", "genre": "Animation, Action, Sci-Fi", "poster": "https://image.tmdb.org/t/p/w500/fqldf2t8ztc9aiwn397F62G96HN.jpg", "tv_show": 1, "tags": "adrenaline, animation, cyberpunk"},
    {"title": "The Bear", "year": "2022", "director": "Christopher Storer", "genre": "Comedy, Drama", "poster": "https://image.tmdb.org/t/p/w500/n77145y7CqV2iZ2P2nKq7gK3t5s.jpg", "tv_show": 1, "tags": "intense, psychological, comedy"},
    {"title": "Cure", "year": "1997", "director": "Kiyoshi Kurosawa", "genre": "Crime, Horror, Mystery", "poster": "https://image.tmdb.org/t/p/w500/xNVJr9q6AtSbjosS6Ed9YirOkSo.jpg", "tv_show": 0, "tags": "psychological, noir, slow burn"},
    {"title": "Memories of Murder", "year": "2003", "director": "Bong Joon-ho", "genre": "Crime, Drama, Thriller", "poster": "https://image.tmdb.org/t/p/w500/jcgUjx1QcupGzjntTVlnQ15lHqy.jpg", "tv_show": 0, "tags": "noir, detective, psychological"},
    {"title": "Mulholland Drive", "year": "2001", "director": "David Lynch", "genre": "Drama, Mystery, Thriller", "poster": "https://image.tmdb.org/t/p/w500/x7A59t6ySylr1L7aubOQEA480vM.jpg", "tv_show": 0, "tags": "surreal, psychological, noir"},
    {"title": "2001: A Space Odyssey", "year": "1968", "director": "Stanley Kubrick", "genre": "Sci-Fi, Mystery, Adventure", "poster": "https://image.tmdb.org/t/p/w500/ve72VxNqjGM69Uky4WTo2bK6rfq.jpg", "tv_show": 0, "tags": "philosophical, atmospheric, sci-fi"},
    {"title": "Chungking Express", "year": "1994", "director": "Wong Kar-wai", "genre": "Drama, Romance, Comedy", "poster": "https://image.tmdb.org/t/p/w500/43I9DcNoCzpyzK8JCkJYpHqHqGG.jpg", "tv_show": 0, "tags": "melancholy, atmospheric, romance"},
    {"title": "Seven Samurai", "year": "1954", "director": "Akira Kurosawa", "genre": "Action, Drama", "poster": "https://image.tmdb.org/t/p/w500/lOMGc8bnSwQhS4XyE1S99uH8NXf.jpg", "tv_show": 0, "tags": "adrenaline, epic, drama"},
    {"title": "La Haine", "year": "1995", "director": "Mathieu Kassovitz", "genre": "Drama, Crime", "poster": "https://image.tmdb.org/t/p/w500/hY4exng4s29RzDbtQInjx9MA3PZ.jpg", "tv_show": 0, "tags": "gritty, cult, adrenaline"},
    {"title": "Persona", "year": "1966", "director": "Ingmar Bergman", "genre": "Drama", "poster": "https://image.tmdb.org/t/p/w500/hloUDKausII3Zf8ROsEZJHSkXza.jpg", "tv_show": 0, "tags": "psychological, surreal, melancholy"},
    {"title": "Drive My Car", "year": "2021", "director": "Ryusuke Hamaguchi", "genre": "Drama", "poster": "https://image.tmdb.org/t/p/w500/znXps7wPyYq8UDCfeyO2vfEIeRS.jpg", "tv_show": 0, "tags": "slow burn, melancholy, poetic"},
    {"title": "The Thing", "year": "1982", "director": "John Carpenter", "genre": "Horror, Mystery, Sci-Fi", "poster": "https://image.tmdb.org/t/p/w500/tzGY49kseSE9QAKk47uuDGwnSCu.jpg", "tv_show": 0, "tags": "paranoia, cult, adrenaline"},
    {"title": "Paris, Texas", "year": "1984", "director": "Wim Wenders", "genre": "Drama", "poster": "https://image.tmdb.org/t/p/w500/sP27Qm4THyRZyHjHYMfIDtJP6YE.jpg", "tv_show": 0, "tags": "melancholy, atmospheric, slow burn"},
    {"title": "Taxi Driver", "year": "1976", "director": "Martin Scorsese", "genre": "Crime, Drama", "poster": "https://image.tmdb.org/t/p/w500/ekstpH614fwDX8DUln1a2Opz0N8.jpg", "tv_show": 0, "tags": "noir, psychological, gritty"},
    {"title": "Spirited Away", "year": "2001", "director": "Hayao Miyazaki", "genre": "Animation, Family, Fantasy", "poster": "https://image.tmdb.org/t/p/w500/39wmItIWsg5sZMyRUHLkWBcuVCM.jpg", "tv_show": 0, "tags": "surreal, whimsical, animation"},
    {"title": "Arrival", "year": "2016", "director": "Denis Villeneuve", "genre": "Sci-Fi, Mystery, Drama", "poster": "https://image.tmdb.org/t/p/w500/pEzNVQfdzYDzVK0XqxERIw2x2se.jpg", "tv_show": 0, "tags": "atmospheric, philosophical, sci-fi"},
    {"title": "In the Mood for Love", "year": "2000", "director": "Wong Kar-wai", "genre": "Drama, Romance", "poster": "https://image.tmdb.org/t/p/w500/iYypPT4bhqXfq1b6EnmxvRt6b2Y.jpg", "tv_show": 0, "tags": "atmospheric, melancholy, poetic"},
    {"title": "Akira", "year": "1988", "director": "Katsuhiro Otomo", "genre": "Animation, Sci-Fi, Action", "poster": "https://image.tmdb.org/t/p/w500/neZ0ykEsPqxamsX6o5QNUFILQrz.jpg", "tv_show": 0, "tags": "cyberpunk, cult, adrenaline"},
    {"title": "Heat", "year": "1995", "director": "Michael Mann", "genre": "Action, Crime, Drama", "poster": "https://image.tmdb.org/t/p/w500/gKaePbkEkaqvMtw74EyhhkfCKKh.jpg", "tv_show": 0, "tags": "noir, adrenaline, heist"},
    {"title": "Fargo", "year": "1996", "director": "Joel Coen", "genre": "Crime, Drama, Thriller", "poster": "https://image.tmdb.org/t/p/w500/rt7cpEr1uP6RTZykBFhBTcRaKvG.jpg", "tv_show": 0, "tags": "cult, noir, dark comedy"},
    {"title": "Pulp Fiction", "year": "1994", "director": "Quentin Tarantino", "genre": "Crime, Thriller", "poster": "https://image.tmdb.org/t/p/w500/vQWk5YBFWF4bZaofAbv0tShwBvQ.jpg", "tv_show": 0, "tags": "cult, dialogue, gritty"},
    {"title": "The Matrix", "year": "1999", "director": "Lana Wachowski", "genre": "Sci-Fi, Action", "poster": "https://image.tmdb.org/t/p/w500/dXNAPwY7VrqMAo51EKhhCJfaGb5.jpg", "tv_show": 0, "tags": "cyberpunk, philosophical, adrenaline"},
    {"title": "Interstellar", "year": "2014", "director": "Christopher Nolan", "genre": "Sci-Fi, Adventure, Drama", "poster": "https://image.tmdb.org/t/p/w500/yQvGrMoipbRoddT0ZR8tPoR7NfX.jpg", "tv_show": 0, "tags": "space, emotional, epic"},
    {"title": "Oldboy", "year": "2003", "director": "Park Chan-wook", "genre": "Action, Drama, Mystery", "poster": "https://image.tmdb.org/t/p/w500/pWDtjs568ZfOTMbURQBYuT4Qxka.jpg", "tv_show": 0, "tags": "revenge, psychological, neo-noir"},
    {"title": "Parasite", "year": "2019", "director": "Bong Joon-ho", "genre": "Comedy, Thriller, Drama", "poster": "https://image.tmdb.org/t/p/w500/7IiTTgloJzvGI1TAYymCfbfl3vT.jpg", "tv_show": 0, "tags": "social satire, suspense, dark comedy"},
    {"title": "No Country for Old Men", "year": "2007", "director": "Joel Coen", "genre": "Crime, Drama, Thriller", "poster": "https://image.tmdb.org/t/p/w500/6d5XOczc226jECq0LIX0siKtgHR.jpg", "tv_show": 0, "tags": "neo-western, tension, nihilism"},
    {"title": "There Will Be Blood", "year": "2007", "director": "Paul Thomas Anderson", "genre": "Drama", "poster": "https://image.tmdb.org/t/p/w500/fa0RDkAlCec0STeMNAhPaF89q6U.jpg", "tv_show": 0, "tags": "obsession, epic, character study"},
    {"title": "Whiplash", "year": "2014", "director": "Damien Chazelle", "genre": "Drama, Music", "poster": "https://image.tmdb.org/t/p/w500/7fn624j5lj3xTme2SgiLCeuedmO.jpg", "tv_show": 0, "tags": "intense, psychological, perfectionism"},
    {"title": "Alien", "year": "1979", "director": "Ridley Scott", "genre": "Horror, Sci-Fi", "poster": "https://image.tmdb.org/t/p/w500/vfrQk5IPloGg1v9Rzbh2Eg3VGyM.jpg", "tv_show": 0, "tags": "claustrophobic, survival, space"},
    {"title": "Blade Runner", "year": "1982", "director": "Ridley Scott", "genre": "Sci-Fi, Drama, Thriller", "poster": "https://image.tmdb.org/t/p/w500/63N9uy8nd9j7Eog2axPQ8lbr3Wj.jpg", "tv_show": 0, "tags": "cyberpunk, neo-noir, existential"}
]


def _normalize_name(name: str) -> str:
    if not name:
        return ""
    return re.sub(r'[^a-zA-Z0-9]', '', name.lower())


def _extract_feature_vector(
    movie: Dict[str, Any], 
    director_indexer: Dict[str, int], 
    cast_indexer: Dict[str, int] = None
) -> np.ndarray:
    """
    Creates a dense numerical feature vector for a movie covering:
    - Multi-hot genres (dim: 20)
    - Release year normalized (dim: 1)
    - Mood / Keyword vector (dim: 8)
    - TV flag (dim: 1)
    - Collision-Free Auteur Index Representation (dim: 32)
    - Collision-Free Lead Cast / Collaboration Vector (dim: 8)
    Total dimensions: 70
    """
    # 1. Genres (20D L1-Normalized)
    g_str = (movie.get("genre") or "").lower()
    genre_vec = [1.0 if g.lower() in g_str else 0.0 for g in GENRE_FEATURES]
    if sum(genre_vec) > 0:
        genre_vec = [x / sum(genre_vec) for x in genre_vec]

    # 2. Release Year normalized between 1920 (0.0) and 2030 (1.0)
    try:
        yr = float(movie.get("p_year") or movie.get("year") or 2000)
        norm_yr = max(0.0, min(1.0, (yr - 1920.0) / 110.0))
    except Exception:
        norm_yr = 0.7

    # 3. Mood Keywords (8D)
    tags_str = ((movie.get("tags") or "") + " " + (movie.get("overview") or "") + " " + g_str).lower()
    mood_vec = []
    for _m_label, words in MOOD_KEYWORDS.items():
        score = sum(1.0 for w in words if w in tags_str)
        mood_vec.append(min(1.0, score * 0.5))

    # 4. TV show flag (1D)
    is_tv = 1.0 if movie.get("tv_show") in [1, "1", True] else 0.0

    # 5. Collision-Free Auteur Representation (32D)
    dir_name = _normalize_name(movie.get("director") or "Unknown")
    dir_vec = [0.0] * 32
    if dir_name in director_indexer:
        dir_idx = director_indexer[dir_name]
        if dir_idx < 31:
            dir_vec[dir_idx] = 1.0
        else:
            dir_vec[31] = 0.5  # Tail auteur bucket
    elif dir_name and dir_name != "unknown":
        dir_vec[31] = 0.25

    # 6. Collision-Free Cast / Actor Co-occurrence Representation (8D)
    cast_vec = [0.0] * 8
    if cast_indexer:
        for actor_norm, c_idx in cast_indexer.items():
            if actor_norm in tags_str:
                cast_vec[c_idx % 8] = 1.0

    # 7. Orthogonal Category Anchors (6D strong categorical partition)
    # Prevents category cross-contamination between Animation/Family, Dark Crime/Horror, Heavy Auteur Drama, etc.
    is_anim = 3.2 if ("animation" in g_str or "family" in g_str) else 0.0
    is_crime_noir = 2.4 if ("crime" in g_str or "noir" in tags_str or "thriller" in g_str or "horror" in g_str) else 0.0
    is_serious_drama = 2.4 if ("drama" in g_str and "animation" not in g_str and "family" not in g_str) else 0.0
    is_comedy_satire = 2.2 if ("comedy" in g_str and "animation" not in g_str) else 0.0
    is_scifi_fantasy = 2.4 if ("sci-fi" in g_str or "science fiction" in g_str or "fantasy" in g_str) else 0.0
    is_action_adv = 2.0 if ("action" in g_str or "adventure" in g_str) else 0.0
    cat_sep_vec = [is_anim, is_crime_noir, is_serious_drama, is_comedy_satire, is_scifi_fantasy, is_action_adv]

    # 8. Cultural & Movement Anchors (3D regional coherence)
    is_italian = 2.0 if any(w in tags_str or w in (movie.get("director") or "").lower() for w in ["italian", "italia", "medusa", "rai cinema", "lotus production", "maccio", "sorrentino", "fellini", "garrone", "de sica", "verdone", "zalone", "carlani", "sordi", "tognazzi", "albanese", "cortellesi"]) else 0.0
    is_anime = 2.5 if any(w in tags_str for w in ["anime", "japan", "japanese", "manga", "shonen", "ghibli", "toei", "madhouse", "mappa", "miyazaki", "shinkai", "kon", "anno", "oshii"]) else 0.0
    is_korean = 2.5 if any(w in tags_str for w in ["korea", "korean", "seoul", "bong joon-ho", "park chan-wook", "lee chang-dong", "kim jee-woon"]) else 0.0
    cult_vec = [is_italian, is_anime, is_korean]

    # Combine into unified array (79D float32)
    return np.array(genre_vec + [norm_yr * 1.5] + mood_vec + [is_tv * 0.5] + dir_vec + cast_vec + cat_sep_vec + cult_vec, dtype=np.float32)


_FETCHING_SEEDS = set()
_FETCHING_LOCK = threading.Lock()


def _get_stratified_seed_items(user_movies: List[Dict[str, Any]]) -> List[Tuple[str, str, bool]]:
    """
    Extracts up to 25-35 high-priority seeds stratified across:
    1. All 5-star masterworks & rewatches (core taste anchors)
    2. Top-rated items across dominant genres
    3. Top-rated items for recurring favorite auteurs
    """
    if not user_movies:
        return []

    seeds: List[Tuple[str, str, bool]] = []
    seen = set()

    def _add_seed(m: Dict[str, Any]):
        title = m.get("movie") or m.get("title")
        year = str(m.get("p_year") or m.get("year") or "")
        is_tv = bool(m.get("tv_show") in [1, "1", True])
        if title:
            key = f"{_normalize_name(title)}_{year}_{is_tv}"
            if key not in seen:
                seen.add(key)
                seeds.append((title, year, is_tv))

    # 1. 5-Star ratings & Rewatches
    tier1 = [m for m in user_movies if (m.get("rating") or 0) >= 5 or (m.get("rewatch") or 0) > 0]
    tier1.sort(key=lambda x: ((x.get("rating") or 0) >= 5, x.get("rewatch") or 0), reverse=True)
    for m in tier1[:15]:
        _add_seed(m)

    # 2. Dominant Genres (Top 2 per genre for up to 6 genres)
    genre_items: Dict[str, List[Dict[str, Any]]] = {}
    for m in user_movies:
        if (m.get("rating") or 0) >= 4:
            for g in str(m.get("genre", "")).split(","):
                cg = g.strip()
                if cg and cg.lower() != "unknown":
                    genre_items.setdefault(cg, []).append(m)

    for g, items in sorted(genre_items.items(), key=lambda x: len(x[1]), reverse=True)[:6]:
        items.sort(key=lambda x: x.get("rating") or 0, reverse=True)
        for m in items[:2]:
            _add_seed(m)

    # 3. Top Auteurs (Top 1 per auteur for top 6 auteurs)
    dir_items: Dict[str, List[Dict[str, Any]]] = {}
    for m in user_movies:
        d = m.get("director")
        if d and d.lower() not in ["unknown", "n/a", ""] and (m.get("rating") or 0) >= 4:
            dir_items.setdefault(d, []).append(m)

    for d, items in sorted(dir_items.items(), key=lambda x: len(x[1]), reverse=True)[:6]:
        items.sort(key=lambda x: x.get("rating") or 0, reverse=True)
        for m in items[:1]:
            _add_seed(m)

    # 4. Other 4-star items as fallback
    if len(seeds) < 25:
        tier2 = [m for m in user_movies if (m.get("rating") or 0) >= 4]
        for m in tier2:
            _add_seed(m)
            if len(seeds) >= 30:
                break

    return seeds[:35]


def _async_fetch_missing_tmdb_seeds(seeds: List[Tuple[str, str, bool]]):
    """
    Detached background worker that runs asynchronously without blocking page loads.
    Fetches TMDB recommendations for uncached seeds and saves them into the SQLite database.
    """
    global _FETCHING_SEEDS
    for title, year, is_tv in seeds:
        key = f"{_normalize_name(title)}_{year}_{is_tv}"
        with _FETCHING_LOCK:
            if key in _FETCHING_SEEDS:
                continue
            _FETCHING_SEEDS.add(key)

        try:
            # Check SQLite cache first
            cached = tmdb_service.get_cached_recommendations(title, year, is_tv)
            if cached is None:
                # Live fetch from TMDB (automatically writes to SQLite cache)
                tmdb_service.get_recommendations_for_title(title, year, is_tv, limit=8, use_cache=False)
                time.sleep(0.15)  # Respectful pause between TMDB calls
        except Exception as e:
            logger.debug(f"Background TMDB seed fetch error for {title}: {e}")
        finally:
            with _FETCHING_LOCK:
                _FETCHING_SEEDS.discard(key)


def _fetch_autonomous_candidates(user_id: int, user_movies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    3-Tier Vector Frontier Recommender Engine:
    Harvests pristine unwatched candidates from the Cinephile Corpus,
    partitioned across:
    1. Direct Resonators (60%): Deep-cuts in each user sub-taste mode.
    2. Aesthetic Crossovers (25%): Harmonic-mean taste bridges between pairs of user sub-tastes.
    3. Quantum Leap Frontiers (15%): High-prestige landmark gateways into unexplored sectors.
    + Dynamic friend favorites and persistent SQLite-cached TMDB seed recommendations.
    """
    from collections import Counter
    from services.corpus_service import get_all_curated_films
    
    seen_keys = set()
    user_genres_counter = Counter()
    user_directors_counter = Counter()

    for m in user_movies:
        key = f"{_normalize_name(m.get('movie'))}_{m.get('p_year', '')}"
        seen_keys.add(key)
        r = m.get("rating") or 0
        w = 2 if r >= 5 else (1 if r >= 4 else 0)
        if w > 0:
            for g in str(m.get("genre", "")).split(","):
                cg = g.strip()
                if cg and cg.lower() != "unknown":
                    user_genres_counter[cg] += w
            d = m.get("director")
            if d and d.lower() not in ["unknown", "n/a", ""]:
                user_directors_counter[d] += w

    # Top positive taste modes (up to 4 dominant genre modes)
    top_user_genres = [g for g, _ in user_genres_counter.most_common(4)] or ["Drama", "Crime", "Sci-Fi"]

    # 1. Fetch entire curated corpus (< 2ms) with fresh reseed check
    all_curated = get_all_curated_films()
    unwatched_curated = []
    for c in all_curated:
        k = f"{_normalize_name(c['title'])}_{c['year']}"
        if k not in seen_keys:
            unwatched_curated.append(c)

    # Stratified Temporal Partitioning (Prevents historical era starvation/monopoly)
    # Era 1: Contemporary (2010–2026) -> 40% Target (~60 candidates)
    # Era 2: Modern Cult & Indie (1980–2009) -> 35% Target (~50 candidates)
    # Era 3: Golden Age Canon (< 1980) -> 25% Target (~35 candidates)
    era_buckets = {
        "contemporary": [],
        "modern_cult": [],
        "golden_age": []
    }

    # 2. Score Unwatched Curated Films across 3 Frontiers & Assign to Era Buckets
    for c in unwatched_curated:
        c_year = int(c.get("year") or 2000)
        c_genres = [g.strip() for g in str(c.get("genre", "")).split(",") if g.strip()]
        c_dir = c.get("director", "")
        
        # Calculate sub-taste mode overlaps
        mode_scores = []
        for g_mode in top_user_genres:
            score = 0.0
            if any(g.lower() == g_mode.lower() for g in c_genres):
                score += 1.0
            if c_dir in user_directors_counter:
                score += 1.5
            mode_scores.append(score)

        pos_modes = [top_user_genres[i] for i, s in enumerate(mode_scores) if s > 0]
        max_mode_score = max(mode_scores) if mode_scores else 0.0

        item_obj = {
            "title": c["title"],
            "year": str(c["year"]),
            "director": c["director"],
            "genre": c["genre"],
            "poster": c.get("poster", ""),
            "tv_show": c.get("tv_show", 0),
            "source": "cinephile_corpus",
            "tags": c.get("movement_tags", "") or c.get("canon_tier", ""),
            "canon_tier": c.get("canon_tier", "landmark"),
            "vote_average": c.get("rating_score", 8.5),
            "vote_count": c.get("vote_count", 2000),
            "craft": {
                "director": c.get("director", ""),
                "cinematographer": c.get("cinematographer", ""),
                "composer": c.get("composer", ""),
                "screenwriter": c.get("screenwriter", ""),
                "lead_actors": c.get("lead_actors", ""),
                "studios": c.get("studios", "")
            }
        }

        if len(pos_modes) >= 2:
            item_obj["frontier_type"] = "crossover"
            item_obj["frontier_desc"] = f"Aesthetic Bridge: {pos_modes[0]} ⟷ {pos_modes[1]}"
            frontier_score = sum(mode_scores) + 0.5
        elif max_mode_score > 0:
            item_obj["frontier_type"] = "resonator"
            item_obj["frontier_desc"] = f"Core {pos_modes[0] if pos_modes else 'Cinema'} Resonator"
            frontier_score = max_mode_score
        else:
            prestige_weight = 2.0 if c.get("canon_tier") in ["sight_and_sound", "palme_dor_festival"] else 1.0
            item_obj["frontier_type"] = "quantum_frontier"
            item_obj["frontier_desc"] = f"Uncharted Frontier: {c_genres[0] if c_genres else 'Cinema'}"
            frontier_score = prestige_weight

        # Assign to era bucket
        if c_year >= 2010:
            era_buckets["contemporary"].append((frontier_score, item_obj))
        elif c_year >= 1980:
            era_buckets["modern_cult"].append((frontier_score, item_obj))
        else:
            era_buckets["golden_age"].append((frontier_score, item_obj))

    # Sort each era bucket by affinity / prestige score
    for k in era_buckets:
        era_buckets[k].sort(key=lambda x: x[0], reverse=True)

    # Stratified Selection: 60 Contemporary, 50 Modern Cult, 35 Golden Age
    selected_items = []
    for _, item in era_buckets["contemporary"][:60]:
        selected_items.append(item)
    for _, item in era_buckets["modern_cult"][:50]:
        selected_items.append(item)
    for _, item in era_buckets["golden_age"][:35]:
        selected_items.append(item)

    # 3. Stratified TMDB Seed Recommendations (Instant SQLite Lookup + Detached Background Worker)
    stratified_seeds = _get_stratified_seed_items(user_movies)
    missing_seeds = []

    for title, year, is_tv in stratified_seeds:
        cached_recs = tmdb_service.get_cached_recommendations(title, year, is_tv)
        if cached_recs is not None:
            for item in cached_recs:
                k = f"{_normalize_name(item.get('title'))}_{item.get('year', '')}"
                if k not in seen_keys:
                    item["frontier_type"] = "resonator"
                    item["frontier_desc"] = "Dynamic TV Resonator" if item.get("tv_show") else "Dynamic Taste Resonator"
                    selected_items.append(item)
                    seen_keys.add(k)
        else:
            missing_seeds.append((title, year, is_tv))

    # Dispatch missing seeds to detached background thread without blocking
    if missing_seeds:
        try:
            t = threading.Thread(
                target=_async_fetch_missing_tmdb_seeds,
                args=(missing_seeds[:8],),
                daemon=True
            )
            t.start()
        except Exception as e:
            logger.debug(f"Could not launch background TMDB worker: {e}")

    # 4. Friend Network Favorites
    try:
        friends = get_friends(user_id)
        friend_ids = [f.get("user_id") for f in friends if f.get("user_id")]
        if friend_ids:
            f_movies = get_movies(friend_ids[0])
            for fm in f_movies:
                if (fm.get("rating") or 0) >= 4 and fm.get("poster"):
                    k = f"{_normalize_name(fm.get('movie'))}_{fm.get('p_year', '')}"
                    if k not in seen_keys:
                        selected_items.append({
                            "title": fm.get("movie"),
                            "year": str(fm.get("p_year") or ""),
                            "director": fm.get("director") or "Unknown",
                            "genre": fm.get("genre") or "Cinema",
                            "poster": fm.get("poster") or "",
                            "tv_show": fm.get("tv_show", 0),
                            "source": "friend_sync",
                            "tags": "friend favorite",
                            "vote_average": fm.get("vote_average") or fm.get("rating_score"),
                            "vote_count": fm.get("vote_count"),
                            "frontier_type": "resonator",
                            "frontier_desc": "Friend Network Resonator"
                        })
                        seen_keys.add(k)
                        if len(selected_items) >= 160:
                            break
    except Exception as e:
        logger.debug(f"Could not load friend candidates: {e}")

    return selected_items[:180]


# ==============================================================================
# 2-TIER HIERARCHICAL CINEMATIC TAXONOMY: MACRO-REALMS & MICRO-CONSTELLATIONS
# ==============================================================================

# Tier 1: Broad Macro-Sectors (The Celestial Realms)
MACRO_ARCHETYPES = [
    {
        "name": "THE ANIMATION & MYTHOLOGICAL CLUSTER",
        "code_prefix": "CLUST-ANIM",
        "color": "#7aa898",
        "description": "Studio Ghibli, Japanese anime masterworks, CGI family animation, Pixar, fantasy worlds, mythical beasts, Miyazaki, Takahata, Hosoda, Shinkai, Kon, Vinland Saga, Spirited Away, Puss in Boots, animated features"
    },
    {
        "name": "THE NOIR, CRIME & PSYCHOLOGICAL LABYRINTH",
        "code_prefix": "CLUST-NOIR",
        "color": "#e63946",
        "description": "East Asian revenge thrillers, American mafia epics, gritty crime investigations, serial killers, corruption, noir, Park Chan-wook, Bong Joon-ho, Scorsese, Coppola, Fincher, Memories of Murder, The Godfather, Seven, Oldboy, Zodiac"
    },
    {
        "name": "THE ARTHOUSE, HUMANIST & EXISTENTIAL CORE",
        "code_prefix": "CLUST-HUMAN",
        "color": "#e0a96d",
        "description": "Post-war humanism, Italian neorealism, French New Wave, European festival winners, intimate relationship dramas, Fellini, Sorrentino, Truffaut, Ozu, De Sica, Hamaguchi, Triet, The Great Beauty, 400 Blows, Tokyo Story, Anatomy of a Fall"
    },
    {
        "name": "THE SPECULATIVE SCI-FI & SURREALIST COSMOS",
        "code_prefix": "CLUST-COSMOS",
        "color": "#7eb5c4",
        "description": "Metaphysical sci-fi, philosophical space odysseys, surreal dreamscapes, existential horror, AI, time dilation, Denis Villeneuve, Stanley Kubrick, Andrei Tarkovsky, David Lynch, Charlie Kaufman, 2001, Blade Runner 2049, Arrival, Stalker, Mulholland Drive"
    },
    {
        "name": "THE SATIRICAL WIT & POP INDIE COMMONS",
        "code_prefix": "CLUST-INDIE",
        "color": "#06d6a0",
        "description": "Dark comedy, social class satire, high-concept indie dramedies, quirky witty ensembles, Coen Brothers, Wes Anderson, Noah Baumbach, Ruben Östlund, Parasite, The Grand Budapest Hotel, Fargo, Licorice Pizza, Triangle of Sadness"
    },
    {
        "name": "THE HIGH-OCTANE ACTION & SURVIVAL FRONTIER",
        "code_prefix": "CLUST-KINETIC",
        "color": "#ff9f1c",
        "description": "Adrenaline-fueled action, intense visceral survival, dystopian car chases, kinetic blockbusters, George Miller, John Carpenter, James Cameron, James Gunn, Mad Max, The Thing, Terminator, Guardians of the Galaxy, The Nice Guys"
    }
]

# Tier 2: Fine-Grained Micro-Constellations (The Thematic Pockets)
MICRO_ARCHETYPES = [
    {
        "name": "GHIBLI PASTORAL MYTHS & SPIRITS",
        "code_prefix": "GHIBLI",
        "color": "#7aa898",
        "description": "Studio Ghibli, lush green nature, spirits, flying machines, childhood nostalgia, environmental fable, Hayao Miyazaki, Isao Takahata, Spirited Away, Princess Mononoke, My Neighbor Totoro, Kiki, Castle in the Sky"
    },
    {
        "name": "CYBERPUNK & GRITTY SHONEN",
        "code_prefix": "CYBER-ANIME",
        "color": "#48cae4",
        "description": "Dark anime, cyberpunk dystopian future, warrior epics, psychological shonen, Mamoru Oshii, Satoshi Kon, Sunghoo Park, Ghost in the Shell, Vinland Saga, Akira, Jujutsu Kaisen 0, Made in Abyss, Perfect Blue"
    },
    {
        "name": "CGI FAMILY ADVENTURES & SLAPSTICK",
        "code_prefix": "CGI-FAMILY",
        "color": "#2ec4b6",
        "description": "Pixar, DreamWorks, illuminated CGI animation, talking animals, humorous family adventures, Joel Crawford, Brad Bird, Pete Docter, Puss in Boots: The Last Wish, Super Mario, Ratatouille, Soul, Zootopia, Minions, Lilo & Stitch"
    },
    {
        "name": "ITALIAN HIGH-SOCIETY MELODRAMA",
        "code_prefix": "AUTEUR-IT",
        "color": "#c4a96d",
        "description": "Roman nobility, melancholic decadence, nostalgic childhood memories, artistic crisis, Paolo Sorrentino, Federico Fellini, Michelangelo Antonioni, The Great Beauty, 8 1/2, La Dolce Vita, Amarcord, Youth, Il Divo"
    },
    {
        "name": "POST-WAR HUMANISM & NEO-REALISM",
        "code_prefix": "NEOREAL",
        "color": "#e0a96d",
        "description": "Post-war poverty, quiet family life, coming-of-age, black and white masterpieces, Vittorio De Sica, Yasujiro Ozu, Francois Truffaut, Bicycle Thieves, Tokyo Story, The 400 Blows, Jeanne Dielman, Umberto D"
    },
    {
        "name": "CONTEMPORARY FESTIVAL ELEGIES",
        "code_prefix": "CANNES",
        "color": "#b56576",
        "description": "Palme d'Or winners, courtroom intimacy, quiet grief, modern love, Justine Triet, Ryusuke Hamaguchi, Celine Sciamma, Joachim Trier, Anatomy of a Fall, Drive My Car, Portrait of a Lady on Fire, Past Lives, Worst Person in the World"
    },
    {
        "name": "EAST ASIAN NEO-NOIR & REVENGE",
        "code_prefix": "NOIR-ASIA",
        "color": "#e63946",
        "description": "Korean revenge thrillers, dark city investigations, rainy streets, claustrophobic violence, Park Chan-wook, Bong Joon-ho, Kim Jee-woon, Oldboy, Memories of Murder, I Saw the Devil, The Handmaiden, Decision to Leave"
    },
    {
        "name": "NEW HOLLYWOOD CORRUPTION & GANGSTERS",
        "code_prefix": "MAFIA",
        "color": "#d97736",
        "description": "American mafia sagas, 70s urban crime, moral corruption, heists, Martin Scorsese, Francis Ford Coppola, Sidney Lumet, The Godfather, Goodfellas, Taxi Driver, Heat, Casino, L.A. Confidential"
    },
    {
        "name": "PSYCHOLOGICAL INVESTIGATION & LABYRINTHS",
        "code_prefix": "MINDHUNTER",
        "color": "#4cc9f0",
        "description": "Serial killer profiling, psychological tension, obsessive detectives, FBI investigations, cold clinical direction, David Fincher, Mindhunter, Seven, Zodiac, The Silence of the Lambs, True Detective, Prisoners"
    },
    {
        "name": "NORDIC ICY PSYCHOLOGICAL TENSION",
        "code_prefix": "NORDIC",
        "color": "#48cae4",
        "description": "Austere tension, cold European investigations, moral decay, psychological cruelty, Michael Haneke, Thomas Vinterberg, The Hunt, Cache, The White Ribbon, cold realism"
    },
    {
        "name": "METAPHYSICAL SPACE & TIME ODYSSEYS",
        "code_prefix": "COSMOS",
        "color": "#7eb5c4",
        "description": "Philosophical space exploration, cosmic mystery, time travel, monumental scale, Stanley Kubrick, Denis Villeneuve, Andrei Tarkovsky, Christopher Nolan, 2001: A Space Odyssey, Interstellar, Arrival, Solaris, 2001"
    },
    {
        "name": "SURREALIST DREAMSCAPES & PARANOIA",
        "code_prefix": "SURREAL",
        "color": "#a89bc4",
        "description": "Surrealist body horror, fragmented dreams, psychological breakdowns, David Lynch, Charlie Kaufman, Yorgos Lanthimos, Mulholland Drive, Poor Things, The Lobster, Synecdoche New York, Persona"
    },
    {
        "name": "DARK SATIRE & SOCIAL CRITIQUE",
        "code_prefix": "SATIRE",
        "color": "#f4a261",
        "description": "Dark comedy, absurdity, class commentary, biting irony, Coen Brothers, Ruben Östlund, Bong Joon-ho, Parasite, Fargo, The Big Lebowski, Triangle of Sadness, In Bruges, The Menu, Dr. Strangelove"
    },
    {
        "name": "POP INDIE DRAMEDIES & QUIRK",
        "code_prefix": "INDIE-POP",
        "color": "#06d6a0",
        "description": "Witty dialogue, quirky coming-of-age, pastel aesthetics, eccentric families, Wes Anderson, Noah Baumbach, Paul Thomas Anderson, The Grand Budapest Hotel, Frances Ha, Licorice Pizza, Lady Bird, Juno"
    },
    {
        "name": "HIGH-PRESSURE WORKPLACE DRAMA",
        "code_prefix": "WORKPLACE",
        "color": "#ba68c8",
        "description": "High-octane kitchen chaos, corporate ambition, fast-paced dialogue, prestige TV, sitcom ensembles, Superstore, Christopher Storer, Matthew Weiner, Jesse Armstrong, The Bear, Succession, Mad Men, Whiplash, Tar"
    },
    {
        "name": "VISCERAL ADRENALINE & SURVIVAL",
        "code_prefix": "KINETIC",
        "color": "#ff9f1c",
        "description": "High-velocity car chases, post-apocalyptic survival, physical action spectacle, George Miller, John Carpenter, James Cameron, Mad Max: Fury Road, Terminator 2, The Thing, Aliens, Seven Samurai"
    },
    {
        "name": "HIGH-CONCEPT ACTION-COMEDY & HEISTS",
        "code_prefix": "HEIST-COMEDY",
        "color": "#ffbe0b",
        "description": "Ensemble heists, witty action comedy, colorful anti-heroes, James Gunn, Shane Black, Steven Soderbergh, Guardians of the Galaxy, The Nice Guys, Logan Lucky, The Suicide Squad, Dungeons & Dragons"
    },
    {
        "name": "SLAPSTICK, PARODIES & CULT COMEDIES",
        "code_prefix": "SLAPSTICK",
        "color": "#ffc300",
        "description": "Slapstick humor, parodies, cult absurd comedies, Tim Burton, Wayans, Leslie Nielsen, Beetlejuice, White Chicks, Naked Gun, Groundhog Day, Jack and Jill, Tre di troppo"
    },
    {
        "name": "SPORTS TRIUMPH & ATHLETIC OBSESSION",
        "code_prefix": "SPORTS",
        "color": "#e76f51",
        "description": "High-stakes athletics, underdog coaching, racing, basketball, discipline, Thomas Carter, Coach Carter, Moneyball, Go-Kart, Ford v Ferrari, Creed, Rush, 100 Metros"
    },
    {
        "name": "HISTORICAL EPICS & FAITH CHRONICLES",
        "code_prefix": "EPIC-HISTORY",
        "color": "#d4a373",
        "description": "Papal politics, religious debates, medieval warfare, historical biopics, Fernando Meirelles, Ridley Scott, Akira Kurosawa, The Two Popes, I due papi, Conclave, The Last Duel, The Mission, Ran, Oppenheimer"
    },
    {
        "name": "MEDITATIVE SLOW-BURN & ISOLATION",
        "code_prefix": "SOLITUDE",
        "color": "#5c6b73",
        "description": "Quiet desert highways, silent alienation, acoustic introspection, Wim Wenders, Kelly Reichardt, Chantal Akerman, Paris Texas, First Cow, Jeanne Dielman, Nomadland"
    },
    {
        "name": "PERIOD ROMANTIC ELEGIES",
        "code_prefix": "PERIOD-ROMANCE",
        "color": "#e76f51",
        "description": "Historical longing, lush velvet costumes, secret love, Wong Kar-wai, Todd Haynes, Stanley Kubrick, In the Mood for Love, Barry Lyndon, Carol, Phantom Thread, Cold War"
    }
]

_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance")
_MACRO_EMBEDDINGS: Optional[np.ndarray] = None
_MICRO_EMBEDDINGS: Optional[np.ndarray] = None


def _get_macro_archetype_embeddings() -> np.ndarray:
    global _MACRO_EMBEDDINGS
    if _MACRO_EMBEDDINGS is None:
        npy_p = os.path.join(_DB_DIR, "macro_archetype_embs.npy")
        if os.path.exists(npy_p):
            try:
                _MACRO_EMBEDDINGS = np.load(npy_p)
            except Exception:
                pass
        if _MACRO_EMBEDDINGS is None:
            from services.embedding_service import compute_text_embeddings
            texts = [a["description"] for a in MACRO_ARCHETYPES]
            _MACRO_EMBEDDINGS = compute_text_embeddings(texts)
    return _MACRO_EMBEDDINGS


def _get_micro_archetype_embeddings() -> np.ndarray:
    global _MICRO_EMBEDDINGS
    if _MICRO_EMBEDDINGS is None:
        npy_p = os.path.join(_DB_DIR, "micro_archetype_embs.npy")
        if os.path.exists(npy_p):
            try:
                _MICRO_EMBEDDINGS = np.load(npy_p)
            except Exception:
                pass
        if _MICRO_EMBEDDINGS is None:
            from services.embedding_service import compute_text_embeddings
            texts = [a["description"] for a in MICRO_ARCHETYPES]
            _MICRO_EMBEDDINGS = compute_text_embeddings(texts)
    return _MICRO_EMBEDDINGS


def _generate_sector_label(
    cluster_items: List[Dict[str, Any]],
    sector_idx: int,
    used_names: Optional[set] = None,
    is_macro: bool = True
) -> Dict[str, Any]:
    """
    Uses FastEmbed semantic embeddings to classify items against Macro or Micro archetypes.
    """
    from collections import Counter
    from services.embedding_service import compute_text_embeddings
    if used_names is None:
        used_names = set()

    genres = Counter()
    directors = Counter()
    titles = []
    years = []
    tags = []

    for it in cluster_items:
        t = it.get("title") or it.get("movie") or ""
        if t:
            titles.append(t)
        d = it.get("director")
        if d and d.lower() not in ["unknown", "n/a", ""]:
            directors[d] += 1
        for g in str(it.get("genre", "")).split(","):
            cg = g.strip()
            if cg and cg.lower() != "unknown":
                genres[cg] += 1
        yr = it.get("year") or it.get("p_year")
        if yr:
            try:
                years.append(int(str(yr)[:4]))
            except Exception:
                pass
        tg = it.get("tags") or it.get("frontier_desc") or ""
        if tg:
            tags.append(tg)

    top_genres = [g for g, _ in genres.most_common(4)]
    top_dirs = [d for d, _ in directors.most_common(2)]
    sample_titles = titles[:6]

    doc = f"Genres: {', '.join(top_genres)}. Directors: {', '.join(top_dirs)}. Landmarks: {', '.join(sample_titles)}. Atmosphere: {' '.join(tags[:5])}"

    archetypes = MACRO_ARCHETYPES if is_macro else MICRO_ARCHETYPES
    archetype_embs = _get_macro_archetype_embeddings() if is_macro else _get_micro_archetype_embeddings()
    doc_emb = compute_text_embeddings([doc])

    sims = cosine_similarity(doc_emb, archetype_embs)[0]
    ranked_indices = np.argsort(sims)[::-1]

    chosen_idx = int(ranked_indices[0])
    for idx in ranked_indices:
        if archetypes[idx]["name"] not in used_names:
            chosen_idx = int(idx)
            break

    chosen = archetypes[chosen_idx]

    dirs_str = ", ".join(top_dirs) if top_dirs else (sample_titles[0] if sample_titles else "Cinephile Core")
    min_yr = min(years) if years else 1970
    max_yr = max(years) if years else 2024
    yr_str = f"{min_yr}–{max_yr}" if min_yr != max_yr else str(min_yr)

    subtitle = f"Anchored by {dirs_str} • {yr_str}"
    code = chosen.get("code_prefix", f"CLUST-{sector_idx + 1:02d}") if is_macro else f"MIC-{sector_idx + 1:02d}"

    return {
        "name": chosen["name"],
        "code": code,
        "subtitle": subtitle,
        "color": chosen["color"],
        "code_prefix": chosen["code_prefix"],
        "similarity": float(sims[chosen_idx])
    }


def _fetch_user_watchlist_safe(user_id: int) -> List[Dict[str, Any]]:
    try:
        pw = get_or_create_personal_watchlist(user_id)
        if pw and pw.get("id"):
            return get_watchlist_items(pw["id"]) or []
    except Exception as e:
        logger.debug(f"Error fetching watchlist: {e}")
    return []


def _extract_density_contours(pts, levels=None, grid_size=56, pad=45.0):
    """
    Given 2D points (N, 2), computes a 2D smoothed density grid and extracts
    organic polygon contour paths at multiple density levels.
    """
    if levels is None:
        levels = [0.25, 0.55, 0.80]
    if len(pts) < 3:
        return []
    pts_arr = np.asarray(pts, dtype=np.float32)
    min_x, max_x = float(np.min(pts_arr[:, 0])) - pad, float(np.max(pts_arr[:, 0])) + pad
    min_y, max_y = float(np.min(pts_arr[:, 1])) - pad, float(np.max(pts_arr[:, 1])) + pad

    if max_x - min_x < 1e-3 or max_y - min_y < 1e-3:
        return []

    H, xedges, yedges = np.histogram2d(
        pts_arr[:, 0], pts_arr[:, 1],
        bins=grid_size,
        range=[[min_x, max_x], [min_y, max_y]]
    )

    sigma = max(2.5, min(6.0, len(pts_arr) / 8.0))
    smooth_H = gaussian_filter(H.T, sigma=sigma)
    max_val = float(np.max(smooth_H))
    if max_val <= 1e-6:
        return []

    norm_H = smooth_H / max_val

    # Center ray-marching at the actual peak mode of the density field, guaranteeing norm_H = 1.0
    max_gy, max_gx = np.unravel_index(np.argmax(smooth_H), smooth_H.shape)
    cx = min_x + (max_gx + 0.5) / grid_size * (max_x - min_x)
    cy = min_y + (max_gy + 0.5) / grid_size * (max_y - min_y)

    r_max = math.hypot(max_x - min_x, max_y - min_y) * 0.75
    r_steps = np.linspace(10.0, r_max, 50)
    angles = np.linspace(0, 2 * np.pi, 36, endpoint=False)

    contours = []
    for lvl in levels:
        contour_pts = []
        for theta in angles:
            target_r = r_max * 0.35
            for r in r_steps:
                wx = cx + r * math.cos(theta)
                wy = cy + r * math.sin(theta)
                gx = int((wx - min_x) / (max_x - min_x) * (grid_size - 1))
                gy = int((wy - min_y) / (max_y - min_y) * (grid_size - 1))
                if 0 <= gx < grid_size and 0 <= gy < grid_size:
                    if norm_H[gy, gx] < lvl:
                        target_r = r
                        break
                else:
                    target_r = r
                    break
            contour_pts.append([round(float(cx + target_r * math.cos(theta)), 1), round(float(cy + target_r * math.sin(theta)), 1)])

        pts_mat = np.array(contour_pts)
        span = np.max(pts_mat, axis=0) - np.min(pts_mat, axis=0)
        if span[0] > 10.0 and span[1] > 10.0:
            contours.append({
                "level": round(float(lvl), 2),
                "elevation": f"DENSITY {round(float(lvl), 2):.2f}",
                "polygon": contour_pts
            })
    return contours


def invalidate_galaxy_cache(user_id: Optional[int] = None):
    """Clears the in-memory galaxy cache for a specific user or entirely."""
    global _GALAXY_CACHE
    if user_id is not None:
        _GALAXY_CACHE.pop(user_id, None)
    else:
        _GALAXY_CACHE.clear()


def build_taste_cosmos_data(user_id: int, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Main entry point: extracts user data, loads candidate recommendations, builds multi-dimensional
    feature matrix with collision-free auteur mapping, computes negative gravity voids for low-rated films,
    runs 2D manifold projection with repulsor physics, and clusters sectors.
    """
    now = time.time()
    if not force_refresh and user_id in _GALAXY_CACHE:
        cached_time, cached_payload = _GALAXY_CACHE[user_id]
        if now - cached_time < _CACHE_TTL_SECONDS:
            c_stars = cached_payload.get("stars", []) if cached_payload else []
            has_missing_tv_posters = any(
                s.get("tv_show") in [1, "1", True] and not (s.get("poster") and str(s.get("poster")).startswith("http"))
                for s in c_stars
            )
            cached_watched = sum(1 for s in c_stars if s.get("is_watched"))
            is_valid = not has_missing_tv_posters and len(c_stars) > 0
            if is_valid:
                if cached_watched == 0:
                    db_m = get_movies(user_id) or []
                    if len(db_m) > 0:
                        is_valid = False
                if is_valid:
                    print(f"[COSMOS SERVICE] Returning cached galaxy for user {user_id} (age: {round(now - cached_time, 1)}s, {cached_watched} watched)", flush=True)
                    return cached_payload

    t_start = time.time()
    print(f"[COSMOS SERVICE] >> Computing fresh galaxy for user {user_id}...", flush=True)

    # 1. Parallel Fetch of User Data from DB (Movies, Watchlist, Friends)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as executor:
        f_movies = executor.submit(get_movies, user_id)
        f_wl = executor.submit(_fetch_user_watchlist_safe, user_id)
        
        user_raw_movies = f_movies.result() or []
        watchlist_raw = f_wl.result() or []

    if not user_raw_movies:
        time.sleep(0.15)
        user_raw_movies = get_movies(user_id) or []

    t_db = time.time()
    print(f"[COSMOS SERVICE] DB fetched in {round(t_db - t_start, 3)}s: {len(user_raw_movies)} watched, {len(watchlist_raw)} watchlist items", flush=True)

    # Index watchlist titles and title_year combinations
    watchlist_exact_keys = set()
    watchlist_titles_only = set()
    for w in watchlist_raw:
        w_t = w.get("title")
        if not w_t:
            continue
        w_norm = _normalize_name(w_t)
        w_yr = str(w.get("p_year") or w.get("year") or "").strip()
        if w_yr:
            watchlist_exact_keys.add(f"{w_norm}_{w_yr}")
        else:
            watchlist_titles_only.add(w_norm)

    def _is_in_watchlist(item_title: str, item_year: Any) -> bool:
        t_norm = _normalize_name(item_title)
        y_norm = str(item_year or "").strip()
        if y_norm:
            if f"{t_norm}_{y_norm}" in watchlist_exact_keys:
                return True
            if t_norm in watchlist_titles_only and not any(k.startswith(f"{t_norm}_") for k in watchlist_exact_keys):
                return True
            return False
        else:
            return t_norm in watchlist_titles_only or any(k.startswith(f"{t_norm}_") for k in watchlist_exact_keys)

    # 2. Fetch Autonomous Candidates (Dynamic TMDB + Auteur + Friends + Canon)
    candidates = _fetch_autonomous_candidates(user_id, user_raw_movies)
    t_cand = time.time()
    print(f"[COSMOS SERVICE] Candidates fetched in {round(t_cand - t_db, 3)}s: {len(candidates)} candidates", flush=True)

    # 3. Build Combined Item Pool with Cosmic Void Classification
    pool: List[Dict[str, Any]] = []
    pool_keys = set()
    user_pool_items = {}

    # User watched movies (aggregating multiple viewing logs/rewatches for the same film)
    for m in user_raw_movies:
        title = m.get("movie") or "Untitled"
        year = str(m.get("p_year") or "")
        key = f"{_normalize_name(title)}_{year}"
        rating = int(m.get("rating") or 3)

        if key in user_pool_items:
            existing = user_pool_items[key]
            if rating > existing["rating"]:
                existing["rating"] = rating
                if rating <= 2:
                    existing["category"] = "void_repulsor"
                elif rating >= 5:
                    existing["category"] = "watched_5"
                elif rating == 4:
                    existing["category"] = "watched_4"
                else:
                    existing["category"] = "watched_standard"
            existing["rewatch"] = 1
            existing["view_count"] = existing.get("view_count", 1) + 1
        else:
            # Category assignment with Cosmic Void / Repulsor support
            if rating <= 2:
                cat = "void_repulsor"
            elif rating >= 5:
                cat = "watched_5"
            elif rating == 4:
                cat = "watched_4"
            else:
                cat = "watched_standard"

            item_dict = {
                "id": f"watched_{m.get('id') or m.get('lista_id') or key}",
                "title": title,
                "year": year,
                "director": m.get("director") or "Unknown",
                "genre": m.get("genre") or "Cinema",
                "poster": m.get("poster") or "",
                "rating": rating,
                "vote_average": m.get("vote_average") or m.get("rating_score"),
                "vote_count": m.get("vote_count"),
                "status": m.get("status", ""),
                "is_abandoned": bool(m.get("is_abandoned") or "abandon" in str(m.get("status", "")).lower() or "dnf" in str(m.get("status", "")).lower()),
                "completed": m.get("completed"),
                "category": cat,
                "tv_show": m.get("tv_show", 0),
                "cinema": m.get("cinema", 0),
                "rewatch": m.get("rewatch", 0),
                "season": m.get("season"),
                "tmdb_id": m.get("tmdb_id"),
                "v_date": m.get("v_date"),
                "is_watched": True,
                "is_watchlist": _is_in_watchlist(title, year),
                "source": "user_log",
                "view_count": 1
            }
            user_pool_items[key] = item_dict
            pool.append(item_dict)
            pool_keys.add(key)

    # Watchlist items that aren't already in watched pool
    for w in watchlist_raw:
        w_title = w.get("title") or "Untitled"
        w_year = str(w.get("p_year") or "")
        key = f"{_normalize_name(w_title)}_{w_year}"
        if key not in pool_keys:
            pool.append({
                "id": f"wl_{w.get('id') or key}",
                "title": w_title,
                "year": w_year,
                "director": w.get("director") or "Unknown",
                "genre": "Cinema",
                "poster": w.get("poster") or "",
                "rating": 0,
                "vote_average": w.get("vote_average") or w.get("rating_score"),
                "vote_count": w.get("vote_count"),
                "category": "watchlist",
                "tv_show": w.get("tv_show", 0),
                "season": w.get("season"),
                "tmdb_id": w.get("tmdb_id"),
                "cinema": 0,
                "rewatch": 0,
                "is_watched": False,
                "is_watchlist": True,
                "source": "watchlist"
            })
            pool_keys.add(key)

    # Candidate recommendations
    for c in candidates:
        c_title = c.get("title") or "Untitled"
        c_year = str(c.get("year") or "")
        key = f"{_normalize_name(c_title)}_{c_year}"
        if key not in pool_keys:
            pool.append({
                "id": f"rec_{key}",
                "title": c_title,
                "year": c_year,
                "director": c.get("director") or "Unknown",
                "genre": c.get("genre") or "Cinema",
                "poster": c.get("poster") or "",
                "rating": 0,
                "category": "uncharted_beacon",
                "tv_show": c.get("tv_show", 0),
                "season": c.get("season"),
                "tmdb_id": c.get("tmdb_id"),
                "cinema": 0,
                "rewatch": 0,
                "is_watched": False,
                "is_watchlist": _is_in_watchlist(c_title, c_year),
                "source": c.get("source", "autonomous_discovery"),
                "tags": c.get("tags", ""),
                "vote_average": c.get("vote_average") or c.get("rating_score"),
                "vote_count": c.get("vote_count")
            })
            pool_keys.add(key)

    # Fallback to curated landmarks if pool is small
    if len(pool) < 15:
        for lm in CURATED_LANDMARKS:
            key = f"{_normalize_name(lm['title'])}_{lm['year']}"
            if key not in pool_keys:
                pool.append({
                    "id": f"rec_{key}",
                    "title": lm["title"],
                    "year": str(lm["year"]),
                    "director": lm["director"],
                    "genre": lm["genre"],
                    "poster": lm["poster"],
                    "rating": 0,
                    "category": "uncharted_beacon",
                    "tv_show": lm.get("tv_show", 0),
                    "cinema": 0,
                    "rewatch": 0,
                    "is_watched": False,
                    "is_watchlist": False,
                    "source": "landmark_canon",
                    "tags": lm.get("tags", ""),
                    "vote_average": lm.get("rating_score", 8.5),
                    "vote_count": 2000
                })
                pool_keys.add(key)

    # 3.9 Enrich pool with canonical metadata (overview, keywords, multi-genres, craft) from Supabase / catalog cache
    try:
        from services.catalog_service import enrich_pool_items
        catalog_crafts = enrich_pool_items(pool)
    except Exception as e:
        logger.debug(f"Catalog enrichment notice in cosmos: {e}")
        catalog_crafts = {}

    # 4. Build Collision-Free Auteur & Lead Cast Indexers
    from collections import Counter
    director_counts = Counter()
    for item in pool:
        d = item.get("director")
        if d and d.lower() not in ["unknown", "n/a", ""]:
            director_counts[_normalize_name(d)] += 1

    # Top 31 distinct directors get dedicated, collision-free slot index 0..30
    director_indexer = {
        name: idx for idx, (name, _) in enumerate(director_counts.most_common(31))
    }

    # Cast co-occurrence indexer for top recurring actors
    cast_indexer = {}
    lead_actors_pool = [
        "ryangosling", "leonardodicaprio", "songkangho", "tonyleung", 
        "christianbale", "willemdafoe", "scarlettjohansson", "alpacino"
    ]
    for idx, act in enumerate(lead_actors_pool):
        cast_indexer[act] = idx

    struct_matrix = np.array(
        [_extract_feature_vector(item, director_indexer, cast_indexer) for item in pool], 
        dtype=np.float32
    )
    struct_norm = struct_matrix / (np.linalg.norm(struct_matrix, axis=1, keepdims=True) + 1e-9)

    # 4b. Fetch / resolve craft credits (Cinematographer, Composer, Writer, Studios)
    crafts_by_key = batch_get_movie_crafts(pool)
    if catalog_crafts:
        for k, c in catalog_crafts.items():
            if k not in crafts_by_key or not crafts_by_key[k].get("cinematographer"):
                crafts_by_key[k] = c

    # 4c. Heterogeneous Cinephile Knowledge Graph & LightGCN Graph Convolution
    try:
        graph_embs, graph_affinities, graph_explanations, graph_node_stats = build_and_run_lightgcn(
            pool, crafts_by_key, user_id=user_id, return_stats=True
        )
    except Exception as e:
        logger.warning(f"LightGCN graph execution fallback: {e}")
        graph_embs = np.zeros((len(pool), 64), dtype=np.float32)
        graph_affinities = [0.0] * len(pool)
        graph_explanations = {}
        graph_node_stats = {}

    # Dense Semantic Embeddings (FastEmbed ONNX 384D with SQLite cache)
    try:
        semantic_matrix = compute_semantic_embeddings(pool)
        semantic_norm = semantic_matrix / (np.linalg.norm(semantic_matrix, axis=1, keepdims=True) + 1e-9)
    except Exception as e:
        logger.warning(f"Semantic embedding blend fallback: {e}")
        semantic_norm = np.zeros((len(pool), 384), dtype=np.float32)

    n_samples = len(pool)
    user_history_len = len(user_raw_movies)

    # 4e. Independent Taste Signals & Training-Free Adaptive Multi-Modal Fusion (S, E, G)
    pos_indices = [idx for idx, it in enumerate(pool) if it.get("is_watched") and it.get("rating", 0) >= 4]
    neg_indices = [idx for idx, it in enumerate(pool) if it.get("category") == "void_repulsor"]

    # 1. Structured similarity S
    if pos_indices:
        pos_weights = np.array([1.5 if pool[i].get("rating", 0) >= 5 else 1.0 for i in pos_indices], dtype=np.float32)
        pos_weights /= np.sum(pos_weights)
        user_struct_centroid = np.sum(struct_norm[pos_indices] * pos_weights[:, np.newaxis], axis=0, keepdims=True)
        user_struct_centroid /= (np.linalg.norm(user_struct_centroid) + 1e-9)
        raw_s_scores = cosine_similarity(struct_norm, user_struct_centroid).flatten()

        # 2. Semantic similarity E with temperature-controlled soft positive-mode aggregation
        try:
            raw_e_scores, positive_modes, pos_responsibilities, dominant_pos_modes = execute_positive_mode_pipeline(
                pool=pool,
                semantic_norm=semantic_norm,
                user_raw_movies=user_raw_movies,
                tau=0.15
            )
        except Exception as e:
            logger.warning(f"Positive mode pipeline fallback: {e}")
            user_sem_centroid = np.sum(semantic_norm[pos_indices] * pos_weights[:, np.newaxis], axis=0, keepdims=True)
            user_sem_centroid /= (np.linalg.norm(user_sem_centroid) + 1e-9)
            raw_e_scores = cosine_similarity(semantic_norm, user_sem_centroid).flatten()
            positive_modes = []
            pos_responsibilities = np.zeros((n_samples, 0), dtype=np.float32)
            dominant_pos_modes = np.full(n_samples, -1, dtype=int)
    else:
        user_struct_centroid = np.mean(struct_norm, axis=0, keepdims=True)
        raw_s_scores = cosine_similarity(struct_norm, user_struct_centroid).flatten()
        user_sem_centroid = np.mean(semantic_norm, axis=0, keepdims=True)
        raw_e_scores = cosine_similarity(semantic_norm, user_sem_centroid).flatten()
        positive_modes = []
        pos_responsibilities = np.zeros((n_samples, 0), dtype=np.float32)
        dominant_pos_modes = np.full(n_samples, -1, dtype=int)

    # 3. Graph similarity G
    raw_g_scores = np.array(graph_affinities, dtype=np.float32)

    # 4. Training-Free Adaptive Multi-Modal Fusion
    try:
        fused_pos_sims, hybrid_matrix, fusion_diagnostics = execute_adaptive_fusion(
            items=pool,
            raw_s_scores=raw_s_scores,
            raw_e_scores=raw_e_scores,
            raw_g_scores=raw_g_scores,
            struct_norm=struct_norm,
            semantic_norm=semantic_norm,
            graph_embs=graph_embs,
            graph_node_stats=graph_node_stats,
            crafts_by_key=crafts_by_key,
            user_history_len=user_history_len
        )
    except Exception as e:
        logger.warning(f"Adaptive fusion fallback to static blend: {e}")
        hybrid_matrix = np.column_stack([0.55 * struct_norm, 0.30 * semantic_norm, 0.15 * graph_embs])
        hybrid_matrix = hybrid_matrix / (np.linalg.norm(hybrid_matrix, axis=1, keepdims=True) + 1e-9)
        fused_pos_sims = 0.55 * raw_s_scores + 0.30 * raw_e_scores + 0.15 * raw_g_scores
        fusion_diagnostics = [{
            "confidence": {"structured": 0.55, "semantic": 0.30, "graph": 0.15, "total": 0.5},
            "effective_weights": {"structured": 0.55, "semantic": 0.30, "graph": 0.15},
            "agreement_score": 1.0,
            "variance": 0.0,
            "is_exploratory": False,
            "low_evidence": False,
            "normalized_modalities": {"structured": 0.5, "semantic": 0.5, "graph": 0.5}
        } for _ in pool]

    # Telemetry logging of effective weights
    if fusion_diagnostics:
        w_s_mean = float(np.mean([d["effective_weights"]["structured"] for d in fusion_diagnostics]))
        w_e_mean = float(np.mean([d["effective_weights"]["semantic"] for d in fusion_diagnostics]))
        w_g_mean = float(np.mean([d["effective_weights"]["graph"] for d in fusion_diagnostics]))
        n_exploratory = sum(1 for d in fusion_diagnostics if d["is_exploratory"])
        n_low_evidence = sum(1 for d in fusion_diagnostics if d["low_evidence"])
        logger.info(
            f"[ADAPTIVE FUSION] Galaxy computed with {n_samples} items: "
            f"Mean Weights (S: {w_s_mean:.2f}, E: {w_e_mean:.2f}, G: {w_g_mean:.2f}) | "
            f"Exploratory Discoveries: {n_exploratory} | Low Evidence Beacons: {n_low_evidence}"
        )

    # 5. Direct Macro-Realm Semantic Partitioning (Tier 1)
    # Classifies every film into its primary Macro Realm with category guardrails
    macro_embs = _get_macro_archetype_embeddings()
    macro_sims = cosine_similarity(semantic_norm, macro_embs)  # N x 6

    # Categorical domain priors
    for i, it in enumerate(pool):
        g_str = str(it.get("genre", "")).lower()
        t_str = str(it.get("tags", "")).lower() + " " + str(it.get("title", "")).lower()
        if "animation" in g_str or "anime" in t_str:
            macro_sims[i, 0] += 0.45  # Realm 0: Animation
        if "crime" in g_str or "noir" in t_str or "thriller" in g_str or "mystery" in g_str:
            macro_sims[i, 1] += 0.22  # Realm 1: Noir, Crime & Psychological
        if "drama" in g_str and "animation" not in g_str and "sci-fi" not in g_str and "comedy" not in g_str and "action" not in g_str:
            macro_sims[i, 2] += 0.22  # Realm 2: Arthouse & Humanist Core
        if "sci-fi" in g_str or "science fiction" in g_str or "space" in t_str:
            macro_sims[i, 3] += 0.26  # Realm 3: Sci-Fi Cosmos
        if "comedy" in g_str and "animation" not in g_str:
            macro_sims[i, 4] += 0.20  # Realm 4: Satirical Wit & Pop Indie
        if "action" in g_str and "animation" not in g_str and "sci-fi" not in g_str:
            macro_sims[i, 5] += 0.20  # Realm 5: Action Frontier

    raw_macro_labels = np.argmax(macro_sims, axis=1)

    # Active Macro Realms (only realms with stars, preserve clean order)
    active_macro_indices = []
    for k in range(len(MACRO_ARCHETYPES)):
        if np.any(raw_macro_labels == k):
            active_macro_indices.append(k)

    n_active = len(active_macro_indices)
    macro_to_active_pos = {k: pos for pos, k in enumerate(active_macro_indices)}
    macro_labels = np.array([macro_to_active_pos[k] for k in raw_macro_labels])

    # 6. Multi-Mode Negative Preference Engine & Feature-Level Veto System
    try:
        neg_risks, veto_factors, veto_diagnostics, negative_modes = execute_negative_mode_pipeline(
            pool=pool,
            hybrid_matrix=hybrid_matrix,
            user_raw_movies=user_raw_movies
        )
    except Exception as e:
        logger.warning(f"Negative mode pipeline fallback: {e}")
        neg_risks = np.zeros(n_samples, dtype=np.float32)
        veto_factors = np.ones(n_samples, dtype=np.float32)
        veto_diagnostics = [{"veto_factor": 1.0, "is_vetoed": False, "reasons": []} for _ in range(n_samples)]
        negative_modes = []

    # Net Gravitational Affinity
    # Explicit Mathematical Grouping:
    #   net_affinity(i) = (s_pos(i) - repulsion_penalty(i)) * veto_factor(i) * quality_factor(i)
    #
    # NOTE ON OPERATOR PRECEDENCE:
    # In unparenthesized expressions such as:
    #   0.65p + 0.35g - 0.45 * penalty * quality
    # multiplication binds first to (0.45 * penalty * quality), which would erroneously
    # amplify the penalty on high-quality films and provide zero quality boost to films with zero penalty.
    # The INTENDED algebraic grouping is strictly:
    #   (s_pos - penalty) * quality
    # where quality_factor scales the net candidate affinity (acclaim prior for unwatched beacons),
    # NOT just the repulsion penalty.
    # 1. Personalized Gated Net Affinity (Repulsion penalty + Feature veto gate)
    vetoed_net_scores = np.zeros(n_samples, dtype=np.float32)
    for idx in range(n_samples):
        s_pos = float(fused_pos_sims[idx])
        s_risk = float(neg_risks[idx])
        v_fac = float(veto_factors[idx])

        # Step 1: Multi-mode repulsion penalty: neg_risk(i) = max_k [ q_k * cos(h_i, c_k^-) ]
        repulsion_penalty = 0.45 * max(0.0, s_risk - 0.30)
        raw_net = max(0.0, s_pos - repulsion_penalty)

        # Step 2: Feature-level veto gate (Director, Genre aversion, Semantic taste mismatch, Execution quality)
        vetoed_net_scores[idx] = raw_net * v_fac

    # Step 3: Bayesian Quality Prior with Vote-Count Shrinkage
    # Q_i = (v_i / (v_i + m)) * R_i + (m / (v_i + m)) * C
    # Applied additively (scaled by veto factor):
    #   net_score_i = max(0.0, vetoed_net_i + alpha * v_fac_i * ((Q_i - C) / 10.0))
    # Multiplication completely eliminated to avoid heteroskedastic score distortion.
    net_scores, quality_diagnostics, quality_meta = batch_apply_quality_prior(
        pool=pool,
        candidate_vetoed_scores=vetoed_net_scores,
        veto_factors=veto_factors,
        mode="additive"
    )

    # Normalized affinity [0.0, 1.0] for radial depth modulation in constellations
    min_net = float(np.min(net_scores))
    max_net = float(np.max(net_scores))
    net_range = max_net - min_net
    if net_range > 1e-5:
        affinity_scores = np.clip((net_scores - min_net) / net_range, 0.0, 1.0)
    else:
        affinity_scores = np.full(n_samples, 0.5, dtype=np.float32)

    # Probabilistic Calibration: P(positive interaction | raw_score) & Honest Match Score
    try:
        calibrated_probs, match_scores, calibration_meta = calibrate_scores(
            candidate_net_scores=net_scores,
            user_raw_movies=user_raw_movies,
            pool_items=pool
        )
    except Exception as e:
        logger.warning(f"Calibration pipeline fallback: {e}")
        calibrated_probs = np.clip(net_scores, 0.05, 0.98).astype(np.float32)
        match_scores = np.clip(np.round(70 + (net_scores * 29)), 55, 99).astype(np.int32)
        calibration_meta = {"calibrator_type": "fallback", "error": str(e)}

    # Backward compatible alias for array
    match_pct_arr = match_scores

    # 7. Continuous Segmented Manifold Geometry with Radial Affinity Modulation
    scaled_x = np.zeros(n_samples, dtype=np.float32)
    scaled_y = np.zeros(n_samples, dtype=np.float32)
    target_x = np.zeros(n_samples, dtype=np.float32)
    target_y = np.zeros(n_samples, dtype=np.float32)
    micro_lookup = {}
    sectors = []
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))  # ~2.39996 rad

    # Map each film into its macro realm territory with local PCA and radial affinity blending
    for pos, k in enumerate(active_macro_indices):
        c_mask = (raw_macro_labels == k)
        c_indices = np.where(c_mask)[0]
        n_c = len(c_indices)
        if n_c == 0:
            continue

        # Base angle and center for this macro territory (Expansive 440px Radius for Clear Topological Valleys)
        sec_base_angle = (2.0 * math.pi * pos / n_active) - (math.pi / 2.0)
        macro_dist = 440.0
        macro_cx = macro_dist * math.cos(sec_base_angle)
        macro_cy = macro_dist * math.sin(sec_base_angle)

        c_hybrid = hybrid_matrix[c_indices]
        macro_info = MACRO_ARCHETYPES[k]
        macro_items = [pool[i] for i in c_indices]

        # Tier 2: Micro-Sub-Clustering within this Macro Realm
        micro_clusters = []
        used_micro_names = set()
        n_micro = max(2, min(4, n_c // 14)) if n_c >= 8 else 1

        if n_micro > 1:
            micro_kmeans = KMeans(n_clusters=n_micro, random_state=42, n_init=10).fit(c_hybrid)
            sub_labels = micro_kmeans.labels_

            for m_id in range(n_micro):
                m_sub_mask = (sub_labels == m_id)
                m_sub_indices = c_indices[m_sub_mask]
                n_mc = len(m_sub_indices)
                if n_mc == 0:
                    continue

                # Expansive dedicated territory for each micro-constellation (145px offset from macro center)
                local_mc_angle = sec_base_angle + (m_id - (n_micro - 1) / 2.0) * 1.35
                mc_offset_dist = 145.0
                dyn_mc_cx = macro_cx + mc_offset_dist * math.cos(local_mc_angle)
                dyn_mc_cy = macro_cy + mc_offset_dist * math.sin(local_mc_angle)

                # Local PCA for continuous 2D coordinate placement + Radial Affinity Modulation
                m_hybrid = hybrid_matrix[m_sub_indices]
                spread_r = max(80.0, 18.0 * math.sqrt(n_mc))
                if n_mc >= 3:
                    pca_loc = PCA(n_components=2, random_state=42)
                    c_loc = pca_loc.fit_transform(m_hybrid)
                    std_x = float(np.std(c_loc[:, 0])) or 1.0
                    std_y = float(np.std(c_loc[:, 1])) or 1.0
                    norm_x = c_loc[:, 0] / std_x
                    norm_y = c_loc[:, 1] / std_y

                    # Deterministic PCA orientation alignment (prevents axis flip across sessions)
                    max_abs_x = int(np.argmax(np.abs(norm_x)))
                    if norm_x[max_abs_x] < 0:
                        norm_x = -norm_x
                    max_abs_y = int(np.argmax(np.abs(norm_y)))
                    if norm_y[max_abs_y] < 0:
                        norm_y = -norm_y

                    r_pca = np.hypot(norm_x, norm_y) * (spread_r * 0.38)
                    theta_pca = np.arctan2(norm_y, norm_x)

                    for i_sub, g_idx in enumerate(m_sub_indices):
                        a_i = float(affinity_scores[g_idx])
                        r_min = 14.0
                        r_max = spread_r * 0.72
                        r_aff = r_min + (1.0 - a_i) * (r_max - r_min)

                        # Controlled coupling: 60% Semantic PCA radius + 40% User Affinity radius
                        r_blended = 0.60 * float(r_pca[i_sub]) + 0.40 * r_aff
                        th = float(theta_pca[i_sub])

                        jit_angle = ((g_idx * 137.5) * math.pi / 180.0)
                        jit_r = ((g_idx * 23) % 17) * 0.5

                        tx = dyn_mc_cx + r_blended * math.cos(th) + jit_r * math.cos(jit_angle)
                        ty = dyn_mc_cy + r_blended * math.sin(th) + jit_r * math.sin(jit_angle)

                        target_x[g_idx] = tx
                        target_y[g_idx] = ty
                        scaled_x[g_idx] = tx
                        scaled_y[g_idx] = ty
                else:
                    for i_sub, g_idx in enumerate(m_sub_indices):
                        ang = i_sub * (2.0 * math.pi / max(1, n_mc))
                        a_i = float(affinity_scores[g_idx])
                        r_aff = 20.0 + (1.0 - a_i) * 35.0
                        tx = dyn_mc_cx + r_aff * math.cos(ang)
                        ty = dyn_mc_cy + r_aff * math.sin(ang)

                        target_x[g_idx] = tx
                        target_y[g_idx] = ty
                        scaled_x[g_idx] = tx
                        scaled_y[g_idx] = ty

                micro_code = f"MIC-{pos+1:02d}{chr(65 + m_id)}"
                mc_obj = {
                    "id": f"micro_{pos}_{m_id}",
                    "code": micro_code,
                    "name": macro_info["name"],
                    "subtitle": f"Cluster {m_id + 1} • {n_mc} Works",
                    "color": macro_info["color"],
                    "cx": round(dyn_mc_cx, 1),
                    "cy": round(dyn_mc_cy, 1),
                    "radius": round(spread_r + 20.0, 1),
                    "count": n_mc,
                    "density_contours": []
                }
                micro_clusters.append(mc_obj)
                for idx_item in m_sub_indices:
                    micro_lookup[idx_item] = mc_obj
        else:
            # Single micro constellation
            dyn_mc_cx = macro_cx
            dyn_mc_cy = macro_cy
            spread_r = max(80.0, 18.0 * math.sqrt(n_c))
            if n_c >= 3:
                pca_loc = PCA(n_components=2, random_state=42)
                c_loc = pca_loc.fit_transform(c_hybrid)
                std_x = float(np.std(c_loc[:, 0])) or 1.0
                std_y = float(np.std(c_loc[:, 1])) or 1.0
                norm_x = c_loc[:, 0] / std_x
                norm_y = c_loc[:, 1] / std_y

                # Deterministic PCA orientation alignment
                max_abs_x = int(np.argmax(np.abs(norm_x)))
                if norm_x[max_abs_x] < 0:
                    norm_x = -norm_x
                max_abs_y = int(np.argmax(np.abs(norm_y)))
                if norm_y[max_abs_y] < 0:
                    norm_y = -norm_y

                r_pca = np.hypot(norm_x, norm_y) * (spread_r * 0.38)
                theta_pca = np.arctan2(norm_y, norm_x)

                for i_sub, g_idx in enumerate(c_indices):
                    a_i = float(affinity_scores[g_idx])
                    r_min = 14.0
                    r_max = spread_r * 0.72
                    r_aff = r_min + (1.0 - a_i) * (r_max - r_min)

                    r_blended = 0.60 * float(r_pca[i_sub]) + 0.40 * r_aff
                    th = float(theta_pca[i_sub])

                    jit_angle = ((g_idx * 137.5) * math.pi / 180.0)
                    jit_r = ((g_idx * 23) % 17) * 0.5

                    tx = dyn_mc_cx + r_blended * math.cos(th) + jit_r * math.cos(jit_angle)
                    ty = dyn_mc_cy + r_blended * math.sin(th) + jit_r * math.sin(jit_angle)

                    target_x[g_idx] = tx
                    target_y[g_idx] = ty
                    scaled_x[g_idx] = tx
                    scaled_y[g_idx] = ty
            else:
                for i_sub, g_idx in enumerate(c_indices):
                    ang = i_sub * (2.0 * math.pi / max(1, n_c))
                    a_i = float(affinity_scores[g_idx])
                    r_aff = 20.0 + (1.0 - a_i) * 35.0
                    tx = dyn_mc_cx + r_aff * math.cos(ang)
                    ty = dyn_mc_cy + r_aff * math.sin(ang)

                    target_x[g_idx] = tx
                    target_y[g_idx] = ty
                    scaled_x[g_idx] = tx
                    scaled_y[g_idx] = ty

            micro_code = f"MIC-{pos+1:02d}A"
            mc_obj = {
                "id": f"micro_{pos}_0",
                "code": micro_code,
                "name": macro_info["name"],
                "subtitle": f"{n_c} Works",
                "color": macro_info["color"],
                "cx": round(dyn_mc_cx, 1),
                "cy": round(dyn_mc_cy, 1),
                "radius": round(spread_r + 20.0, 1),
                "count": n_c,
                "density_contours": []
            }
            micro_clusters.append(mc_obj)
            for idx_item in c_indices:
                micro_lookup[idx_item] = mc_obj

        # Vectorized N-Body Anti-Collision Relaxation with Restoring Anchor Spring and Hard Clamping
        if len(c_indices) > 1:
            idx_arr = np.array(c_indices, dtype=np.int32)
            px = scaled_x[idx_arr].copy()
            py = scaled_y[idx_arr].copy()
            t_px = target_x[idx_arr].copy()
            t_py = target_y[idx_arr].copy()
            min_star_dist = 38.0
            k_anchor = 0.12
            max_disp = 28.0

            for _ in range(40):
                dx = px[:, None] - px[None, :]
                dy = py[:, None] - py[None, :]
                d = np.hypot(dx, dy)
                np.fill_diagonal(d, np.inf)

                too_close = d < min_star_dist
                if not np.any(too_close):
                    break

                safe_d = np.where(d < 1e-4, 1.0, d)
                overlap = np.where(too_close, (min_star_dist - d) * 0.5, 0.0)

                fx = np.sum(np.where(too_close, (dx / safe_d) * overlap, 0.0), axis=1)
                fy = np.sum(np.where(too_close, (dy / safe_d) * overlap, 0.0), axis=1)

                # Restoring anchor spring force towards semantic/affinity target
                fx += (t_px - px) * k_anchor
                fy += (t_py - py) * k_anchor

                px += fx
                py += fy

                # Hard clamp displacement from anchor target (guarantees zero neighborhood drift)
                disp = np.hypot(px - t_px, py - t_py)
                over_disp = disp > max_disp
                scale_disp = np.where(over_disp, max_disp / np.maximum(disp, 1e-4), 1.0)
                px = t_px + (px - t_px) * scale_disp
                py = t_py + (py - t_py) * scale_disp

            scaled_x[idx_arr] = px
            scaled_y[idx_arr] = py

        # Extract top directors/era for subtitle
        directors_cnt = Counter([it.get("director") for it in macro_items if it.get("director") and it.get("director").lower() not in ["unknown", "n/a", ""]])
        top_dirs = [d for d, _ in directors_cnt.most_common(2)]
        years = []
        for it in macro_items:
            yr = it.get("year") or it.get("p_year")
            if yr:
                try:
                    years.append(int(str(yr)[:4]))
                except Exception:
                    pass
        dirs_str = ", ".join(top_dirs) if top_dirs else "Cinephile Core"
        min_yr = min(years) if years else 1970
        max_yr = max(years) if years else 2024
        yr_str = f"{min_yr}–{max_yr}" if min_yr != max_yr else str(min_yr)
        macro_subtitle = f"Anchored by {dirs_str} • {yr_str}"

        dyn_macro_cx = float(np.mean(scaled_x[c_indices]))
        dyn_macro_cy = float(np.mean(scaled_y[c_indices]))
        dyn_macro_r = float(np.max(np.hypot(scaled_x[c_indices] - dyn_macro_cx, scaled_y[c_indices] - dyn_macro_cy))) + 28.0

        n_anchors = len([i for i in c_indices if pool[i].get("rating", 0) >= 4])
        elevation_val = int(480 + min(920, n_c * 7 + n_anchors * 40))

        # Extract Organic Topographic Density Contours (3 Clean Mathematical Isoclines)
        c_pts = [[float(scaled_x[i]), float(scaled_y[i])] for i in c_indices]
        density_contours = _extract_density_contours(c_pts, levels=[0.25, 0.55, 0.80])

        sec_obj = {
            "id": f"sector_{pos}",
            "code": macro_info.get("code_prefix", f"CLUST-{pos+1:02d}"),
            "name": macro_info["name"],
            "subtitle": macro_subtitle,
            "color": macro_info["color"],
            "cx": round(dyn_macro_cx, 1),
            "cy": round(dyn_macro_cy, 1),
            "radius": round(dyn_macro_r, 1),
            "cov_x": round(max(35.0, float(np.std(scaled_x[c_indices]))), 1),
            "cov_y": round(max(35.0, float(np.std(scaled_y[c_indices]))), 1),
            "elevation": f"DENSITY {min(0.99, round(elevation_val / 1400.0, 2)):.2f}",
            "density_contours": density_contours,
            "count": n_c,
            "micro_clusters": micro_clusters
        }
        sectors.append(sec_obj)

    # 8. Organic Inverse-Square Repulsive Potential Field for Negative Voids (In-situ, Zero Coordinate Exile!)
    if neg_indices:
        # Subtle localized repulsive push on nearby non-void stars (capped at 16px, void stars stay in-situ!)
        for _pass in range(4):
            damping = 0.8 ** _pass
            for v_idx in neg_indices:
                vx, vy = scaled_x[v_idx], scaled_y[v_idx]
                v_weight = 1.3 if pool[v_idx].get("rating", 0) <= 1 else 1.0
                for idx in range(n_samples):
                    if idx == v_idx or idx in neg_indices:
                        continue
                    dx = scaled_x[idx] - vx
                    dy = scaled_y[idx] - vy
                    dist = math.hypot(dx, dy)
                    if 2.0 < dist < 120.0:
                        rep_force = min(12.0, (1600.0 / (dist * dist + 200.0)) * math.exp(-dist / 80.0) * v_weight * damping)
                        push_x = (dx / dist) * rep_force
                        push_y = (dy / dist) * rep_force

                        # Respect maximum displacement from target
                        new_x = scaled_x[idx] + push_x
                        new_y = scaled_y[idx] + push_y
                        d_target = math.hypot(new_x - target_x[idx], new_y - target_y[idx])
                        if d_target <= 28.0:
                            scaled_x[idx] = new_x
                            scaled_y[idx] = new_y

    def is_valid_craft_name(val: Any) -> bool:
        if val is None:
            return False
        s = str(val).strip().lower()
        invalid_names = {
            "", "none", "null", "undefined", "unknown", "n/a", "na", "-", "--", 
            "[]", "{}", "nan", "showrunner", "showrunners", "various", "various directors", 
            "director", "directors", "creator", "creators", "uncredited", "writer", 
            "writers", "tba", "unknown director", "unknown showrunner"
        }
        return s not in invalid_names and len(s) >= 3

    def resolve_star_director(item_dir: Any, craft_dir: Any) -> str:
        i_str = str(item_dir).strip() if item_dir is not None else ""
        c_str = str(craft_dir).strip() if craft_dir is not None else ""
        if is_valid_craft_name(i_str):
            return i_str
        if is_valid_craft_name(c_str):
            return c_str
        return i_str or c_str or "Unknown"

    # 9. Assembling Stars payload
    stars: List[Dict[str, Any]] = []
    for idx, item in enumerate(pool):
        net_s = float(net_scores[idx])
        match_pct = int(match_pct_arr[idx])
        
        c_id = int(macro_labels[idx])
        sec_info = sectors[c_id] if c_id < len(sectors) else sectors[0]
        mc_info = micro_lookup.get(idx, sec_info.get("micro_clusters", [{}])[0])

        k_lookup = _normalize_key(item.get("title") or item.get("movie") or "", item.get("p_year") or item.get("year"))
        craft_data = crafts_by_key.get(k_lookup, {})
        reason = graph_explanations.get(str(item["id"]), "")
        if not reason:
            reason = item.get("frontier_desc", "")

        star_poster = item.get("poster") or craft_data.get("poster") or ""
        if not star_poster or not star_poster.startswith("http"):
            k_clean = _normalize_name(item.get("title") or "")
            for land in CURATED_LANDMARKS:
                if _normalize_name(land.get("title", "")) == k_clean and land.get("poster"):
                    star_poster = land["poster"]
                    break

        resolved_director = resolve_star_director(item.get("director"), craft_data.get("director"))
        resolved_creator = str(item.get("creator") or craft_data.get("creator") or "").strip()
        if not is_valid_craft_name(resolved_creator):
            resolved_creator = ""

        star_obj = {
            "id": item["id"],
            "title": item["title"],
            "year": item["year"],
            "director": resolved_director,
            "creator": resolved_creator,
            "genre": item["genre"],
            "poster": star_poster,
            "rating": item["rating"],
            "category": item["category"],
            "tv_show": item["tv_show"],
            "season": item.get("season"),
            "tmdb_id": item.get("tmdb_id"),
            "cinema": item["cinema"],
            "rewatch": item["rewatch"],
            "is_watched": item["is_watched"],
            "is_watchlist": item["is_watchlist"],
            "is_anchor": bool(item.get("is_watched") and (item.get("rating", 0) >= 4.5)),
            "is_void": bool(item.get("category") == "void_repulsor" or (item.get("is_watched") and item.get("rating", 0) <= 2)),
            "source": item["source"],
            "frontier_type": item.get("frontier_type", "resonator"),
            "frontier_desc": item.get("frontier_desc", ""),
            "canon_tier": item.get("canon_tier", ""),
            "x": round(float(scaled_x[idx]), 1),
            "y": round(float(scaled_y[idx]), 1),
            "target_x": round(float(target_x[idx]), 1),
            "target_y": round(float(target_y[idx]), 1),
            "affinity_score": round(float(affinity_scores[idx]), 3),
            "match_score": int(match_scores[idx]),
            "calibrated_prob": round(float(calibrated_probs[idx]), 3),
            "match_pct": int(match_scores[idx]),
            "calibration_meta": calibration_meta,
            "quality_score": quality_diagnostics[idx].get("bayesian_quality") if idx < len(quality_diagnostics) else None,
            "quality_delta": quality_diagnostics[idx].get("delta", 0.0) if idx < len(quality_diagnostics) else 0.0,
            "quality_diagnostics": quality_diagnostics[idx] if idx < len(quality_diagnostics) else {},
            "neg_risk": round(float(neg_risks[idx]), 3) if idx < len(neg_risks) else 0.0,
            "veto_factor": round(float(veto_factors[idx]), 3) if idx < len(veto_factors) else 1.0,
            "is_vetoed": bool(veto_diagnostics[idx].get("is_vetoed", False)) if idx < len(veto_diagnostics) else False,
            "negative_diagnostics": veto_diagnostics[idx] if idx < len(veto_diagnostics) else {},
            "positive_mode_id": int(dominant_pos_modes[idx]) if idx < len(dominant_pos_modes) else -1,
            "positive_mode_label": positive_modes[dominant_pos_modes[idx]].label if (idx < len(dominant_pos_modes) and 0 <= dominant_pos_modes[idx] < len(positive_modes)) else "",
            "confidence": fusion_diagnostics[idx]["confidence"] if idx < len(fusion_diagnostics) else {},
            "effective_weights": fusion_diagnostics[idx]["effective_weights"] if idx < len(fusion_diagnostics) else {},
            "agreement_score": fusion_diagnostics[idx]["agreement_score"] if idx < len(fusion_diagnostics) else 1.0,
            "is_exploratory": fusion_diagnostics[idx]["is_exploratory"] if idx < len(fusion_diagnostics) else False,
            "low_evidence": fusion_diagnostics[idx]["low_evidence"] if idx < len(fusion_diagnostics) else False,
            "sector_id": sec_info["id"],
            "sector_code": sec_info["code"],
            "sector_name": sec_info["name"],
            "sector_color": sec_info["color"],
            "micro_id": mc_info.get("id", ""),
            "micro_code": mc_info.get("code", ""),
            "micro_name": mc_info.get("name", ""),
            "micro_color": mc_info.get("color", sec_info["color"]),
            "micro_subtitle": mc_info.get("subtitle", ""),
            "craft": {
                "director": resolved_director,
                "creator": resolved_creator,
                "cinematographer": craft_data.get("cinematographer", ""),
                "composer": craft_data.get("composer", ""),
                "screenwriter": craft_data.get("screenwriter", ""),
                "lead_actors": craft_data.get("lead_actors", ""),
                "studios": craft_data.get("studios", "")
            },
            "affinity_reason": reason,
            "raw_vector_idx": idx
        }
        stars.append(star_obj)

    # 10. Generate Rich Force-Directed Graph Edges with Franchise, Auteur, and Craft Taxonomy
    links: List[Dict[str, Any]] = []
    seen_link_pairs = set()

    def add_link(id1, id2, str_val, l_type, l_reason):
        if id1 == id2:
            return
        pair = tuple(sorted([id1, id2]))
        if pair in seen_link_pairs:
            return
        seen_link_pairs.add(pair)
        links.append({
            "source": id1,
            "target": id2,
            "strength": round(float(str_val), 2),
            "link_type": l_type,
            "reason": l_reason
        })

    # --- Phase A1: TV Series Canon Linker (Same Show, Different Seasons) ---
    def extract_series_base_title(title_str: str) -> Optional[str]:
        t = str(title_str).strip()
        pattern = r'[\s,:\-_]+(?:Season|Series|Stagione|The Final Season|Limited Series)\b.*$'
        cleaned = re.sub(pattern, '', t, flags=re.IGNORECASE).strip()
        if cleaned and len(cleaned) >= 2 and cleaned.lower() != t.lower():
            return cleaned.lower()
        return None

    series_map = {}
    for idx, s in enumerate(stars):
        s_key = extract_series_base_title(s["title"])
        if s_key:
            series_map.setdefault(s_key, []).append(idx)

    for s_key, s_indices in series_map.items():
        if len(s_indices) >= 2:
            raw_title = stars[s_indices[0]]["title"]
            pattern = r'[\s,:\-_]+(?:Season|Series|Stagione|The Final Season|Limited Series)\b.*$'
            real_series_name = re.sub(pattern, '', raw_title, flags=re.IGNORECASE).strip()
            for mi in range(len(s_indices)):
                for mj in range(mi + 1, len(s_indices)):
                    idx_a = s_indices[mi]
                    idx_b = s_indices[mj]
                    add_link(
                        stars[idx_a]["id"], stars[idx_b]["id"], 1.0, "franchise",
                        f"TV Series Canon: {real_series_name}"
                    )

    # --- Phase A2: Explicit Franchise, Anime Canon & Saga Universe Linker ---
    FRANCHISE_CANON_PATTERNS = [
        ("The Twilight Saga", r'^(?:the\s+)?twilight(?:\s+saga|\s*:\s*new\s+moon|\s*:\s*eclipse|\s*:\s*breaking\s+dawn|\s*\(\d{4}\)|\s*$|\s+part)'),
        ("The Twilight Zone", r'^(?:the\s+)?twilight\s+zone\b'),
        ("Twilight of the Gods", r'^twilight\s+of\s+the\s+gods\b'),
        ("Saw", r'^saw(?:\s+[ivx\d]+|\s*:\s*|\s*$)'),
        ("Scream", r'^scream(?:\s+[ivx\d]+|\s*:\s*|\s*$)'),
        ("Alien", r'^(?:the\s+)?alien(?:\s+[ivx\d]+|\s*:\s*covenant|\s*:\s*resurrection|\s*:\s*romulus|\s*:\s*director|\s*3|\s*$)'),
        ("The Matrix", r'^(?:the\s+)?matrix(?:\s+reloaded|\s+revolutions|\s+resurrections|\s*:\s*|\s*$)'),
        ("Blade Runner", r'^blade\s+runner\b'),
        ("Star Wars", r'^star\s+wars\b'),
        ("Star Trek", r'^star\s+trek\b'),
        ("Lord of the Rings", r'^(?:the\s+)?lord\s+of\s+the\s+rings\b'),
        ("Harry Potter", r'^harry\s+potter\b|^fantastic\s+beasts\b'),
        ("Mission: Impossible", r'^mission(?:\s*:\s*|\s+)impossible\b'),
        ("John Wick", r'^john\s+wick\b'),
        ("Indiana Jones", r'^indiana\s+jones\b'),
        ("Jurassic Park", r'^jurassic\s+(?:park|world)\b'),
        ("The Godfather", r'^(?:the\s+)?godfather\b'),
        ("Planet of the Apes", r'^(?:the\s+)?(?:planet\s+of\s+the\s+apes|kingdom\s+of\s+the\s+planet\s+of\s+the\s+apes|war\s+for\s+the\s+planet\s+of\s+the\s+apes|dawn\s+of\s+the\s+planet\s+of\s+the\s+apes|rise\s+of\s+the\s+planet\s+of\s+the\s+apes)\b'),
        ("Mad Max", r'^mad\s+max\b|^furiosa\b'),
        ("Fast & Furious", r'^(?:the\s+)?fast\s+(?:&|and)\s+(?:the\s+)?furious\b|^2\s+fast\s+2\s+furious\b|^fast\s+(?:five|[ivx\d]+)\b|^f9\b|^fast\s+x\b|^hobbs\s+&\s+shaw\b'),
        ("Guardians of the Galaxy", r'^guardians\s+of\s+the\s+galaxy\b'),
        ("Spider-Man", r'^spider-?man\b'),
        ("Batman", r'^(?:the\s+)?batman\b|^the\s+dark\s+knight\b'),
        ("Top Gun", r'^top\s+gun\b'),
        ("Avatar", r'^avatar(?:\s*:\s*the\s+way\s+of\s+water|\s*:\s*fire\s+and\s+ash|\s*\(\d{4}\)|\s*$)'),
        ("Dune", r'^dune(?:\s*:\s*part|\s*\(\d{4}\)|\s*$)'),
        ("Hunger Games", r'^(?:the\s+)?hunger\s+games\b'),
        ("Pirates of the Caribbean", r'^pirates\s+of\s+the\s+caribbean\b'),
        ("Bourne", r'^(?:the\s+)?bourne\b'),
        ("Die Hard", r'^die\s+hard\b'),
        ("Terminator", r'^(?:the\s+)?terminator\b'),
        ("Ghost in the Shell", r'^ghost\s+in\s+the\s+shell\b|^koukaku\s+kidoutai\b'),
        ("Attack on Titan", r'^attack\s+on\s+titan\b|^shingeki\s+no\s+kyojin\b'),
        ("Fullmetal Alchemist", r'^fullmetal\s+alchemist\b'),
        ("Jujutsu Kaisen", r'^jujutsu\s+kaisen\b'),
        ("Demon Slayer", r'^demon\s+slayer\b|^kimetsu\s+no\s+yaiba\b'),
        ("Vinland Saga", r'^vinland\s+saga\b'),
        ("Evangelion", r'^neon\s+genesis\s+evangelion\b|^evangelion(?:\s*:\s*|\s+[0-9]|\s*$)'),
        ("Dragon Ball", r'^dragon\s+ball\b'),
        ("Cowboy Bebop", r'^cowboy\s+bebop\b'),
        ("Code Geass", r'^code\s+geass\b'),
        ("Death Note", r'^death\s+note\b'),
        ("One Piece", r'^one\s+piece\b'),
        ("Naruto", r'^naruto\b|^boruto\b'),
        ("Hunter x Hunter", r'^hunter\s*(?:x|×)\s*hunter\b'),
        ("Berserk", r'^berserk\b'),
        ("Mob Psycho 100", r'^mob\s+psycho\s*100\b'),
        ("Steins;Gate", r'^steins;?gate\b'),
        ("Chainsaw Man", r'^chainsaw\s+man\b'),
        ("Bleach", r'^bleach(?:\s*:\s*thousand|\s*\(\d{4}\)|\s*$)'),
        ("JoJo\'s Bizarre Adventure", r'^(?:le\s+bizzarre\s+avventure\s+di\s+)?jojo(?:\'s\s+bizarre\s+adventure|\s*$)'),
        ("Super Mario", r'^(?:the\s+)?super\s+mario\b'),
        ("How to Train Your Dragon", r'^how\s+to\s+train\s+your\s+dragon\b'),
        ("Kung Fu Panda", r'^kung\s+fu\s+panda\b'),
        ("Toy Story", r'^toy\s+story\b'),
        ("Despicable Me / Minions", r'^despicable\s+me\b|^minions\b'),
        ("The Incredibles", r'^(?:the\s+)?incredibles\b'),
        ("Knives Out", r'^knives\s+out\b|^glass\s+onion\b'),
        ("A Quiet Place", r'^a\s+quiet\s+place\b'),
        ("The Conjuring Universe", r'^(?:the\s+)?conjuring\b|^annabelle\b|^the\s+nun\b'),
        ("Insidious", r'^insidious\b'),
        ("Halloween", r'^halloween(?:\s+[ivx\d]+|\s+kills|\s+ends|\s*:\s*|\s*$)'),
        ("Evil Dead", r'^(?:the\s+)?evil\s+dead\b|^army\s+of\s+darkness\b'),
        ("Rocky / Creed", r'^rocky(?:\s+[ivx\d]+|\s+balboa|\s*$)|^creed(?:\s+[ivx\d]+|\s*$)'),
        ("Kingsman", r'^kingsman\b'),
        ("Sherlock Holmes", r'^sherlock\s+holmes\b'),
        ("Zootopia", r'^zootopia\b|^zootropolis\b'),
    ]

    def extract_franchise_key(title_str: str) -> Optional[str]:
        t = str(title_str).lower().strip()
        # 1. Match explicit curated patterns with word boundary anchoring
        for f_name, pattern in FRANCHISE_CANON_PATTERNS:
            if re.search(pattern, t, flags=re.IGNORECASE):
                return f_name

        # 2. Dynamic Delimiter Prefix Matching (e.g. "Title: Subtitle" or "Title - Subtitle")
        for delim in [":", " - ", " – "]:
            if delim in t:
                raw_prefix = title_str.split(delim)[0].strip()
                norm_p = re.sub(r'^(?:the|a|an)\s+', '', raw_prefix, flags=re.IGNORECASE).strip()
                if len(norm_p) >= 4 and not norm_p.isdigit():
                    return raw_prefix

        return None

    franchise_map = {}
    for idx, s in enumerate(stars):
        fkey = extract_franchise_key(s["title"])
        if fkey:
            franchise_map.setdefault(fkey, []).append(idx)

    for fkey, member_indices in franchise_map.items():
        if len(member_indices) >= 2:
            for mi in range(len(member_indices)):
                for mj in range(mi + 1, len(member_indices)):
                    idx_a = member_indices[mi]
                    idx_b = member_indices[mj]
                    s_a = stars[idx_a]
                    s_b = stars[idx_b]
                    add_link(
                        s_a["id"], s_b["id"], 1.0, "franchise",
                        f"Franchise Canon: {fkey}"
                    )

    # --- Phase B: Auteur & Director Constellations ---
    director_star_map = {}
    for idx, s in enumerate(stars):
        d = str(s.get("director", "")).strip()
        if is_valid_craft_name(d):
            director_star_map.setdefault(d.lower(), []).append(idx)

    for d_name, d_indices in director_star_map.items():
        if len(d_indices) >= 2:
            real_d_name = stars[d_indices[0]]["director"]
            for mi in range(len(d_indices)):
                for mj in range(mi + 1, min(len(d_indices), mi + 4)):
                    idx_a = d_indices[mi]
                    idx_b = d_indices[mj]
                    add_link(
                        stars[idx_a]["id"], stars[idx_b]["id"], 0.85, "director",
                        f"Directorial Lineage: {real_d_name}"
                    )

    # --- Phase C: Cinematography & Original Score Craft Bonds ---
    dop_map = {}
    comp_map = {}
    for idx, s in enumerate(stars):
        dop = s.get("craft", {}).get("cinematographer")
        if is_valid_craft_name(dop):
            dop_map.setdefault(str(dop).strip().lower(), []).append(idx)
        comp = s.get("craft", {}).get("composer")
        if is_valid_craft_name(comp):
            comp_map.setdefault(str(comp).strip().lower(), []).append(idx)

    for dop_name, d_indices in dop_map.items():
        if len(d_indices) >= 2:
            real_dop = stars[d_indices[0]]["craft"]["cinematographer"]
            for mi in range(len(d_indices)):
                for mj in range(mi + 1, min(len(d_indices), mi + 3)):
                    add_link(
                        stars[d_indices[mi]]["id"], stars[d_indices[mj]]["id"], 0.75, "cinematography",
                        f"Cinematography: {real_dop}"
                    )

    for comp_name, c_indices in comp_map.items():
        if len(c_indices) >= 2:
            real_comp = stars[c_indices[0]]["craft"]["composer"]
            for mi in range(len(c_indices)):
                for mj in range(mi + 1, min(len(c_indices), mi + 3)):
                    add_link(
                        stars[c_indices[mi]]["id"], stars[c_indices[mj]]["id"], 0.70, "composer",
                        f"Original Score: {real_comp}"
                    )

    # Calculate Node Degree & Hub Flag for Degree Centrality Scaling (Craft & Lineage Keystones)
    from collections import Counter
    degree_counts = Counter()
    for l in links:
        degree_counts[l["source"]] += 1
        degree_counts[l["target"]] += 1

    for s in stars:
        deg = degree_counts[s["id"]]
        s["degree"] = deg
        s["is_hub"] = deg >= 3

    # Strictly pick Top 5 highest-affinity 5★ landmark keystones across the galaxy as anchors
    anchor_candidates = [s for s in stars if s.get("is_watched") and (s.get("rating") or 0) >= 5.0]
    top_anchor_ids = set(s["id"] for s in sorted(anchor_candidates, key=lambda x: (x.get("degree", 0), x.get("match_pct", 0)), reverse=True)[:5])

    for s in stars:
        s["is_anchor"] = s["id"] in top_anchor_ids

    links = links[:1200]  # Rich, expansive organic network

    # Stats for telemetry HUD
    watched_count = sum(1 for s in stars if s["is_watched"])
    uncharted_count = sum(1 for s in stars if not s["is_watched"])
    watchlist_count = sum(1 for s in stars if s["is_watchlist"])

    payload = {
        "success": True,
        "timestamp": now,
        "stars": stars,
        "links": links,
        "sectors": sectors,
        "stats": {
            "watched_stars": watched_count,
            "uncharted_beacons": uncharted_count,
            "watchlist_stars": watchlist_count,
            "total_celestial_bodies": len(stars),
            "active_sectors": len(sectors),
            "negative_modes_count": len(negative_modes),
            "positive_modes_count": len(positive_modes),
            "positive_modes": [
                {
                    "id": m.mode_id,
                    "label": m.label,
                    "weight": round(float(m.weight), 3),
                    "size": m.size,
                    "cohesion": round(float(m.cohesion), 3),
                    "genres": m.dominant_genres,
                    "directors": m.dominant_directors
                }
                for m in positive_modes
            ],
            "vetoed_stars_count": sum(1 for s in stars if s.get("is_vetoed")),
            "calibration": calibration_meta,
            "quality_prior": quality_meta
        }
    }

    # Store in cache only if valid (avoid caching 0-watched if user has movies in DB)
    watched_in_payload = sum(1 for s in stars if s.get("is_watched"))
    if watched_in_payload > 0 or not user_raw_movies:
        _GALAXY_CACHE[user_id] = (now, payload)
    return payload


def get_probe_recommendations(target_x: float, target_y: float, user_id: int, limit: int = 6) -> Dict[str, Any]:
    """
    Returns the nearest unwatched candidate stars to a cosmic probe dropped at (target_x, target_y).
    Excludes vetoed stars so probe recommendations only surface non-aversion films.
    """
    galaxy_data = build_taste_cosmos_data(user_id)
    stars = galaxy_data.get("stars", [])
    
    unwatched = [s for s in stars if not s.get("is_watched")]
    # Exclude vetoed items from probe recommendations
    unwatched_clean = [s for s in unwatched if not s.get("is_vetoed") and s.get("veto_factor", 1.0) >= 0.50]
    if unwatched_clean:
        unwatched = unwatched_clean
    elif not unwatched:
        unwatched = stars

    # Rank by distance to probe
    ranked = sorted(unwatched, key=lambda s: math.hypot(s["x"] - target_x, s["y"] - target_y))
    
    return {
        "success": True,
        "probe_x": target_x,
        "probe_y": target_y,
        "recommendations": ranked[:limit]
    }
