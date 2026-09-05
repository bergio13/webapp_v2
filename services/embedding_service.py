import os
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import sqlite3
import hashlib
import struct
import logging
from typing import List, Dict, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Cache database path
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance")
os.makedirs(DB_DIR, exist_ok=True)
CACHE_DB_PATH = os.path.join(DB_DIR, "embeddings_cache.db")

_EMBED_MODEL = None


def _get_embedding_model():
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        try:
            from fastembed import TextEmbedding
            # BAAI/bge-small-en-v1.5 is 67MB, high-speed ONNX, 384 dimensions
            _EMBED_MODEL = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            logger.info("FastEmbed TextEmbedding model initialized successfully (BAAI/bge-small-en-v1.5)")
        except Exception as e:
            logger.warning(f"Could not load FastEmbed TextEmbedding: {e}")
            _EMBED_MODEL = False
    return _EMBED_MODEL if _EMBED_MODEL is not False else None


def _init_cache_db():
    try:
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    item_key TEXT PRIMARY KEY,
                    text_hash TEXT,
                    vec_blob BLOB,
                    dim INTEGER,
                    created_at REAL DEFAULT (strftime('%s', 'now'))
                )
            """)
            conn.commit()
    except Exception as e:
        logger.error(f"Error initializing embeddings SQLite cache: {e}")


# Initialize table on import
_init_cache_db()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _vec_to_blob(vec: np.ndarray) -> bytes:
    vec_f32 = np.asarray(vec, dtype=np.float32)
    return vec_f32.tobytes()


def _blob_to_vec(blob: bytes, dim: int = 384) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


_EMBEDDING_CACHE: Dict[str, np.ndarray] = {}


def get_cached_embedding(item_key: str, text_hash: str) -> Optional[np.ndarray]:
    cache_k = f"{item_key}_{text_hash}"
    if cache_k in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[cache_k]
    try:
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT vec_blob, dim FROM embeddings WHERE item_key = ? AND text_hash = ?",
                (item_key, text_hash)
            )
            row = cursor.fetchone()
            if row:
                blob, dim = row
                vec = _blob_to_vec(blob, dim)
                _EMBEDDING_CACHE[cache_k] = vec
                return vec
    except Exception as e:
        logger.debug(f"Cache lookup error for {item_key}: {e}")
    return None


def get_cached_embeddings_batch(items_meta: List[Dict[str, str]]) -> Dict[str, np.ndarray]:
    """
    Bulk retrieves embeddings from in-memory cache and SQLite (<2ms).
    items_meta: list of dicts with {"key": str, "text_hash": str}
    Returns dict mapping item_key to 384D float32 vector.
    """
    results: Dict[str, np.ndarray] = {}
    missing_in_mem: List[Dict[str, str]] = []

    for it in items_meta:
        k = it["key"]
        th = it["text_hash"]
        cache_k = f"{k}_{th}"
        if cache_k in _EMBEDDING_CACHE:
            results[k] = _EMBEDDING_CACHE[cache_k]
        else:
            missing_in_mem.append(it)

    if not missing_in_mem:
        return results

    try:
        keys = list({it["key"] for it in missing_in_mem})
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            cursor = conn.cursor()
            chunk_size = 500
            for i in range(0, len(keys), chunk_size):
                chunk = keys[i:i + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                cursor.execute(
                    f"SELECT item_key, text_hash, vec_blob, dim FROM embeddings WHERE item_key IN ({placeholders})",
                    chunk
                )
                for row in cursor.fetchall():
                    item_key, text_hash, blob, dim = row
                    vec = _blob_to_vec(blob, dim)
                    cache_k = f"{item_key}_{text_hash}"
                    _EMBEDDING_CACHE[cache_k] = vec
                    results[item_key] = vec
    except Exception as e:
        logger.debug(f"Bulk embedding cache lookup error: {e}")

    return results


def store_cached_embeddings(items: List[Dict[str, Any]]):
    """
    items: list of dicts with {"key": str, "text_hash": str, "vec": np.ndarray}
    """
    if not items:
        return
    for it in items:
        cache_k = f"{it['key']}_{it['text_hash']}"
        _EMBEDDING_CACHE[cache_k] = np.asarray(it["vec"], dtype=np.float32)

    try:
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT OR REPLACE INTO embeddings (item_key, text_hash, vec_blob, dim)
                VALUES (?, ?, ?, ?)
                """,
                [(it["key"], it["text_hash"], _vec_to_blob(it["vec"]), len(it["vec"])) for it in items]
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to save embeddings to cache: {e}")


def construct_semantic_text(movie: Dict[str, Any]) -> str:
    """
    Synthesizes a rich descriptive text for semantic embedding:
    Includes title, year, director, genres, tags, overview, and cast if available.
    """
    title = movie.get("title") or movie.get("movie") or "Untitled"
    year = str(movie.get("p_year") or movie.get("year") or "")
    director = movie.get("director") or "Unknown"
    genre = movie.get("genre") or "Cinema"
    tags = movie.get("tags") or ""
    overview = movie.get("overview") or ""

    parts = [f"Title: {title} ({year}).", f"Director: {director}.", f"Genres: {genre}."]
    if tags:
        parts.append(f"Keywords: {tags}.")
    if overview:
        parts.append(f"Overview: {overview}")
    
    return " ".join(parts)


