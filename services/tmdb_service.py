import os
import re
import time
import json
import sqlite3
from typing import Dict, List, Any, Optional
from functools import wraps
import requests
from tmdbv3api import TMDb, Movie, TV, Season, Search

# Initialize TMDb
tmdb = TMDb()
tmdb.api_key = os.environ.get('TMDB_API_KEY')

movie_api = Movie()
tv_api = TV()
season_api = Season()
search_api = Search()

_CACHE_TTL = 3600  # 1 hour
_INSTANCE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance")
os.makedirs(_INSTANCE_DIR, exist_ok=True)
_REC_CACHE_DB_PATH = os.path.join(_INSTANCE_DIR, "tmdb_recommendations.db")

def _normalize_rec_seed_key(title: str, year: Any = "", is_tv: bool = False) -> str:
    clean_title = re.sub(r"[^a-z0-9]", "", str(title).lower())
    clean_year = str(year)[:4] if year else ""
    type_suffix = "tv" if is_tv else "movie"
    return f"{clean_title}_{clean_year}_{type_suffix}"

def _init_rec_db():
    try:
        with sqlite3.connect(_REC_CACHE_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tmdb_recommendations (
                    seed_key TEXT PRIMARY KEY,
                    title TEXT,
                    year TEXT,
                    is_tv INTEGER,
                    recommendations_json TEXT,
                    created_at REAL
                )
            """)
            conn.commit()
    except Exception as e:
        print(f"Error initializing tmdb_recommendations DB: {e}")

def get_cached_recommendations(title: str, year: Any = None, is_tv: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Instant lookup of cached TMDB recommendations from local SQLite database."""
    if not title:
        return None
    try:
        _init_rec_db()
        key = _normalize_rec_seed_key(title, year, is_tv)
        with sqlite3.connect(_REC_CACHE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT recommendations_json, created_at FROM tmdb_recommendations WHERE seed_key = ?", (key,))
            row = cursor.fetchone()
            if row:
                rec_json, created_at = row
                if time.time() - created_at < 60 * 86400:  # 60-day TTL
                    return json.loads(rec_json)
    except Exception as e:
        print(f"Error reading from tmdb_recommendations cache: {e}")
    return None

def save_cached_recommendations(title: str, year: Any = None, is_tv: bool = False, candidates: List[Dict[str, Any]] = None):
    """Saves fetched TMDB recommendations to local SQLite database."""
    if not title:
        return
    try:
        _init_rec_db()
        key = _normalize_rec_seed_key(title, year, is_tv)
        rec_json = json.dumps(candidates or [])
        with sqlite3.connect(_REC_CACHE_DB_PATH) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tmdb_recommendations (seed_key, title, year, is_tv, recommendations_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (key, str(title), str(year or ""), 1 if is_tv else 0, rec_json, time.time()))
            conn.commit()
    except Exception as e:
        print(f"Error writing to tmdb_recommendations cache: {e}")

def _cached(ttl=_CACHE_TTL, maxsize=1000):
    """In-memory TTL cache decorator for TMDB lookups."""
    def decorator(func):
        cache_store = {}
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            if key in cache_store:
                val, timestamp = cache_store[key]
                if now - timestamp < ttl:
                    return val
            result = func(*args, **kwargs)
            if result is not None:
                if len(cache_store) >= maxsize:
                    sorted_keys = sorted(cache_store.keys(), key=lambda k: cache_store[k][1])
                    for k in sorted_keys[:maxsize // 5]:
                        cache_store.pop(k, None)
                cache_store[key] = (result, now)
            return result
        return wrapper
    return decorator

movie_genres = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
    27: "Horror", 10402: "Musical", 9648: "Mystery", 10749: "Romance", 878: "Sci-Fi",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western"
}

tv_genres = {
    10759: "Action & Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 10762: "Kids", 9648: "Mystery",
    10763: "News", 10764: "Reality", 10765: "Sci-Fi & Fantasy", 10766: "Soap",
    10767: "Talk", 10768: "War & Politics", 37: "Western"
}

@_cached(ttl=3600)
def get_movie_details(title, year=None, manual_director=None, tmdb_id=None):
    """
    Search TMDB for a movie, extracting poster, genres, and director.
    If tmdb_id is provided, fetches exact movie directly without search guessing.
    Strictly prioritizes Movies over TV shows.
    """
    clean_title = re.sub(r',?\s*season\s*\d+.*$', '', title, flags=re.IGNORECASE).strip()
    if not clean_title:
        clean_title = title

    try:
        best_match = None
        is_tv_result = False

        # 1. Direct ID lookup if available
        if tmdb_id:
            try:
                m_details = movie_api.details(int(tmdb_id))
                if m_details:
                    poster_path = getattr(m_details, 'poster_path', None)
                    poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else f"https://placehold.co/500x750/0f172a/7eb5c4?text={requests.utils.quote(clean_title[:20])}"
                    
                    genres = getattr(m_details, 'genres', []) or []
                    genre_names = [g.get('name', '') if isinstance(g, dict) else getattr(g, 'name', '') for g in genres]
                    genre = ", ".join(filter(None, genre_names)) or "Feature Film"
                    
                    director = "Unknown"
                    if manual_director:
                        director = manual_director
                    else:
                        credits = getattr(m_details, 'credits', None)
                        if credits and isinstance(credits, dict) and 'crew' in credits:
                            for crew_member in credits['crew']:
                                if crew_member.get('job') == 'Director':
                                    director = crew_member.get('name', 'Unknown')
                                    break
                    
                    matched_title = getattr(m_details, 'title', None) or clean_title
                    vote_avg = getattr(m_details, 'vote_average', None)
                    vote_cnt = getattr(m_details, 'vote_count', None)
                    return {
                        "poster": poster,
                        "genre": genre,
                        "director": director if director != "Unknown" else (manual_director or "Unknown"),
                        "title": matched_title,
                        "rating": round(float(vote_avg), 1) if vote_avg is not None else None,
                        "vote_average": round(float(vote_avg), 1) if vote_avg is not None else None,
                        "vote_count": int(vote_cnt) if vote_cnt is not None else None,
                    }
            except Exception as ex:
                print(f"Error fetching movie by tmdb_id {tmdb_id}: {ex}")

        # 2. Search movie database first
        movie_res = movie_api.search(clean_title) or []
        norm_input = re.sub(r'[^a-z0-9]', '', clean_title.lower())
        str_year = str(year).strip() if year else ''

        # Match exact title + exact year in movies
        if str_year:
            for m_item in movie_res:
                m_title = re.sub(r'[^a-z0-9]', '', (m_item.get('title') or '').lower())
                date_str = m_item.get('release_date') or ''
                if m_title == norm_input and date_str[:4] == str_year:
                    best_match = m_item
                    break

        # Match exact title in movies
        if not best_match:
            for m_item in movie_res:
                m_title = re.sub(r'[^a-z0-9]', '', (m_item.get('title') or '').lower())
                if m_title == norm_input:
                    best_match = m_item
                    break

        # Match year in movies
        if not best_match and str_year:
            for m_item in movie_res:
                date_str = m_item.get('release_date') or ''
                if date_str[:4] == str_year:
                    best_match = m_item
                    break

        # Fallback to first movie result
        if not best_match and movie_res:
            best_match = movie_res[0]

        # Only fallback to TV search if NO movies exist at all
        if not best_match:
            tv_res = tv_api.search(clean_title) or []
            if tv_res:
                best_match = tv_res[0]
                is_tv_result = True

        if not best_match:
            return {
                "poster": f"https://placehold.co/500x750/0f172a/7eb5c4?text={requests.utils.quote(clean_title[:20])}",
                "genre": "Cinematic Pick",
                "director": manual_director or "Unknown",
                "title": title
            }
            
        poster_path = best_match.get('poster_path')
        poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else f"https://placehold.co/500x750/0f172a/7eb5c4?text={requests.utils.quote(clean_title[:20])}"
        rating = best_match.get('vote_average')
        vote_count = best_match.get('vote_count')
        if rating is not None:
            try:
                rating = round(float(rating), 1)
            except (TypeError, ValueError):
                rating = None
        if vote_count is not None:
            try:
                vote_count = int(vote_count)
            except (TypeError, ValueError):
                vote_count = None
        
        genre_ids = best_match.get('genre_ids', [])
        genre_map = tv_genres if is_tv_result else movie_genres
        genre_list = [genre_map.get(gid, "") for gid in genre_ids if genre_map.get(gid)]
        genre = ", ".join(genre_list) if genre_list else ("TV Series" if is_tv_result else "Feature Film")
        
        director = "Unknown"
        if manual_director:
            director = manual_director
        else:
            try:
                if not is_tv_result:
                    movie_details = movie_api.details(best_match['id'])
                    credits = movie_details.credits
                    if credits and 'crew' in credits:
                        for crew_member in credits['crew']:
                            if crew_member['job'] == 'Director':
                                director = crew_member['name']
                                break
                else:
                    created_by = best_match.get('created_by', [])
                    if created_by:
                        director = created_by[0].get('name', 'Unknown')
            except Exception:
                pass

        matched_name = best_match.get('name') if is_tv_result else best_match.get('title')
        return {
            "poster": poster,
            "genre": genre,
            "director": director if director != "Unknown" else (manual_director or "Unknown"),
            "title": matched_name or title,
            "rating": rating,
            "vote_average": rating,
            "vote_count": vote_count,
        }
    except Exception as e:
        print(f"Error in tmdb_service.get_movie_details: {e}")
        return {
            "poster": f"https://placehold.co/500x750/0f172a/7eb5c4?text={requests.utils.quote(title[:20])}",
            "genre": "Unknown",
            "director": manual_director or "Unknown",
            "title": title,
            "rating": None,
        }

@_cached(ttl=3600)
def get_tv_details(title, year=None, season_num=1, manual_director=None, tmdb_id=None):
    """
    Search TMDB for a TV show and extract poster, genres, and creator/director.
    If tmdb_id is provided, fetches exact TV series and season directly.
    """
    from utils import format_display_title
    try:
        clean_title = re.sub(r',?\s*season\s*\d+.*$', '', title, flags=re.IGNORECASE).strip()
        if not clean_title:
            clean_title = title

        best_match = None
        ids = None
        show_name = None

        if tmdb_id:
            ids = int(tmdb_id)
            try:
                tv_data = tv_api.details(ids)
                show_name = getattr(tv_data, 'name', None) or clean_title
            except Exception:
                pass

        if not ids:
            res = tv_api.search(clean_title) or []
            if not res:
                return {
                    "poster": "https://via.placeholder.com/200x300?text=No+Poster",
                    "genre": "Unknown",
                    "director": manual_director or "Unknown",
                    "title": format_display_title(title)
                }
            
            str_year = str(year).strip() if year else ''
            norm_input = re.sub(r'[^a-z0-9]', '', clean_title.lower())

            # Match exact title + year
            if str_year:
                for result in res:
                    t_title = re.sub(r'[^a-z0-9]', '', (result.get('name') or '').lower())
                    first_air_date = result.get('first_air_date') or ''
                    if t_title == norm_input and first_air_date[:4] == str_year:
                        best_match = result
                        break

            # Match exact title
            if not best_match:
                for result in res:
                    t_title = re.sub(r'[^a-z0-9]', '', (result.get('name') or '').lower())
                    if t_title == norm_input:
                        best_match = result
                        break

            # Match year
            if not best_match and str_year:
                for result in res:
                    first_air_date = result.get('first_air_date') or ''
                    if first_air_date[:4] == str_year:
                        best_match = result
                        break

            if not best_match:
                best_match = res[0]
                
            ids = best_match['id']
            show_name = best_match.get('name') or best_match.get('original_name') or clean_title

        show_name = format_display_title(show_name or clean_title)
        
        # Get season details for season-specific poster
        poster = None
        full_title = f"{show_name}, Season {season_num or 1}" if season_num else show_name
        try:
            show_season = season_api.details(ids, int(season_num) if season_num else 1)
            poster_path = getattr(show_season, 'poster_path', None)
            if poster_path:
                poster = f"https://image.tmdb.org/t/p/w500{poster_path}"
            s_name = getattr(show_season, 'name', None)
            if s_name:
                full_title = f"{show_name}, {s_name}"
        except Exception:
            pass

        # Fallback to series main poster
        if not poster:
            try:
                tv_data = tv_api.details(ids)
                poster_path = getattr(tv_data, 'poster_path', None)
                if poster_path:
                    poster = f"https://image.tmdb.org/t/p/w500{poster_path}"
            except Exception:
                pass

        if not poster and best_match:
            poster_path = best_match.get('poster_path')
            if poster_path:
                poster = f"https://image.tmdb.org/t/p/w500{poster_path}"

        if not poster:
            poster = f"https://placehold.co/500x750/0f172a/7eb5c4?text={requests.utils.quote(clean_title[:20])}"

        # Genres
        genre = "TV Series"
        try:
            tv_details = tv_api.details(ids)
            genres = getattr(tv_details, 'genres', []) or []
            genre_names = [g.get('name', '') if isinstance(g, dict) else getattr(g, 'name', '') for g in genres]
            if genre_names:
                genre = ", ".join(filter(None, genre_names))
        except Exception:
            if best_match:
                genre_ids = best_match.get('genre_ids', [])
                genre_list = [tv_genres.get(gid, "") for gid in genre_ids if tv_genres.get(gid)]
                if genre_list:
                    genre = ", ".join(genre_list)
        
        director = "Unknown"
        if manual_director:
            director = manual_director
        else:
            try:
                tv_details = tv_api.details(ids)
                if hasattr(tv_details, 'created_by') and tv_details.created_by:
                    director = tv_details.created_by[0]['name']
                else:
                    api_key = tmdb.api_key or os.environ.get('TMDB_API_KEY')
                    credits_url = f"https://api.themoviedb.org/3/tv/{ids}/credits?api_key={api_key}"
                    credits_response = requests.get(credits_url, timeout=5)
                    if credits_response.status_code == 200:
                        credits_data = credits_response.json()
                        for crew_member in credits_data.get('crew', []):
                            if crew_member.get('job') in ['Director', 'Creator', 'Executive Producer']:
                                director = crew_member['name']
                                break
            except Exception:
                pass
                
        return {
            "poster": poster,
            "genre": genre,
            "director": director if director != "Unknown" else (manual_director or "Unknown"),
            "title": full_title
        }
    except Exception as e:
        print(f"Error in tmdb_service.get_tv_details: {e}")
        return {
            "poster": "https://via.placeholder.com/200x300?text=Error",
            "genre": "Unknown",
            "director": manual_director or "Unknown",
            "title": format_display_title(title)
        }

@_cached(ttl=1800)
def search_titles(query, is_tv=False, limit=12):
    """
    Quick search for autocomplete suggestions.
    Returns a list of dicts with title, year, poster, and type.
    """
    try:
        res = search_api.multi({"query": query})
        results = []
        for item in res:
            media_type = item.get('media_type')
            
            # Skip if it's a person or if is_tv is strictly requested and this is a movie (or vice versa if we wanted to enforce it)
            # Actually, the user wants to search both regardless, but maybe we prioritize what they selected, 
            # or just show everything and let them pick. We will show everything.
            if media_type not in ['movie', 'tv']:
                continue

            if media_type == 'tv':
                date = item.get('first_air_date', '')
                year = date[:4] if date else ''
                title = item.get('name', '')
            else:
                date = item.get('release_date', '')
                year = date[:4] if date else ''
                title = item.get('title', '')
                
            poster_path = item.get('poster_path')
            poster = f"https://image.tmdb.org/t/p/w92{poster_path}" if poster_path else "https://via.placeholder.com/92x138?text=No+Poster"
            poster_w500 = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
            
            results.append({
                "id": item.get('id'),
                "title": title, 
                "year": year, 
                "poster": poster,
                "poster_w500": poster_w500,
                "type": media_type
            })
            
            if len(results) >= limit:
                break
                
        return results
    except Exception as e:
        print(f"Error in tmdb_service.search_titles: {e}")
        return []

@_cached(ttl=86400)
def get_director_by_id(media_id, media_type):
    """
    Fetch the director or creator for a specific media ID.
    """
    try:
        api_key = tmdb.api_key
        if media_type == 'tv':
            # Check created_by first for TV shows
            tv_details = tv_api.details(media_id)
            if hasattr(tv_details, 'created_by') and tv_details.created_by:
                return tv_details.created_by[0]['name']
                
            credits_url = f"https://api.themoviedb.org/3/tv/{media_id}/credits?api_key={api_key}"
            credits_response = requests.get(credits_url)
            if credits_response.status_code == 200:
                for crew in credits_response.json().get('crew', []):
                    if crew['job'] in ['Director', 'Creator', 'Executive Producer']:
                        return crew['name']
        else:
            credits_url = f"https://api.themoviedb.org/3/movie/{media_id}/credits?api_key={api_key}"
            credits_response = requests.get(credits_url)
            if credits_response.status_code == 200:
                for crew in credits_response.json().get('crew', []):
                    if crew['job'] == 'Director':
                        return crew['name']
    except Exception as e:
        print(f"Error in tmdb_service.get_director_by_id: {e}")
        
    return ""

@_cached(ttl=3600)
def get_full_media_details(tmdb_id=None, title=None, year=None, is_tv=False, country="IT"):
    """
    Fetch comprehensive media details from TMDB including trailer, watch providers, credits, and synopsis.
    """
    api_key = os.environ.get('TMDB_API_KEY') or tmdb.api_key
    if not api_key:
        return {"success": False, "error": "TMDB API Key missing"}

    media_type = "tv" if is_tv else "movie"
    target_id = tmdb_id

    # 1. Resolve target ID if not provided
    if not target_id and title:
        import re
        clean_title = re.sub(r',?\s*season\s*\d+.*$', '', title, flags=re.IGNORECASE).strip()
        search_results = search_titles(clean_title or title, is_tv=is_tv, limit=8)
        
        if search_results:
            best_match = None
            if year:
                for r in search_results:
                    if str(r.get("year", "")) == str(year):
                        best_match = r
                        break
            if not best_match:
                best_match = search_results[0]
                
            target_id = best_match.get("id")
            media_type = best_match.get("type", media_type)

    if not target_id:
        return {"success": False, "error": "Media not found on TMDB"}

    # 2. Fetch full details with append_to_response
    url = f"https://api.themoviedb.org/3/{media_type}/{target_id}?api_key={api_key}&append_to_response=videos,watch/providers,credits"
    try:
        resp = requests.get(url, timeout=6)
        if resp.status_code != 200:
            # If failed as movie, retry as TV or vice versa
            alt_type = "tv" if media_type == "movie" else "movie"
            alt_url = f"https://api.themoviedb.org/3/{alt_type}/{target_id}?api_key={api_key}&append_to_response=videos,watch/providers,credits"
            resp = requests.get(alt_url, timeout=6)
            if resp.status_code == 200:
                media_type = alt_type
            else:
                return {"success": False, "error": f"TMDB returned status {resp.status_code}"}

        data = resp.json()

        # Parse basic fields
        is_tv_show = (media_type == "tv")
        media_title = data.get("name") if is_tv_show else data.get("title")
        orig_title = data.get("original_name") if is_tv_show else data.get("original_title")
        release_date = data.get("first_air_date") if is_tv_show else data.get("release_date")
        rel_year = release_date[:4] if release_date else (str(year) if year else "")
        tagline = data.get("tagline") or ""
        overview = data.get("overview") or "No plot summary available."
        vote_avg = round(float(data.get("vote_average", 0)), 1) if data.get("vote_average") else None
        vote_count = int(data.get("vote_count", 0)) if data.get("vote_count") is not None else None
        
        # Runtime formatting
        runtime_mins = None
        if not is_tv_show:
            runtime_mins = data.get("runtime")
        else:
            ep_runtimes = data.get("episode_run_time") or []
            if ep_runtimes:
                runtime_mins = ep_runtimes[0]

        formatted_runtime = ""
        if runtime_mins and runtime_mins > 0:
            hrs = runtime_mins // 60
            mins = runtime_mins % 60
            formatted_runtime = f"{hrs}h {mins}m" if hrs > 0 else f"{mins}m"

        # Poster & Backdrop
        poster_path = data.get("poster_path")
        backdrop_path = data.get("backdrop_path")
        poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
        backdrop = f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else None

        # Genres
        genres = [g.get("name") for g in data.get("genres", []) if g.get("name")]

        # Director / Creator
        director = "Unknown"
        credits_data = data.get("credits", {})
        if is_tv_show:
            created_by = data.get("created_by", [])
            if created_by:
                director = created_by[0].get("name", "Unknown")
            elif credits_data.get("crew"):
                for cm in credits_data["crew"]:
                    if cm.get("job") in ["Director", "Creator", "Executive Producer"]:
                        director = cm.get("name", "Unknown")
                        break
        else:
            if credits_data.get("crew"):
                for cm in credits_data["crew"]:
                    if cm.get("job") == "Director":
                        director = cm.get("name", "Unknown")
                        break

        # Cast (Top 8)
        cast_list = []
        for cast_member in credits_data.get("cast", [])[:8]:
            p_path = cast_member.get("profile_path")
            cast_list.append({
                "name": cast_member.get("name"),
                "character": cast_member.get("character") or "Cast",
                "profile": f"https://image.tmdb.org/t/p/w185{p_path}" if p_path else None
            })

        # Videos / Trailer
        videos = data.get("videos", {}).get("results", [])
        trailer_obj = None
        # Sort trailers: prioritize Official Trailer, then Trailer, then Teaser
        scored_videos = []
        for v in videos:
            if v.get("site") == "YouTube":
                v_type = v.get("type", "")
                is_official = bool(v.get("official"))
                score = 0
                if v_type == "Trailer":
                    score = 100 + (50 if is_official else 0)
                elif v_type == "Teaser":
                    score = 50 + (25 if is_official else 0)
                elif v_type == "Clip":
                    score = 20
                scored_videos.append((score, v))

        scored_videos.sort(key=lambda x: x[0], reverse=True)
        if scored_videos:
            best_v = scored_videos[0][1]
            v_key = best_v.get("key")
            trailer_obj = {
                "key": v_key,
                "name": best_v.get("name") or "Official Trailer",
                "site": "YouTube",
                "embed_url": f"https://www.youtube-nocookie.com/embed/{v_key}?autoplay=0&rel=0"
            }

        # Watch Providers (JustWatch)
        wp_all = data.get("watch/providers", {}).get("results", {})
        available_countries = sorted(list(wp_all.keys()))
        
        target_country = (country or "IT").upper()
        wp_country_data = wp_all.get(target_country) or wp_all.get("IT") or wp_all.get("US") or {}
        
        def format_provider_list(prov_list):
            formatted = []
            for p in prov_list or []:
                logo_path = p.get("logo_path")
                formatted.append({
                    "name": p.get("provider_name"),
                    "logo": f"https://image.tmdb.org/t/p/w92{logo_path}" if logo_path else None
                })
            return formatted

        watch_providers = {
            "country": target_country,
            "link": wp_country_data.get("link") or f"https://www.themoviedb.org/{media_type}/{target_id}/watch",
            "flatrate": format_provider_list(wp_country_data.get("flatrate")),
            "rent": format_provider_list(wp_country_data.get("rent")),
            "buy": format_provider_list(wp_country_data.get("buy")),
            "free": format_provider_list(wp_country_data.get("free") or wp_country_data.get("ads")),
            "available_countries": available_countries
        }

        return {
            "success": True,
            "id": target_id,
            "media_type": media_type,
            "title": media_title or title,
            "original_title": orig_title,
            "tagline": tagline,
            "overview": overview,
            "release_date": release_date,
            "year": rel_year,
            "runtime": runtime_mins,
            "formatted_runtime": formatted_runtime,
            "vote_average": vote_avg,
            "vote_count": vote_count,
            "poster": poster,
            "backdrop": backdrop,
            "genres": genres,
            "director": director,
            "cast": cast_list,
            "trailer": trailer_obj,
            "watch_providers": watch_providers,
            "tmdb_url": f"https://www.themoviedb.org/{media_type}/{target_id}"
        }

    except Exception as e:
        print(f"Error fetching full media details: {e}")
        return {"success": False, "error": str(e)}


@_cached(ttl=7200)
def get_recommendations_for_title(title: str, year: str = None, is_tv: bool = False, limit: int = 8, use_cache: bool = True):
    """
    Fetches high-quality TMDB movie or TV series recommendations based on a seed title.
    Checks SQLite persistent cache first, writes to cache upon live fetch.
    """
    if not title:
        return []

    # 1. Check persistent SQLite cache first
    if use_cache:
        cached_recs = get_cached_recommendations(title, year, is_tv)
        if cached_recs is not None:
            return cached_recs[:limit]

    api_key = os.environ.get('TMDB_API_KEY') or tmdb.api_key
    if not api_key:
        return []

    try:
        # Clean season suffix if TV show
        clean_title = re.sub(r',?\s*season\s*\d+.*$', '', title, flags=re.IGNORECASE).strip() if is_tv else title
        if not clean_title:
            clean_title = title

        # 1. Resolve ID via search_titles
        search_res = search_titles(clean_title, is_tv=is_tv, limit=4)
        if not search_res:
            save_cached_recommendations(title, year, is_tv, [])
            return []

        target = None
        if year:
            for s in search_res:
                if str(s.get("year", "")) == str(year):
                    target = s
                    break
        if not target:
            target = search_res[0]

        target_id = target.get("id")
        if not target_id:
            save_cached_recommendations(title, year, is_tv, [])
            return []

        media_type = "tv" if is_tv else "movie"
        genres_map = tv_genres if is_tv else movie_genres

        # 2. Query TMDB Recommendations Endpoint with strict timeout
        url = f"https://api.themoviedb.org/3/{media_type}/{target_id}/recommendations?api_key={api_key}&language=en-US&page=1"
        resp = requests.get(url, timeout=2.5)
        if resp.status_code != 200:
            # Fallback to similar
            url = f"https://api.themoviedb.org/3/{media_type}/{target_id}/similar?api_key={api_key}&language=en-US&page=1"
            resp = requests.get(url, timeout=2.5)

        if resp.status_code != 200:
            save_cached_recommendations(title, year, is_tv, [])
            return []

        results = resp.json().get("results", [])
        candidates = []
        for item in results[:limit * 2]:
            p_path = item.get("poster_path")
            if not p_path:
                continue

            rel_date = item.get("first_air_date" if is_tv else "release_date") or ""
            c_year = rel_date[:4] if rel_date else ""
            c_title = item.get("name" if is_tv else "title") or item.get("original_name" if is_tv else "original_title") or ""
            
            g_ids = item.get("genre_ids", [])
            genre_list = [genres_map.get(gid, "") for gid in g_ids if genres_map.get(gid)]
            genre_str = ", ".join(genre_list) if genre_list else ("TV Series" if is_tv else "Cinema")

            vote_avg = item.get("vote_average", 0)
            vote_cnt = item.get("vote_count", 0)
            if vote_avg and float(vote_avg) < 6.0:
                continue  # Quality filter

            candidates.append({
                "title": c_title,
                "year": c_year,
                "director": "Unknown",
                "genre": genre_str,
                "poster": f"https://image.tmdb.org/t/p/w500{p_path}",
                "tv_show": 1 if is_tv else 0,
                "overview": item.get("overview") or "",
                "source": "tmdb_recommendation",
                "vote_average": round(float(vote_avg), 1) if vote_avg else None,
                "vote_count": int(vote_cnt) if vote_cnt is not None else 0
            })
            if len(candidates) >= limit:
                break

        # Save to SQLite cache
        save_cached_recommendations(title, year, is_tv, candidates)
        return candidates
    except Exception as e:
        print(f"Error in get_recommendations_for_title for '{title}': {e}")
        return []


@_cached(ttl=86400)
def get_director_filmography(director_name: str, limit: int = 6):
    """
    Fetches acclaimed titles directed by a specific auteur from TMDB.
    """
    api_key = os.environ.get('TMDB_API_KEY') or tmdb.api_key
    if not api_key or not director_name or director_name.lower() in ["unknown", "n/a", ""]:
        return []

    try:
        # 1. Search Person
        search_url = f"https://api.themoviedb.org/3/search/person?api_key={api_key}&query={requests.utils.quote(director_name)}"
        resp = requests.get(search_url, timeout=4)
        if resp.status_code != 200:
            return []

        persons = resp.json().get("results", [])
        if not persons:
            return []

        person_id = persons[0].get("id")
        if not person_id:
            return []

        # 2. Fetch Movie Credits as Director
        credits_url = f"https://api.themoviedb.org/3/person/{person_id}/movie_credits?api_key={api_key}&language=en-US"
        c_resp = requests.get(credits_url, timeout=4)
        if c_resp.status_code != 200:
            return []

        crew_items = c_resp.json().get("crew", [])
        directed_movies = [m for m in crew_items if m.get("job") == "Director" and m.get("poster_path")]
        
        # Sort by popularity or vote average
        directed_movies.sort(key=lambda x: (x.get("vote_count", 0) > 50, x.get("popularity", 0)), reverse=True)

        candidates = []
        for m in directed_movies[:limit]:
            p_path = m.get("poster_path")
            rel_date = m.get("release_date") or ""
            c_year = rel_date[:4] if rel_date else ""
            c_title = m.get("title") or m.get("original_title") or ""
            
            g_ids = m.get("genre_ids", [])
            genre_list = [movie_genres.get(gid, "") for gid in g_ids if movie_genres.get(gid)]
            genre_str = ", ".join(genre_list) if genre_list else "Cinema"

            candidates.append({
                "title": c_title,
                "year": c_year,
                "director": director_name,
                "genre": genre_str,
                "poster": f"https://image.tmdb.org/t/p/w500{p_path}",
                "tv_show": 0,
                "overview": m.get("overview") or "",
                "source": "auteur_canon",
                "vote_average": round(float(m.get("vote_average", 0)), 1) if m.get("vote_average") else None,
                "vote_count": int(m.get("vote_count", 0)) if m.get("vote_count") is not None else 0
            })

        return candidates
    except Exception as e:
        print(f"Error in get_director_filmography for '{director_name}': {e}")
        return []

