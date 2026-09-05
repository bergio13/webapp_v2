"""services/catalog_service.py — Supabase Canonical Movie Catalog Service

Manages the canonical media catalog stored directly in Supabase (`public.movie_catalog`),
with an automatic high-speed local SQLite cache (`instance/movie_catalog.db`)
for sub-millisecond local reads during manifold synthesis and recommendations:
- Multi-genres, plot overview, thematic keywords/tags
- Full craft credits (Director, Cinematographer, Composer, Screenwriter, Editor, Lead Cast, Studios)
- Pre-computed 384D FastEmbed semantic embeddings
"""

import os
import re
import json
import math
import sqlite3
import logging
from typing import Dict, List, Any, Optional
import requests
import numpy as np
from dotenv import load_dotenv

load_dotenv()

from database import client as supabase_client

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance")
os.makedirs(DB_DIR, exist_ok=True)
CATALOG_DB_PATH = os.path.join(DB_DIR, "movie_catalog.db")
TMDB_BASE_URL = "https://api.themoviedb.org/3"

_IN_MEMORY_CATALOG: Dict[str, Dict[str, Any]] = {}


def _get_api_key() -> Optional[str]:
    return os.environ.get("TMDB_API_KEY")


def normalize_movie_key(title: str, year: Any = "") -> str:
    clean_title = re.sub(
        r',?\s*(?:season\s*\d+|series\s*\d+|volume\s*\d+|vol\s*\d+|s\d+|the final season|final season|limited series|miniseries)\b.*$', 
        '', 
        str(title or ""), 
        flags=re.IGNORECASE
    ).strip()
    clean_title = re.sub(r"[^a-z0-9]", "", clean_title.lower())
    clean_year = str(year or "").strip()[:4]
    return f"{clean_title}_{clean_year}"


def _blob_to_vec(blob: bytes) -> Optional[np.ndarray]:
    if not blob:
        return None
    return np.frombuffer(blob, dtype=np.float32)


def _vec_to_blob(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype=np.float32).tobytes()


def _safe_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ["none", "null", "n/a", ""]:
        return None
    digits = re.findall(r"\d+", s)
    if digits:
        try:
            return int(digits[0])
        except (ValueError, TypeError):
            return None
    return None