def compute_semantic_embeddings(movies: List[Dict[str, Any]]) -> np.ndarray:
    """
    Computes dense 384-dimensional semantic embeddings for a list of movies.
    Leverages in-memory + SQLite batch cache so previously seen movies are retrieved instantly (< 2ms).
    Uncached movies are embedded in a single batch via FastEmbed ONNX.
    """
    if not movies:
        return np.zeros((0, 384), dtype=np.float32)

    embeddings = [None] * len(movies)
    items_meta = []
    
    for idx, m in enumerate(movies):
        title = m.get("title") or m.get("movie") or "Untitled"
        year = str(m.get("p_year") or m.get("year") or "")
        clean_title = "".join(c for c in title.lower() if c.isalnum())
        item_key = f"{clean_title}_{year}"
        
        text = construct_semantic_text(m)
        t_hash = _hash_text(text)
        items_meta.append({"idx": idx, "key": item_key, "text_hash": t_hash, "text": text})

    # Bulk lookup
    cached_map = get_cached_embeddings_batch([{"key": it["key"], "text_hash": it["text_hash"]} for it in items_meta])

    to_embed_indices = []
    to_embed_texts = []
    to_embed_meta = []

    for it in items_meta:
        idx = it["idx"]
        k = it["key"]
        if k in cached_map:
            embeddings[idx] = cached_map[k]
        else:
            to_embed_indices.append(idx)
            to_embed_texts.append(it["text"])
            to_embed_meta.append({"key": it["key"], "text_hash": it["text_hash"]})

    # 2. Batch embed missing items if any
    if to_embed_indices:
        model = _get_embedding_model()
        if model is not None:
            try:
                batch_results = list(model.embed(to_embed_texts))
                cache_items_to_save = []

                for i, vec in enumerate(batch_results):
                    orig_idx = to_embed_indices[i]
                    vec_norm = vec / (np.linalg.norm(vec) + 1e-9)
                    vec_norm_f32 = vec_norm.astype(np.float32)
                    embeddings[orig_idx] = vec_norm_f32
                    
                    cache_items_to_save.append({
                        "key": to_embed_meta[i]["key"],
                        "text_hash": to_embed_meta[i]["text_hash"],
                        "vec": vec_norm_f32
                    })

                store_cached_embeddings(cache_items_to_save)
            except Exception as e:
                logger.error(f"Error during FastEmbed batch generation: {e}")
                for i, orig_idx in enumerate(to_embed_indices):
                    embeddings[orig_idx] = _fallback_pseudo_embedding(to_embed_texts[i])
        else:
            for i, orig_idx in enumerate(to_embed_indices):
                embeddings[orig_idx] = _fallback_pseudo_embedding(to_embed_texts[i])

    return np.array(embeddings, dtype=np.float32)


_TEXT_EMB_CACHE: Dict[str, np.ndarray] = {}


def compute_text_embeddings(texts: List[str]) -> np.ndarray:
    """
    Computes dense 384-dimensional normalized semantic embeddings for a list of text strings with in-memory caching.
    """
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)

    results = [None] * len(texts)
    missing_indices = []
    missing_texts = []

    for i, t in enumerate(texts):
        th = _hash_text(t)
        if th in _TEXT_EMB_CACHE:
            results[i] = _TEXT_EMB_CACHE[th]
        else:
            missing_indices.append(i)
            missing_texts.append(t)

    if missing_texts:
        model = _get_embedding_model()
        if model is not None:
            try:
                batch_res = list(model.embed(missing_texts))
                for j, vec in enumerate(batch_res):
                    orig_idx = missing_indices[j]
                    v_norm = (vec / (np.linalg.norm(vec) + 1e-9)).astype(np.float32)
                    th = _hash_text(missing_texts[j])
                    _TEXT_EMB_CACHE[th] = v_norm
                    results[orig_idx] = v_norm
            except Exception as e:
                logger.error(f"Error embedding text list: {e}")
                for j, orig_idx in enumerate(missing_indices):
                    results[orig_idx] = _fallback_pseudo_embedding(missing_texts[j])
        else:
            for j, orig_idx in enumerate(missing_indices):
                results[orig_idx] = _fallback_pseudo_embedding(missing_texts[j])

    return np.array(results, dtype=np.float32)


def movie_year(m: Dict[str, Any]) -> str:
    return str(m.get("year") or m.get("p_year") or "")


def _fallback_pseudo_embedding(text: str) -> np.ndarray:
    """
    Deterministic fallback embedding generator when ONNX runtime is unavailable.
    """
    rng = np.random.RandomState(int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16))
    vec = rng.randn(384).astype(np.float32)
    return vec / (np.linalg.norm(vec) + 1e-9)
