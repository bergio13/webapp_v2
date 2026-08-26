import os
import time
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
def get_movie_details(title, year, manual_director=None):
    """
    Search TMDB for a movie or TV show, extracting poster, genres, and director.
    Handles season title stripping (e.g. 'Reacher, Season 1' -> 'Reacher') and falls back to TV API.
    """
    import re
    clean_title = re.sub(r',?\s*season\s*\d+.*$', '', title, flags=re.IGNORECASE).strip()
    if not clean_title:
        clean_title = title

    try:
        # 1. Check TV search if title matches known show patterns or media hints
        movie_res = movie_api.search(clean_title) or []
        tv_res = tv_api.search(clean_title) or []

        # Find exact title match in TV vs Movie
        norm_input = re.sub(r'[^a-z0-9]', '', clean_title.lower())
        
        best_match = None
        is_tv_result = False

        # Check for exact title match in TV first if title is short/known TV title
        for t_item in tv_res:
            t_name = re.sub(r'[^a-z0-9]', '', (t_item.get('name') or '').lower())
            if t_name == norm_input:
                best_match = t_item
                is_tv_result = True
                break

        # Check exact title match in Movies if not found in TV
        if not best_match:
            for m_item in movie_res:
                m_title = re.sub(r'[^a-z0-9]', '', (m_item.get('title') or '').lower())
                if m_title == norm_input:
                    best_match = m_item
                    is_tv_result = False
                    break

        # Fallback to year matching
        if not best_match:
            for m_item in movie_res:
                date_str = m_item.get('release_date') or ''
                if date_str and str(year) and date_str[:4] == str(year):
                    best_match = m_item
                    is_tv_result = False
                    break

        if not best_match:
            for t_item in tv_res:
                date_str = t_item.get('first_air_date') or ''
                if date_str and str(year) and date_str[:4] == str(year):
                    best_match = t_item
                    is_tv_result = True
                    break

        if not best_match:
            if movie_res:
                best_match = movie_res[0]
                is_tv_result = False
            elif tv_res:
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
        if rating is not None:
            try:
                rating = round(float(rating), 1)
            except (TypeError, ValueError):
                rating = None
        
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
def get_tv_details(title, year, season_num, manual_director=None):
    """
    Search TMDB for a TV show and extract poster, genres, and creator/director.
    """
    from utils import format_display_title
    try:
        clean_title = re.sub(r',?\s*season\s*\d+.*$', '', title, flags=re.IGNORECASE).strip()
        res = tv_api.search(clean_title or title)
        if not res:
            return {
                "poster": "https://via.placeholder.com/200x300?text=No+Poster",
                "genre": "Unknown",
                "director": manual_director or "Unknown",
                "title": format_display_title(title)
            }
        
        # Try to find exact year match
        best_match = None
        for result in res:
            first_air_date = result.get('first_air_date')
            if first_air_date and first_air_date[:4] == str(year):
                best_match = result
                break
        
        # Fallback to first result if no year match
        if not best_match:
            best_match = res[0]
            
        ids = best_match['id']
        show_name = best_match.get('name') or best_match.get('original_name') or title
        show_name = format_display_title(show_name)
        
        # Get season details for poster
        try:
            show_season = season_api.details(ids, season_num or 1)
            poster_path = show_season.poster_path
            poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else f"https://image.tmdb.org/t/p/w500{best_match.get('poster_path') or ''}"
            season_name = show_season.name if (hasattr(show_season, 'name') and show_season.name) else f"Season {season_num or 1}"
            full_title = f"{show_name}, {season_name}"
        except Exception:
            poster_path = best_match.get('poster_path')
            poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "https://via.placeholder.com/200x300?text=No+Poster"
            full_title = f"{show_name}, Season {season_num or 1}" if season_num else show_name
            
        genre_ids = best_match.get('genre_ids', [])
        genre_list = [tv_genres.get(gid, "") for gid in genre_ids if tv_genres.get(gid)]
        genre = ", ".join(genre_list) if genre_list else "Unknown"
        
        director = "Unknown"
        if manual_director:
            director = manual_director
        else:
            try:
                tv_details = tv_api.details(ids)
                if hasattr(tv_details, 'created_by') and tv_details.created_by:
                    director = tv_details.created_by[0]['name']
                else:
                    # Try to get credits for TV show
                    try:
                        api_key = tmdb.api_key
                        credits_url = f"https://api.themoviedb.org/3/tv/{ids}/credits?api_key={api_key}"
                        credits_response = requests.get(credits_url)
                        if credits_response.status_code == 200:
                            credits_data = credits_response.json()
                            for crew_member in credits_data.get('crew', []):
                                if crew_member['job'] in ['Director', 'Creator', 'Executive Producer']:
                                    director = crew_member['name']
                                    break
                    except Exception:
                        pass
                    
                    if not director or director == "Unknown":
                        director = "Various Directors"
            except Exception:
                director = "Unknown"
                
        return {
            "poster": poster,
            "genre": genre,
            "director": director,
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
            
            results.append({
                "id": item.get('id'),
                "title": title, 
                "year": year, 
                "poster": poster,
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
                "embed_url": f"https://www.youtube-nocookie.com/embed/{v_key}?autoplay=1&rel=0"
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