def _safe_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def init_local_cache():
    """Initializes the local SQLite replica cache."""
    try:
        with sqlite3.connect(CATALOG_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS movie_catalog (
                    movie_key TEXT PRIMARY KEY,
                    tmdb_id INTEGER,
                    imdb_id TEXT,
                    title TEXT NOT NULL,
                    year INTEGER,
                    is_tv INTEGER DEFAULT 0,
                    genres TEXT DEFAULT '',
                    overview TEXT DEFAULT '',
                    keywords TEXT DEFAULT '',
                    director TEXT DEFAULT '',
                    cinematographer TEXT DEFAULT '',
                    composer TEXT DEFAULT '',
                    screenwriter TEXT DEFAULT '',
                    editor TEXT DEFAULT '',
                    lead_actors TEXT DEFAULT '',
                    studios TEXT DEFAULT '',
                    poster TEXT DEFAULT '',
                    vote_average REAL DEFAULT 0.0,
                    vote_count INTEGER DEFAULT 0,
                    embedding_blob BLOB,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    updated_at REAL DEFAULT (strftime('%s', 'now'))
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cat_tmdb_id ON movie_catalog(tmdb_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cat_title_year ON movie_catalog(title, year)")

            # Canonical TV Season Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tv_season_catalog (
                    season_key TEXT PRIMARY KEY,
                    tmdb_id INTEGER NOT NULL,
                    season_number INTEGER NOT NULL,
                    show_title TEXT NOT NULL,
                    season_name TEXT DEFAULT '',
                    air_date TEXT DEFAULT '',
                    year INTEGER,
                    overview TEXT DEFAULT '',
                    poster TEXT DEFAULT '',
                    vote_average REAL DEFAULT 0.0,
                    episode_count INTEGER DEFAULT 0,
                    director TEXT DEFAULT '',
                    lead_actors TEXT DEFAULT '',
                    cinematographer TEXT DEFAULT '',
                    composer TEXT DEFAULT '',
                    screenwriter TEXT DEFAULT '',
                    embedding_blob BLOB,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    updated_at REAL DEFAULT (strftime('%s', 'now'))
                )
            """)
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tv_season_tmdb_season ON tv_season_catalog(tmdb_id, season_number)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tv_season_show_title ON tv_season_catalog(show_title)")
            conn.commit()
    except Exception as e:
        logger.error(f"Error initializing local movie_catalog SQLite cache: {e}")


_IN_MEMORY_SEASONS: Dict[str, Dict[str, Any]] = {}


init_local_cache()


def get_catalog_item(title: str, year: Any = None, tmdb_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Fast indexed retrieval from memory, local SQLite cache, or Supabase."""
    key = normalize_movie_key(title, year)
    if key in _IN_MEMORY_CATALOG:
        return _IN_MEMORY_CATALOG[key]

    # 1. Check local SQLite cache (<0.2ms)
    try:
        with sqlite3.connect(CATALOG_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if tmdb_id:
                cursor.execute("SELECT * FROM movie_catalog WHERE tmdb_id = ? OR movie_key = ?", (int(tmdb_id), key))
            else:
                cursor.execute("SELECT * FROM movie_catalog WHERE movie_key = ?", (key,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d["embedding"] = _blob_to_vec(d.get("embedding_blob"))
                _IN_MEMORY_CATALOG[key] = d
                return d
    except Exception as e:
        logger.debug(f"Local catalog cache lookup error for {key}: {e}")

    # 2. Check Supabase
    try:
        query = supabase_client.table("movie_catalog").select("*")
        if tmdb_id:
            query = query.or_(f"tmdb_id.eq.{int(tmdb_id)},movie_key.eq.{key}")
        else:
            query = query.eq("movie_key", key)
        res = query.limit(1).execute()
        if res.data:
            row = res.data[0]
            # Unpack embedding from JSON if stored
            emb_json = row.get("embedding_json")
            if emb_json and isinstance(emb_json, str) and emb_json.startswith("["):
                try:
                    vec = np.array(json.loads(emb_json), dtype=np.float32)
                    row["embedding"] = vec
                    row["embedding_blob"] = _vec_to_blob(vec)
                except Exception:
                    pass
            _cache_locally(row)
            _IN_MEMORY_CATALOG[key] = row
            return row
    except Exception as e:
        logger.debug(f"Supabase catalog lookup error for {key}: {e}")

    return None


def batch_get_catalog(keys: List[str]) -> Dict[str, Dict[str, Any]]:
    """Bulk retrieves catalog items from memory, local cache, and Supabase (<5ms)."""
    if not keys:
        return {}

    results = {}
    missing_keys = []
    for k in keys:
        if k in _IN_MEMORY_CATALOG:
            results[k] = _IN_MEMORY_CATALOG[k]
        else:
            missing_keys.append(k)

    if not missing_keys:
        return results

    # 1. Check local SQLite cache
    try:
        with sqlite3.connect(CATALOG_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            chunk_size = 500
            for i in range(0, len(missing_keys), chunk_size):
                chunk = missing_keys[i:i + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                cursor.execute(f"SELECT * FROM movie_catalog WHERE movie_key IN ({placeholders})", chunk)
                for row in cursor.fetchall():
                    d = dict(row)
                    d["embedding"] = _blob_to_vec(d.get("embedding_blob"))
                    _IN_MEMORY_CATALOG[d["movie_key"]] = d
                    results[d["movie_key"]] = d
    except Exception as e:
        logger.debug(f"Bulk local catalog lookup error: {e}")

    # 2. Check Supabase for still-missing keys
    still_missing = [k for k in missing_keys if k not in results]
    if still_missing:
        try:
            chunk_size = 100
            for i in range(0, len(still_missing), chunk_size):
                chunk = still_missing[i:i + chunk_size]
                res = supabase_client.table("movie_catalog").select("*").in_("movie_key", chunk).execute()
                for row in (res.data or []):
                    emb_json = row.get("embedding_json")
                    if emb_json and isinstance(emb_json, str) and emb_json.startswith("["):
                        try:
                            vec = np.array(json.loads(emb_json), dtype=np.float32)
                            row["embedding"] = vec
                            row["embedding_blob"] = _vec_to_blob(vec)
                        except Exception:
                            pass
                    _cache_locally(row)
                    _IN_MEMORY_CATALOG[row["movie_key"]] = row
                    results[row["movie_key"]] = row
        except Exception as e:
            logger.debug(f"Bulk Supabase catalog lookup error: {e}")

    return results


def _cache_locally(item_data: Dict[str, Any]):
    """Saves a row into the local SQLite cache."""
    try:
        with sqlite3.connect(CATALOG_DB_PATH) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO movie_catalog (
                    movie_key, tmdb_id, imdb_id, title, year, is_tv, genres,
                    overview, keywords, director, cinematographer, composer,
                    screenwriter, editor, lead_actors, studios, poster,
                    vote_average, vote_count, embedding_blob, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, (strftime('%s', 'now')))
            """, (
                item_data.get("movie_key"),
                item_data.get("tmdb_id"),
                item_data.get("imdb_id", ""),
                item_data.get("title", ""),
                item_data.get("year"),
                item_data.get("is_tv", 0),
                item_data.get("genres", ""),
                item_data.get("overview", ""),
                item_data.get("keywords", ""),
                item_data.get("director", ""),
                item_data.get("cinematographer", ""),
                item_data.get("composer", ""),
                item_data.get("screenwriter", ""),
                item_data.get("editor", ""),
                item_data.get("lead_actors", ""),
                item_data.get("studios", ""),
                item_data.get("poster", ""),
                float(item_data.get("vote_average") or 0.0),
                int(item_data.get("vote_count") or 0),
                item_data.get("embedding_blob")
            ))
            conn.commit()
    except Exception as e:
        logger.debug(f"Local SQLite cache write error: {e}")


def _normalize_title_for_match(t: str) -> str:
    s = str(t or "").lower()
    # Normalize Roman numerals to digits for matching sequels (e.g. Creed 3 == Creed III)
    s = re.sub(r"\bviii\b", "8", s)
    s = re.sub(r"\bvii\b", "7", s)
    s = re.sub(r"\bvi\b", "6", s)
    s = re.sub(r"\biv\b", "4", s)
    s = re.sub(r"\biii\b", "3", s)
    s = re.sub(r"\bii\b", "2", s)
    s = re.sub(r"\bix\b", "9", s)
    s = re.sub(r"\bx\b", "10", s)
    s = re.sub(r"\bv\b", "5", s)
    s = re.sub(r"\bi\b", "1", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _select_best_tmdb_result(results: List[Dict[str, Any]], query_title: str) -> Optional[int]:
    if not results:
        return None
    if len(results) == 1:
        return results[0].get("id")

    norm_query = _normalize_title_for_match(query_title)
    best_candidate = None
    best_score = -1e9

    for r in results:
        r_title = r.get("title") or r.get("name") or ""
        norm_r = _normalize_title_for_match(r_title)

        score = 0.0
        # Exact match after Roman numeral / whitespace normalization
        if norm_r == norm_query:
            score += 1000.0
        elif norm_query in norm_r:
            score += max(0.0, 500.0 - (len(norm_r) - len(norm_query)) * 20.0)

        # Popularity and vote count factor (prioritizes major releases over obscure 0-vote shorts/spinoffs)
        vote_count = r.get("vote_count", 0) or 0
        pop = r.get("popularity", 0.0) or 0.0
        score += min(500.0, math.log10(vote_count + 1) * 100.0)
        score += min(100.0, float(pop))

        if score > best_score:
            best_score = score
            best_candidate = r

    return best_candidate.get("id") if best_candidate else results[0].get("id")


def fetch_and_enrich_from_tmdb(
    title: str, 
    year: Any = None, 
    tmdb_id: Optional[int] = None, 
    is_tv: bool = False
) -> Dict[str, Any]:
    """
    Queries TMDB API with `append_to_response=credits,keywords` to obtain:
    - Full multi-genres
    - Plot overview synopsis
    - Thematic keywords / tags
    - Crew: Director, DOP, Composer, Screenwriter, Editor
    - Cast: Top 6 lead actors
    - Studios, poster, vote average, vote count
    """
    key = normalize_movie_key(title, year)
    existing = get_catalog_item(title, year, tmdb_id)
    if existing and existing.get("overview") and existing.get("cinematographer"):
        return existing

    api_key = _get_api_key()
    item_data = {
        "movie_key": key,
        "tmdb_id": tmdb_id,
        "imdb_id": "",
        "title": title,
        "year": int(str(year)[:4]) if str(year or "")[:4].isdigit() else None,
        "is_tv": 1 if is_tv else 0,
        "genres": "",
        "overview": "",
        "keywords": "",
        "director": "",
        "cinematographer": "",
        "composer": "",
        "screenwriter": "",
        "editor": "",
        "lead_actors": "",
        "studios": "",
        "poster": "",
        "vote_average": 0.0,
        "vote_count": 0
    }

    if not api_key:
        return item_data

    try:
        resolved_id = tmdb_id
        media_type = "tv" if is_tv else "movie"

        if not resolved_id:
            clean_title = re.sub(r",?\s*season\s*\d+.*$", "", title, flags=re.IGNORECASE).strip()
            params = {"api_key": api_key, "query": clean_title}
            if year and not is_tv:
                params["year"] = str(year)[:4]
            elif year and is_tv:
                params["first_air_date_year"] = str(year)[:4]

            search_endpoint = f"{TMDB_BASE_URL}/search/{media_type}"
            s_res = requests.get(search_endpoint, params=params, timeout=5)
            if s_res.status_code == 200:
                results = s_res.json().get("results", [])
                if results:
                    resolved_id = _select_best_tmdb_result(results, clean_title)
                elif not is_tv:
                    tv_s_res = requests.get(f"{TMDB_BASE_URL}/search/tv", params=params, timeout=5)
                    if tv_s_res.status_code == 200:
                        tv_results = tv_s_res.json().get("results", [])
                        if tv_results:
                            resolved_id = _select_best_tmdb_result(tv_results, clean_title)
                            media_type = "tv"
                            item_data["is_tv"] = 1

        if not resolved_id:
            return item_data

        item_data["tmdb_id"] = resolved_id

        # Detailed fetch with credits & keywords
        details_url = f"{TMDB_BASE_URL}/{media_type}/{resolved_id}"
        d_res = requests.get(
            details_url, 
            params={"api_key": api_key, "append_to_response": "credits,keywords"}, 
            timeout=6
        )
        if d_res.status_code != 200:
            return item_data

        d = d_res.json()

        matched_title = d.get("title") or d.get("name") or title
        item_data["title"] = matched_title
        release_date = d.get("release_date") or d.get("first_air_date") or ""
        if release_date and release_date[:4].isdigit():
            item_data["year"] = int(release_date[:4])

        item_data["overview"] = (d.get("overview") or "").strip()

        genre_names = [g.get("name") for g in d.get("genres", []) if g.get("name")]
        item_data["genres"] = ", ".join(genre_names)

        kw_list = []
        kw_data = d.get("keywords", {})
        raw_kws = kw_data.get("keywords") or kw_data.get("results") or []
        for kw in raw_kws:
            name = kw.get("name")
            if name:
                kw_list.append(name.strip())
        item_data["keywords"] = ", ".join(kw_list[:14])

        poster_path = d.get("poster_path")
        if poster_path:
            item_data["poster"] = f"https://image.tmdb.org/t/p/w500{poster_path}"
        item_data["vote_average"] = float(d.get("vote_average") or 0.0)
        item_data["vote_count"] = int(d.get("vote_count") or 0)
        item_data["imdb_id"] = d.get("imdb_id") or ""

        studios = [p.get("name") for p in d.get("production_companies", []) if p.get("name")]
        item_data["studios"] = ", ".join(studios[:3])

        credits = d.get("credits", {})
        crew = credits.get("crew", [])
        cast = credits.get("cast", [])

        directors = []
        dops = []
        composers = []
        writers = []
        editors = []

        for member in crew:
            job = (member.get("job") or "").strip()
            name = (member.get("name") or "").strip()
            if not name:
                continue
            if job in ["Director", "Series Director"]:
                directors.append(name)
            elif job in ["Director of Photography", "Cinematographer"]:
                dops.append(name)
            elif job in ["Original Music Composer", "Music", "Music Director", "Original Score"]:
                composers.append(name)
            elif job in ["Screenplay", "Writer", "Author", "Story", "Series Writer", "Comic Book", "Original Series Design"]:
                writers.append(name)
            elif job == "Editor":
                editors.append(name)

        if media_type == "tv" and not directors:
            created_by = [c.get("name") for c in d.get("created_by", []) if c.get("name")]
            directors.extend(created_by)
            if not directors:
                for member in crew:
                    job = (member.get("job") or "").strip()
                    name = (member.get("name") or "").strip()
                    if job in ["Creator", "Original Series Design", "Author", "Comic Book"] and name:
                        directors.append(name)
                if not directors:
                    for member in crew:
                        job = (member.get("job") or "").strip()
                        name = (member.get("name") or "").strip()
                        if job in ["Executive Producer"] and name:
                            directors.append(name)

        item_data["director"] = ", ".join(list(dict.fromkeys(directors))[:2])
        item_data["cinematographer"] = ", ".join(list(dict.fromkeys(dops))[:2])
        item_data["composer"] = ", ".join(list(dict.fromkeys(composers))[:2])
        item_data["screenwriter"] = ", ".join(list(dict.fromkeys(writers))[:2])
        item_data["editor"] = ", ".join(list(dict.fromkeys(editors))[:2])

        lead_actors = [c.get("name") for c in cast[:6] if c.get("name")]
        item_data["lead_actors"] = ", ".join(lead_actors)

    except Exception as e:
        logger.debug(f"Error enriching '{title}' from TMDB: {e}")

    return item_data


def upsert_catalog_item(item_data: Dict[str, Any], compute_embedding: bool = True) -> Dict[str, Any]:
    """
    Inserts or updates a movie record in Supabase `movie_catalog` AND local SQLite cache.
    Automatically computes and caches the 384D semantic vector via FastEmbed if missing.
    """
    key = item_data.get("movie_key") or normalize_movie_key(item_data.get("title", ""), item_data.get("year"))
    item_data["movie_key"] = key

    # Compute embedding if missing
    emb = item_data.get("embedding")
    emb_blob = item_data.get("embedding_blob")
    if emb is None and not emb_blob and compute_embedding:
        try:
            from services.embedding_service import construct_semantic_text, _get_embedding_model
            sem_text = construct_semantic_text(item_data)
            model = _get_embedding_model()
            if model is not None:
                vec = list(model.embed([sem_text]))[0]
                vec_norm = vec / (np.linalg.norm(vec) + 1e-9)
                item_data["embedding"] = vec_norm.astype(np.float32)
                emb_blob = _vec_to_blob(vec_norm)
                item_data["embedding_blob"] = emb_blob
        except Exception as e:
            logger.debug(f"Failed to compute embedding for {key}: {e}")

    # 1. Update local cache
    _cache_locally(item_data)
    _IN_MEMORY_CATALOG[key] = item_data

    # 2. Upsert to Supabase
    try:
        supabase_payload = {
            "movie_key": str(item_data.get("movie_key")),
            "tmdb_id": _safe_int(item_data.get("tmdb_id")),
            "imdb_id": str(item_data.get("imdb_id") or ""),
            "title": str(item_data.get("title") or ""),
            "year": _safe_int(item_data.get("year")),
            "is_tv": 1 if item_data.get("is_tv") in [1, "1", True] else 0,
            "genres": str(item_data.get("genres") or ""),
            "overview": str(item_data.get("overview") or ""),
            "keywords": str(item_data.get("keywords") or ""),
            "director": str(item_data.get("director") or ""),
            "cinematographer": str(item_data.get("cinematographer") or ""),
            "composer": str(item_data.get("composer") or ""),
            "screenwriter": str(item_data.get("screenwriter") or ""),
            "editor": str(item_data.get("editor") or ""),
            "lead_actors": str(item_data.get("lead_actors") or ""),
            "studios": str(item_data.get("studios") or ""),
            "poster": str(item_data.get("poster") or ""),
            "vote_average": _safe_float(item_data.get("vote_average")),
            "vote_count": _safe_int(item_data.get("vote_count")) or 0
        }
        if item_data.get("embedding") is not None:
            supabase_payload["embedding_json"] = json.dumps([round(float(x), 6) for x in item_data["embedding"]])

        supabase_client.table("movie_catalog").upsert(supabase_payload).execute()
    except Exception as e:
        logger.debug(f"Supabase upsert notice for {key}: {e}")

    return item_data


def enrich_pool_items(pool: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Bulk enriches a pool of movie dictionaries in place (<5ms):
    Looks up all movie keys in `movie_catalog`.
    Merges: overview, keywords/tags, lead_actors, cinematographer, composer, screenwriter, studios, and full multi-genres.
    Also returns the craft map required by Knowledge Graph / LightGCN.
    """
    if not pool:
        return {}

    keys = []
    item_map = {}
    for it in pool:
        title = it.get("title") or it.get("movie") or ""
        year = it.get("year") or it.get("p_year")
        k = normalize_movie_key(title, year)
        it["movie_key"] = k
        keys.append(k)
        item_map[k] = it

    catalog_data = batch_get_catalog(keys)
    crafts_by_key = {}

    for k, it in item_map.items():
        cat = catalog_data.get(k)
        if cat:
            # Multi-genres
            if cat.get("genres") and (not it.get("genre") or it.get("genre") in ["Cinema", "Unknown"] or len(cat.get("genres")) > len(it.get("genre", ""))):
                it["genre"] = cat["genres"]

            # Overview synopsis
            if cat.get("overview"):
                it["overview"] = cat["overview"]

            # Keywords / Tags
            if cat.get("keywords"):
                it["tags"] = cat["keywords"]

            # Director
            if cat.get("director") and (not it.get("director") or it.get("director") in ["Unknown", ""]):
                it["director"] = cat["director"]

            # Poster
            if cat.get("poster") and (not it.get("poster") or "placeholder" in str(it.get("poster"))):
                it["poster"] = cat["poster"]

            # Craft dictionary for graph convolution & HUD
            craft_dict = {
                "movie_key": k,
                "title": cat.get("title") or it.get("title"),
                "year": str(cat.get("year") or it.get("year") or ""),
                "director": cat.get("director") or it.get("director", ""),
                "cinematographer": cat.get("cinematographer", ""),
                "composer": cat.get("composer", ""),
                "screenwriter": cat.get("screenwriter", ""),
                "editor": cat.get("editor", ""),
                "lead_actors": cat.get("lead_actors", ""),
                "studios": cat.get("studios", ""),
                "poster": cat.get("poster") or it.get("poster", "")
            }
            it["craft"] = craft_dict
            it["lead_actors"] = cat.get("lead_actors", "")
            crafts_by_key[k] = craft_dict
            
            # Pre-computed embedding pass-through
            if cat.get("embedding") is not None:
                it["embedding"] = cat["embedding"]
        else:
            craft_dict = {
                "movie_key": k,
                "title": it.get("title") or it.get("movie"),
                "year": str(it.get("year") or it.get("p_year") or ""),
                "director": it.get("director", ""),
                "cinematographer": "",
                "composer": "",
                "screenwriter": "",
                "editor": "",
                "lead_actors": "",
                "studios": "",
                "poster": it.get("poster", "")
            }
            it["craft"] = craft_dict
            crafts_by_key[k] = craft_dict

    return crafts_by_key


def sync_local_to_supabase(batch_size: int = 50) -> Dict[str, int]:
    """
    Pushes all locally cached catalog records into Supabase `movie_catalog` in batches.
    Useful for populating Supabase after creating the table, or syncing offline work.
    """
    stats = {"total_read": 0, "synced": 0, "errors": 0}
    try:
        with sqlite3.connect(CATALOG_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM movie_catalog")
            rows = cursor.fetchall()
            stats["total_read"] = len(rows)

            batch = []
            for r in rows:
                d = dict(r)
                item = {
                    "movie_key": str(d.get("movie_key")),
                    "tmdb_id": _safe_int(d.get("tmdb_id")),
                    "imdb_id": str(d.get("imdb_id") or ""),
                    "title": str(d.get("title") or ""),
                    "year": _safe_int(d.get("year")),
                    "is_tv": 1 if d.get("is_tv") in [1, "1", True] else 0,
                    "genres": str(d.get("genres") or ""),
                    "overview": str(d.get("overview") or ""),
                    "keywords": str(d.get("keywords") or ""),
                    "director": str(d.get("director") or ""),
                    "cinematographer": str(d.get("cinematographer") or ""),
                    "composer": str(d.get("composer") or ""),
                    "screenwriter": str(d.get("screenwriter") or ""),
                    "editor": str(d.get("editor") or ""),
                    "lead_actors": str(d.get("lead_actors") or ""),
                    "studios": str(d.get("studios") or ""),
                    "poster": str(d.get("poster") or ""),
                    "vote_average": _safe_float(d.get("vote_average")),
                    "vote_count": _safe_int(d.get("vote_count")) or 0
                }
                emb_blob = d.get("embedding_blob")
                if emb_blob:
                    vec = _blob_to_vec(emb_blob)
                    if vec is not None:
                        item["embedding_json"] = json.dumps([round(float(x), 6) for x in vec])

                batch.append(item)
                if len(batch) >= batch_size:
                    try:
                        supabase_client.table("movie_catalog").upsert(batch).execute()
                        stats["synced"] += len(batch)
                    except Exception as be:
                        logger.error(f"Error syncing batch to Supabase: {be}")
                        stats["errors"] += len(batch)
                    batch = []

            if batch:
                try:
                    supabase_client.table("movie_catalog").upsert(batch).execute()
                    stats["synced"] += len(batch)
                except Exception as be:
                    logger.error(f"Error syncing final batch to Supabase: {be}")
                    stats["errors"] += len(batch)

    except Exception as e:
        logger.error(f"Failed to sync local catalog to Supabase: {e}")

    return stats


# =============================================================================
# TV SEASON CANONICAL CATALOG EXTENSIONS
# =============================================================================

def resolve_tv_season_number(
    raw_title: str,
    tmdb_id: Optional[int] = None,
    current_season: Optional[Any] = None,
    poster_url: Optional[str] = None
) -> int:
    r"""
    Intelligently extracts the accurate season number for a TV show:
    1. Regex check for Season / Series / Volume / Part / S (\d+).
    2. TMDB season name check (e.g. 'The Final Season', 'Volume 4', subtitle matching).
    3. Poster-based matching against TMDB season posters (e.g. JoJo's Bizarre Adventure parts).
    4. Fallback to current_season or 1.
    """
    if raw_title:
        m = re.search(r'(?i)\b(?:season|series|volume|vol|part|bk|book|stagione|s)\s*(\d+)\b', raw_title)
        if m:
            return int(m.group(1))

    api_key = _get_api_key()
    if tmdb_id and api_key:
        try:
            url = f"{TMDB_BASE_URL}/tv/{int(tmdb_id)}"
            res = requests.get(url, params={"api_key": api_key}, timeout=4)
            if res.status_code == 200:
                data = res.json()
                seasons = [s for s in data.get("seasons", []) if s.get("season_number", 0) > 0]

                # Match poster if available
                if poster_url:
                    clean_post = poster_url.split("/")[-1].strip()
                    for s in seasons:
                        p_path = (s.get("poster_path") or "").split("/")[-1].strip()
                        if p_path and p_path == clean_post:
                            return int(s["season_number"])

                title_lower = raw_title.lower()
                # Check for final season terms
                if any(x in title_lower for x in ["the final season", "final season", "last season"]):
                    for s in seasons:
                        if any(x in (s.get("name") or "").lower() for x in ["final", "the final season"]):
                            return int(s["season_number"])
                    if seasons:
                        return int(seasons[-1]["season_number"])

                # Check named season / subtitle matching season name
                for s in seasons:
                    s_name = (s.get("name") or "").lower().strip()
                    if len(s_name) > 3 and s_name in title_lower:
                        return int(s["season_number"])
        except Exception:
            pass

    if current_season and str(current_season).isdigit() and int(current_season) > 0:
        return int(current_season)
    return 1


def normalize_season_key(tmdb_id: Any, season_number: Any) -> str:
    s_num = int(season_number) if str(season_number or "").isdigit() else 1
    return f"{int(tmdb_id)}_s{s_num}"


def get_tv_season_catalog_item(tmdb_id: int, season_number: int = 1) -> Optional[Dict[str, Any]]:
    """Fast indexed retrieval of a TV season from memory, SQLite cache, or Supabase."""
    if not tmdb_id:
        return None
    s_key = normalize_season_key(tmdb_id, season_number)
    if s_key in _IN_MEMORY_SEASONS:
        return _IN_MEMORY_SEASONS[s_key]

    # 1. Local SQLite cache (<0.2ms)
    try:
        with sqlite3.connect(CATALOG_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tv_season_catalog WHERE season_key = ?", (s_key,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d["embedding"] = _blob_to_vec(d.get("embedding_blob"))
                _IN_MEMORY_SEASONS[s_key] = d
                return d
    except Exception as e:
        logger.debug(f"Local tv_season_catalog cache lookup error for {s_key}: {e}")

    # 2. Supabase
    try:
        res = supabase_client.table("tv_season_catalog").select("*").eq("season_key", s_key).limit(1).execute()
        if res.data:
            row = res.data[0]
            emb_json = row.get("embedding_json")
            if emb_json and isinstance(emb_json, str) and emb_json.startswith("["):
                try:
                    vec = np.array(json.loads(emb_json), dtype=np.float32)
                    row["embedding"] = vec
                    row["embedding_blob"] = _vec_to_blob(vec)
                except Exception:
                    pass
            _cache_season_locally(row)
            _IN_MEMORY_SEASONS[s_key] = row
            return row
    except Exception as e:
        logger.debug(f"Supabase tv_season_catalog lookup error for {s_key}: {e}")

    return None


def _cache_season_locally(item_data: Dict[str, Any]):
    """Internal write to local SQLite replica cache for tv_season_catalog."""
    try:
        with sqlite3.connect(CATALOG_DB_PATH) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tv_season_catalog (
                    season_key, tmdb_id, season_number, show_title,
                    season_name, air_date, year, overview, poster,
                    vote_average, episode_count, director, lead_actors,
                    cinematographer, composer, screenwriter, embedding_blob
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(item_data.get("season_key")),
                int(item_data.get("tmdb_id")),
                int(item_data.get("season_number")),
                str(item_data.get("show_title") or ""),
                str(item_data.get("season_name") or ""),
                str(item_data.get("air_date") or ""),
                _safe_int(item_data.get("year")),
                str(item_data.get("overview") or ""),
                str(item_data.get("poster") or ""),
                float(item_data.get("vote_average") or 0.0),
                int(item_data.get("episode_count") or 0),
                str(item_data.get("director") or ""),
                str(item_data.get("lead_actors") or ""),
                str(item_data.get("cinematographer") or ""),
                str(item_data.get("composer") or ""),
                str(item_data.get("screenwriter") or ""),
                item_data.get("embedding_blob")
            ))
            conn.commit()
    except Exception as e:
        logger.debug(f"Local SQLite cache write error for tv_season_catalog: {e}")


def _fetch_tv_season_from_episode_groups(
    tmdb_id: int, 
    season_number: int, 
    api_key: str, 
    item_data: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Fallback for anime and series where TMDB groups multi-cour/annual seasons
    under Episode Groups rather than root /season/N endpoints (e.g. Frieren Season 2).
    """
    try:
        eg_url = f"{TMDB_BASE_URL}/tv/{int(tmdb_id)}/episode_groups"
        eg_res = requests.get(eg_url, params={"api_key": api_key}, timeout=4)
        if eg_res.status_code != 200:
            return None

        results = eg_res.json().get("results") or []
        target_group = None
        for eg in results:
            eg_id = eg.get("id")
            det_res = requests.get(f"{TMDB_BASE_URL}/tv/episode_group/{eg_id}", params={"api_key": api_key}, timeout=4)
            if det_res.status_code == 200:
                for g in (det_res.json().get("groups") or []):
                    g_name = g.get("name", "")
                    if re.search(rf"(?i)\b(?:season|series|part|cours?|volume)\s*0?{int(season_number)}\b", g_name) or g.get("order") == int(season_number):
                        target_group = g
                        break
            if target_group:
                break

        if not target_group:
            return None

        eps = target_group.get("episodes") or []
        item_data["season_name"] = target_group.get("name") or f"Season {season_number}"
        item_data["episode_count"] = len(eps)
        if eps:
            first_ep = eps[0]
            ep_date = first_ep.get("air_date") or ""
            item_data["air_date"] = ep_date
            if ep_date and ep_date[:4].isdigit():
                item_data["year"] = int(ep_date[:4])

        # Fetch show details for title, overarching series overview, and general craft/cast
        tv_details = requests.get(f"{TMDB_BASE_URL}/tv/{int(tmdb_id)}", params={"api_key": api_key, "append_to_response": "credits"}, timeout=5)
        if tv_details.status_code == 200:
            tv_d = tv_details.json()
            if not item_data.get("show_title"):
                item_data["show_title"] = tv_d.get("name") or ""
            item_data["overview"] = tv_d.get("overview") or ""
            credits = tv_d.get("credits", {})
            cast = [c.get("name") for c in credits.get("cast", [])[:6] if c.get("name")]
            item_data["lead_actors"] = ", ".join(cast)
            directors = [c.get("name") for c in tv_d.get("created_by", []) if c.get("name")]
            for cr in credits.get("crew", []):
                if cr.get("job") in ["Director", "Series Director"] and cr.get("name"):
                    directors.append(cr["name"])
            item_data["director"] = ", ".join(list(dict.fromkeys(directors))[:2])

        # For anime/episode groups: select distinct official poster from TMDB images gallery
        img_res = requests.get(
            f"{TMDB_BASE_URL}/tv/{int(tmdb_id)}/images", 
            params={"api_key": api_key, "include_image_language": "en,ja,null"}, 
            timeout=4
        )
        if img_res.status_code == 200:
            posters = img_res.json().get("posters") or []
            main_poster_path = tv_d.get("poster_path") or ""
            
            # Sort by community votes and rating so top official art is prioritized
            sorted_posters = sorted(
                posters, 
                key=lambda x: (x.get("vote_count", 0), x.get("vote_average", 0)), 
                reverse=True
            )
            
            candidates = []
            seen = set()
            for p in sorted_posters:
                fp = p.get("file_path") or ""
                ar = p.get("aspect_ratio") or 0.67
                if fp and fp not in seen and 0.55 <= ar <= 0.8:
                    seen.add(fp)
                    candidates.append(fp)

            alt_candidates = [c for c in candidates if c != main_poster_path]
            s_num = int(season_number) if str(season_number).isdigit() else 1
            if s_num == 1:
                chosen_poster = main_poster_path or (candidates[0] if candidates else None)
            else:
                alt_idx = s_num - 2
                chosen_poster = alt_candidates[alt_idx % len(alt_candidates)] if alt_candidates else (candidates[alt_idx % len(candidates)] if candidates else main_poster_path)

            if chosen_poster:
                item_data["poster"] = f"https://image.tmdb.org/t/p/w500{chosen_poster}"

        return item_data
    except Exception as e:
        logger.debug(f"Error in _fetch_tv_season_from_episode_groups: {e}")
        return None


def fetch_and_enrich_tv_season(
    tmdb_id: int, 
    season_number: int = 1, 
    show_title: Optional[str] = None,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Queries TMDB API for season-level metadata with `append_to_response=credits,keywords`:
    - Specific season synopsis (`overview`)
    - Season name/subtitle (e.g. 'Night Country')
    - Premiere air date & season release year
    - Season-specific cast (top 6 actors)
    - Season directors, showrunner, composer, cinematographer, writers
    - Season poster & vote average
    """
    s_key = normalize_season_key(tmdb_id, season_number)
    existing = get_tv_season_catalog_item(tmdb_id, season_number)
    if existing and not force_refresh and existing.get("overview") and existing.get("lead_actors") and existing.get("year"):
        return existing

    api_key = _get_api_key()
    item_data = {
        "season_key": s_key,
        "tmdb_id": int(tmdb_id),
        "season_number": int(season_number),
        "show_title": show_title or "",
        "season_name": f"Season {season_number}",
        "air_date": "",
        "year": None,
        "overview": "",
        "poster": "",
        "vote_average": 0.0,
        "episode_count": 0,
        "director": "",
        "lead_actors": "",
        "cinematographer": "",
        "composer": "",
        "screenwriter": ""
    }

    if not api_key:
        return item_data

    try:
        url = f"{TMDB_BASE_URL}/tv/{int(tmdb_id)}/season/{int(season_number)}"
        res = requests.get(url, params={"api_key": api_key, "append_to_response": "credits,keywords"}, timeout=6)
        if res.status_code != 200:
            eg_data = _fetch_tv_season_from_episode_groups(tmdb_id, season_number, api_key, item_data.copy())
            if eg_data and eg_data.get("year"):
                return eg_data
            return item_data

        d = res.json()
        item_data["season_name"] = d.get("name") or f"Season {season_number}"
        item_data["overview"] = d.get("overview") or ""
        air_date = d.get("air_date") or ""
        item_data["air_date"] = air_date
        if air_date and air_date[:4].isdigit():
            item_data["year"] = int(air_date[:4])
        
        episodes = d.get("episodes") or []
        item_data["episode_count"] = len(episodes)
        if not item_data.get("year") and episodes and episodes[0].get("air_date"):
            ep_date = str(episodes[0]["air_date"])
            if ep_date[:4].isdigit():
                item_data["year"] = int(ep_date[:4])
                item_data["air_date"] = ep_date
        
        poster_path = d.get("poster_path")
        if poster_path:
            item_data["poster"] = f"https://image.tmdb.org/t/p/w500{poster_path}"
        
        item_data["vote_average"] = float(d.get("vote_average") or 0.0)

        credits = d.get("credits", {})
        cast = credits.get("cast", [])
        crew = credits.get("crew", [])

        lead_actors = [c.get("name") for c in cast[:6] if c.get("name")]
        item_data["lead_actors"] = ", ".join(lead_actors)

        directors = []
        dops = []
        composers = []
        writers = []

        for member in crew:
            job = (member.get("job") or "").strip()
            name = (member.get("name") or "").strip()
            if not name:
                continue
            if job in ["Director", "Series Director"]:
                directors.append(name)
            elif job in ["Director of Photography", "Cinematographer"]:
                dops.append(name)
            elif job in ["Original Music Composer", "Music", "Music Director", "Original Score"]:
                composers.append(name)
            elif job in ["Writer", "Screenplay", "Story", "Series Writer"]:
                writers.append(name)

        if not directors and episodes:
            for ep in episodes:
                for cr in ep.get("crew", []):
                    if cr.get("job") == "Director" and cr.get("name"):
                        directors.append(cr["name"])
                    elif cr.get("job") in ["Writer", "Screenplay"] and cr.get("name"):
                        writers.append(cr["name"])

        if not item_data["show_title"] or not item_data.get("overview"):
            tv_details = requests.get(f"{TMDB_BASE_URL}/tv/{int(tmdb_id)}", params={"api_key": api_key}, timeout=5)
            if tv_details.status_code == 200:
                tv_d = tv_details.json()
                if not item_data["show_title"]:
                    item_data["show_title"] = tv_d.get("name") or ""
                if not item_data.get("overview"):
                    item_data["overview"] = tv_d.get("overview") or ""
                if not directors:
                    directors.extend([c.get("name") for c in tv_d.get("created_by", []) if c.get("name")])

        item_data["director"] = ", ".join(list(dict.fromkeys(directors))[:2])
        item_data["cinematographer"] = ", ".join(list(dict.fromkeys(dops))[:2])
        item_data["composer"] = ", ".join(list(dict.fromkeys(composers))[:2])
        item_data["screenwriter"] = ", ".join(list(dict.fromkeys(writers))[:2])

    except Exception as e:
        logger.debug(f"Error enriching TV season {tmdb_id} s{season_number} from TMDB: {e}")

    return item_data


def upsert_tv_season_catalog_item(item_data: Dict[str, Any], compute_embedding: bool = True) -> Dict[str, Any]:
    """
    Inserts or updates a TV season record in Supabase `public.tv_season_catalog` AND local SQLite cache.
    Automatically computes and caches the 384D semantic vector via FastEmbed if missing.
    """
    tmdb_id = _safe_int(item_data.get("tmdb_id"))
    season_num = _safe_int(item_data.get("season_number")) or 1
    s_key = item_data.get("season_key") or normalize_season_key(tmdb_id, season_num)
    item_data["season_key"] = s_key
    item_data["tmdb_id"] = tmdb_id
    item_data["season_number"] = season_num

    # Compute embedding if missing
    emb = item_data.get("embedding")
    emb_blob = item_data.get("embedding_blob")
    if emb is None and not emb_blob and compute_embedding:
        try:
            from services.embedding_service import construct_semantic_text, _get_embedding_model
            sem_data = dict(item_data)
            sem_data["title"] = f"{item_data.get('show_title', '')}: {item_data.get('season_name', '')}"
            sem_text = construct_semantic_text(sem_data)
            model = _get_embedding_model()
            if model is not None:
                vec = list(model.embed([sem_text]))[0]
                vec_norm = vec / (np.linalg.norm(vec) + 1e-9)
                item_data["embedding"] = vec_norm.astype(np.float32)
                emb_blob = _vec_to_blob(vec_norm)
                item_data["embedding_blob"] = emb_blob
        except Exception as e:
            logger.debug(f"Failed to compute embedding for TV season {s_key}: {e}")

    # 1. Update local SQLite cache
    _cache_season_locally(item_data)
    _IN_MEMORY_SEASONS[s_key] = item_data

    # 2. Upsert to Supabase
    try:
        supabase_payload = {
            "season_key": str(item_data.get("season_key")),
            "tmdb_id": int(item_data.get("tmdb_id")),
            "season_number": int(item_data.get("season_number")),
            "show_title": str(item_data.get("show_title") or ""),
            "season_name": str(item_data.get("season_name") or ""),
            "air_date": str(item_data.get("air_date") or ""),
            "year": _safe_int(item_data.get("year")),
            "overview": str(item_data.get("overview") or ""),
            "poster": str(item_data.get("poster") or ""),
            "vote_average": _safe_float(item_data.get("vote_average")),
            "episode_count": _safe_int(item_data.get("episode_count")) or 0,
            "director": str(item_data.get("director") or ""),
            "lead_actors": str(item_data.get("lead_actors") or ""),
            "cinematographer": str(item_data.get("cinematographer") or ""),
            "composer": str(item_data.get("composer") or ""),
            "screenwriter": str(item_data.get("screenwriter") or "")
        }
        if emb_blob:
            vec = _blob_to_vec(emb_blob)
            if vec is not None:
                supabase_payload["embedding_json"] = json.dumps([round(float(x), 6) for x in vec])
        supabase_client.table("tv_season_catalog").upsert(supabase_payload).execute()
    except Exception as se:
        logger.debug(f"Supabase tv_season_catalog upsert error for {s_key}: {se}")

    return item_data


def sync_local_seasons_to_supabase(batch_size: int = 50) -> Dict[str, int]:
    """Pushes all locally cached TV season records into Supabase `tv_season_catalog` in batches."""
    stats = {"total_read": 0, "synced": 0, "errors": 0}
    try:
        with sqlite3.connect(CATALOG_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tv_season_catalog")
            rows = cursor.fetchall()
            stats["total_read"] = len(rows)

            batch = []
            for r in rows:
                d = dict(r)
                item = {
                    "season_key": str(d.get("season_key")),
                    "tmdb_id": int(d.get("tmdb_id")),
                    "season_number": int(d.get("season_number")),
                    "show_title": str(d.get("show_title") or ""),
                    "season_name": str(d.get("season_name") or ""),
                    "air_date": str(d.get("air_date") or ""),
                    "year": _safe_int(d.get("year")),
                    "overview": str(d.get("overview") or ""),
                    "poster": str(d.get("poster") or ""),
                    "vote_average": _safe_float(d.get("vote_average")),
                    "episode_count": _safe_int(d.get("episode_count")) or 0,
                    "director": str(d.get("director") or ""),
                    "lead_actors": str(d.get("lead_actors") or ""),
                    "cinematographer": str(d.get("cinematographer") or ""),
                    "composer": str(d.get("composer") or ""),
                    "screenwriter": str(d.get("screenwriter") or "")
                }
                emb_blob = d.get("embedding_blob")
                if emb_blob:
                    vec = _blob_to_vec(emb_blob)
                    if vec is not None:
                        item["embedding_json"] = json.dumps([round(float(x), 6) for x in vec])
                batch.append(item)

                if len(batch) >= batch_size:
                    try:
                        supabase_client.table("tv_season_catalog").upsert(batch).execute()
                        stats["synced"] += len(batch)
                    except Exception as be:
                        logger.error(f"Error syncing seasons batch to Supabase: {be}")
                        stats["errors"] += len(batch)
                    batch = []

            if batch:
                try:
                    supabase_client.table("tv_season_catalog").upsert(batch).execute()
                    stats["synced"] += len(batch)
                except Exception as be:
                    logger.error(f"Error syncing final seasons batch to Supabase: {be}")
                    stats["errors"] += len(batch)
    except Exception as e:
        logger.error(f"Failed to sync local seasons to Supabase: {e}")

    return stats
