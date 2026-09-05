"""
services/graph_service.py — Heterogeneous Cinephile Knowledge Graph & LightGCN Engine
Constructs a craft-aware knowledge graph connecting User, Movies, Directors, Cinematographers (DoP),
Composers, Screenwriters, Actors, and Studios, running multi-hop LightGCN graph convolutions
and generating transparent craft reasoning paths.
"""

import math
import logging
from typing import Dict, List, Any, Tuple, Optional
import numpy as np
import scipy.sparse as sp

logger = logging.getLogger(__name__)


def _normalize_name(name: str) -> str:
    return "".join(c for c in str(name).lower() if c.isalnum())


class CinephileKnowledgeGraph:
    def __init__(self):
        self.node_to_idx: Dict[str, int] = {}
        self.idx_to_node: Dict[int, Tuple[str, str]] = {}  # idx -> (type, raw_name)
        self.edges: List[Tuple[int, int, float]] = []

    def get_or_create_node(self, node_type: str, raw_name: str) -> int:
        norm = _normalize_name(raw_name)
        key = f"{node_type}:{norm}"
        if key not in self.node_to_idx:
            idx = len(self.node_to_idx)
            self.node_to_idx[key] = idx
            self.idx_to_node[idx] = (node_type, raw_name)
        return self.node_to_idx[key]

    def add_edge(self, u: int, v: int, weight: float = 1.0):
        self.edges.append((u, v, weight))
        self.edges.append((v, u, weight))


def build_and_run_lightgcn(
    movies: List[Dict[str, Any]],
    crafts_by_key: Dict[str, Dict[str, Any]],
    user_id: int = 15,
    embedding_dim: int = 64,
    n_layers: int = 3,
    return_stats: bool = False
) -> Any:
    """
    Builds the heterogeneous knowledge graph, executes 3-layer LightGCN convolution,
    and returns:
      1. movie_graph_embeddings: (N, embedding_dim)
      2. graph_scores: list of graph affinity match percentages
      3. graph_explanations: mapping from movie_id -> craft explanation string
      4. (optional if return_stats=True) graph_node_stats: mapping movie_id -> node topology stats
    """
    n_movies = len(movies)
    if n_movies == 0:
        if return_stats:
            return np.zeros((0, embedding_dim)), [], {}, {}
        return np.zeros((0, embedding_dim)), [], {}

    kg = CinephileKnowledgeGraph()

    # 1. User Node
    user_idx = kg.get_or_create_node("user", f"user_{user_id}")

    # Index movie nodes
    movie_node_indices = []
    for idx, m in enumerate(movies):
        m_id = str(m.get("id"))
        m_idx = kg.get_or_create_node("movie", f"movie_{m_id}")
        movie_node_indices.append(m_idx)

    # 2. Build Graph Edges
    useful_edges_per_movie = [0] * n_movies
    for idx, m in enumerate(movies):
        m_idx = movie_node_indices[idx]
        title = m.get("title") or m.get("movie") or ""
        year = m.get("p_year") or m.get("year")
        from services.craft_service import _normalize_key
        key = _normalize_key(title, year)
        craft = crafts_by_key.get(key, {})

        # User -> Movie Rating Edge
        if m.get("is_watched"):
            rating = float(m.get("rating", 0))
            if rating >= 5.0:
                kg.add_edge(user_idx, m_idx, 1.5)
                useful_edges_per_movie[idx] += 1
            elif rating >= 4.0:
                kg.add_edge(user_idx, m_idx, 1.0)
                useful_edges_per_movie[idx] += 1
            elif rating <= 2.0:
                kg.add_edge(user_idx, m_idx, -1.2)  # Negative gravity repulsion
                useful_edges_per_movie[idx] += 1
        elif m.get("is_watchlist"):
            kg.add_edge(user_idx, m_idx, 0.8)
            useful_edges_per_movie[idx] += 1

        # Movie -> Director
        director = craft.get("director") or m.get("director")
        if director and director.lower() not in ["unknown", "n/a", ""]:
            for d in [x.strip() for x in director.split(",") if x.strip()]:
                d_idx = kg.get_or_create_node("director", d)
                kg.add_edge(m_idx, d_idx, 1.2)
                useful_edges_per_movie[idx] += 1

        # Movie -> Cinematographer (DoP)
        dop = craft.get("cinematographer")
        if dop:
            for d in [x.strip() for x in dop.split(",") if x.strip()]:
                dop_idx = kg.get_or_create_node("cinematographer", d)
                kg.add_edge(m_idx, dop_idx, 1.1)
                useful_edges_per_movie[idx] += 1

        # Movie -> Composer
        composer = craft.get("composer")
        if composer:
            for c in [x.strip() for x in composer.split(",") if x.strip()]:
                comp_idx = kg.get_or_create_node("composer", c)
                kg.add_edge(m_idx, comp_idx, 0.95)
                useful_edges_per_movie[idx] += 1

        # Movie -> Screenwriter
        writer = craft.get("screenwriter")
        if writer:
            for w in [x.strip() for x in writer.split(",") if x.strip()]:
                w_idx = kg.get_or_create_node("screenwriter", w)
                kg.add_edge(m_idx, w_idx, 0.9)
                useful_edges_per_movie[idx] += 1

        # Movie -> Lead Actors
        actors = craft.get("lead_actors")
        if actors:
            for a in [x.strip() for x in actors.split(",") if x.strip()][:3]:
                act_idx = kg.get_or_create_node("actor", a)
                kg.add_edge(m_idx, act_idx, 0.65)
                useful_edges_per_movie[idx] += 1

        # Movie -> Studios
        studios = craft.get("studios")
        if studios:
            for s in [x.strip() for x in studios.split(",") if x.strip()][:2]:
                s_idx = kg.get_or_create_node("studio", s)
                kg.add_edge(m_idx, s_idx, 0.5)
                useful_edges_per_movie[idx] += 1

        # Movie -> Genre
        genres = m.get("genre", "")
        if genres:
            for g in [x.strip() for x in str(genres).split(",") if x.strip()]:
                g_idx = kg.get_or_create_node("genre", g)
                kg.add_edge(m_idx, g_idx, 0.4)

    # 3. LightGCN Sparse Graph Convolution
    total_nodes = len(kg.node_to_idx)
    rows = [e[0] for e in kg.edges]
    cols = [e[1] for e in kg.edges]
    weights = [e[2] for e in kg.edges]

    adj = sp.csr_matrix((weights, (rows, cols)), shape=(total_nodes, total_nodes), dtype=np.float32)

    # Symmetric Degree Normalization D^-1/2 * A * D^-1/2
    abs_adj = sp.csr_matrix((np.abs(weights), (rows, cols)), shape=(total_nodes, total_nodes), dtype=np.float32)
    degrees = np.array(abs_adj.sum(axis=1)).flatten()
    degrees[degrees < 1e-6] = 1e-6
    d_inv_sqrt = np.power(degrees, -0.5)
    d_mat = sp.diags(d_inv_sqrt)
    norm_adj = d_mat.dot(adj).dot(d_mat)

    # Deterministic Multi-Scale Node Embeddings & User Impulse Propagation
    E0 = np.zeros((total_nodes, embedding_dim), dtype=np.float32)
    # User node carries initial positive unit impulse
    E0[user_idx] = 1.0 / np.sqrt(embedding_dim)
    
    # Base positive identity initialization for all craft and movie nodes
    rng = np.random.RandomState(42)
    for i in range(total_nodes):
        if i != user_idx:
            # Deterministic projection vector
            E0[i] = rng.uniform(0.1, 0.5, size=embedding_dim).astype(np.float32)
            E0[i] /= (np.linalg.norm(E0[i]) + 1e-9)

    # Multi-hop Message Passing (LightGCN Convolution)
    all_embeddings = [E0]
    current_E = E0
    layer_weights = [0.4, 0.35, 0.25]

    for l in range(n_layers - 1):
        current_E = norm_adj.dot(current_E)
        all_embeddings.append(current_E)

    # Final Aggregated Multi-Hop Embeddings
    E_final = sum(w * e for w, e in zip(layer_weights[:len(all_embeddings)], all_embeddings))
    E_norm = E_final / (np.linalg.norm(E_final, axis=1, keepdims=True) + 1e-9)

    # Personalized PageRank Energy Diffusion directly from User node
    u_impulse = np.zeros(total_nodes, dtype=np.float32)
    u_impulse[user_idx] = 1.0
    p = u_impulse
    for _ in range(4):
        p = 0.75 * norm_adj.dot(p) + 0.25 * u_impulse

    # Extract User & Movie Embeddings
    movie_embs = E_norm[movie_node_indices]
    movie_ppr = p[movie_node_indices]

    # Combine cosine embedding similarity with direct graph diffusion energy
    user_emb = E_norm[user_idx]
    cosine_aff = np.dot(movie_embs, user_emb)
    graph_affinities = 0.5 * cosine_aff + 0.5 * (movie_ppr * 5.0)

    # 4. Generate Graph Reasoning Paths ("Why Recommended")
    graph_explanations = {}
    
    # Pre-index high-rated user favorites
    pos_movies = [m for m in movies if m.get("is_watched") and m.get("rating", 0) >= 4]
    
    for idx, m in enumerate(movies):
        m_id = str(m.get("id"))
        if m.get("is_watched"):
            continue

        title = m.get("title") or m.get("movie") or ""
        year = m.get("p_year") or m.get("year")
        from services.craft_service import _normalize_key
        key = _normalize_key(title, year)
        craft = crafts_by_key.get(key, {})

        c_dop = craft.get("cinematographer")
        c_comp = craft.get("composer")
        c_dir = craft.get("director") or m.get("director")
        c_writer = craft.get("screenwriter")
        c_studios = craft.get("studios")

        reasons = []

        # Check DoP connection
        if c_dop:
            dop_first = c_dop.split(",")[0].strip()
            favs_with_dop = [
                p.get("title") for p in pos_movies 
                if dop_first.lower() in crafts_by_key.get(_normalize_key(p.get("title"), p.get("p_year") or p.get("year")), {}).get("cinematographer", "").lower()
            ]
            if favs_with_dop:
                reasons.append(f"Cinematography by {dop_first} ({', '.join(favs_with_dop[:2])})")

        # Check Composer connection
        if c_comp and len(reasons) < 2:
            comp_first = c_comp.split(",")[0].strip()
            favs_with_comp = [
                p.get("title") for p in pos_movies 
                if comp_first.lower() in crafts_by_key.get(_normalize_key(p.get("title"), p.get("p_year") or p.get("year")), {}).get("composer", "").lower()
            ]
            if favs_with_comp:
                reasons.append(f"Score by {comp_first} ({', '.join(favs_with_comp[:2])})")

        # Check Director connection
        if c_dir and len(reasons) < 2:
            dir_first = c_dir.split(",")[0].strip()
            favs_with_dir = [
                p.get("title") for p in pos_movies 
                if dir_first.lower() in (p.get("director") or "").lower()
            ]
            if favs_with_dir:
                reasons.append(f"Directed by {dir_first} ({', '.join(favs_with_dir[:2])})")

        # Check Studio connection
        if c_studios and ("a24" in c_studios.lower() or "ghibli" in c_studios.lower() or "neon" in c_studios.lower()):
            studio_name = "A24" if "a24" in c_studios.lower() else ("Studio Ghibli" if "ghibli" in c_studios.lower() else "NEON")
            if len(reasons) < 2:
                reasons.append(f"Produced by {studio_name}")

        if reasons:
            graph_explanations[m_id] = " + ".join(reasons)
        else:
            # Fallback based on genre / mood synergy
            genre_name = m.get("genre", "Cinema").split(",")[0].strip()
            graph_explanations[m_id] = f"Aesthetic synergy with your {genre_name} favorites"

    # 5. Extract Topology & Connectivity Stats for Adaptive Graph Confidence
    graph_node_stats = {}
    for idx, m in enumerate(movies):
        m_id = str(m.get("id"))
        m_idx = movie_node_indices[idx]
        deg = int(degrees[m_idx])
        u_edges = useful_edges_per_movie[idx]

        # Check if connected to user favorites
        has_fav = False
        if m.get("is_watched") and float(m.get("rating", 0)) >= 4.0:
            has_fav = True
        elif m_id in graph_explanations and "favorites" not in graph_explanations[m_id].lower():
            # If an explicit craft reason connecting to a favorite was found
            has_fav = True
        else:
            # Check DoP / Composer / Director craft overlap with pos_movies
            title = m.get("title") or m.get("movie") or ""
            year = m.get("p_year") or m.get("year")
            from services.craft_service import _normalize_key
            craft = crafts_by_key.get(_normalize_key(title, year), {})
            c_dir = (craft.get("director") or m.get("director") or "").strip().lower()
            c_dop = (craft.get("cinematographer") or "").strip().lower()
            c_comp = (craft.get("composer") or "").strip().lower()
            for p in pos_movies:
                p_key = _normalize_key(p.get("title") or p.get("movie") or "", p.get("p_year") or p.get("year"))
                p_craft = crafts_by_key.get(p_key, {})
                if c_dir and c_dir in (p.get("director") or "").lower():
                    has_fav = True
                    break
                if c_dop and c_dop in (p_craft.get("cinematographer") or "").lower():
                    has_fav = True
                    break
                if c_comp and c_comp in (p_craft.get("composer") or "").lower():
                    has_fav = True
                    break

        graph_node_stats[m_id] = {
            "degree": deg,
            "useful_edges": u_edges,
            "has_fav_connection": has_fav,
            "has_diffusion": bool(movie_ppr[idx] > 1e-4)
        }

    if return_stats:
        return movie_embs, graph_affinities.tolist(), graph_explanations, graph_node_stats
    return movie_embs, graph_affinities.tolist(), graph_explanations
