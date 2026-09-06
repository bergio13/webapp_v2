"""Main blueprint — home, list, and API endpoints."""
import datetime
import math
import os

import requests as http_requests
from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
)
from flask_login import current_user, login_required

from concurrent.futures import ThreadPoolExecutor

from database import (
    get_monthly_movies,
    get_movies_paginated,
    get_or_create_personal_watchlist,
    get_user_id,
    get_watchlist_items,
    get_yearly_cinema_count,
    get_yearly_movie_count,
    get_yearly_movie_and_cinema_counts,
)
from extensions import cache, limiter
from services import tmdb_service
from utils import (
    dict_months,
    get_current_year_month,
    get_watched_title_year_lookup,
    make_user_cache_key,
    months,
)

main_bp = Blueprint("main", __name__)

# ---------------------------------------------------------------------------
# Landing & home
# ---------------------------------------------------------------------------

@main_bp.route("/")
def animation():
    return render_template("animation.html", session=session)


_RADAR_CACHE = {"data": [], "timestamp": 0}
_RADAR_CACHE_TTL = 21600  # 6 hours cache for movies now in theaters


def _get_cached_now_playing_radar():
    """Fetch and globally cache Now In Theaters movies from TMDb (6-hour TTL)."""
    import time
    now_ts = time.time()
    if _RADAR_CACHE["data"] and (now_ts - _RADAR_CACHE["timestamp"]) < _RADAR_CACHE_TTL:
        return _RADAR_CACHE["data"]
    
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        return _RADAR_CACHE["data"]
    try:
        url = f"https://api.themoviedb.org/3/movie/now_playing?api_key={api_key}&language=en-US&page=1"
        resp = http_requests.get(url, timeout=3.5)
        if resp.status_code == 200:
            data = resp.json()
            radar_movies = []
            for m in (data.get("results") or []):
                p = m.get("poster_path")
                b = m.get("backdrop_path")
                if p:
                    radar_movies.append({
                        "id": m.get("id"),
                        "title": m.get("title", ""),
                        "poster": f"https://image.tmdb.org/t/p/w342{p}",
                        "backdrop": f"https://image.tmdb.org/t/p/w780{b}" if b else f"https://image.tmdb.org/t/p/w342{p}",
                        "rating": round(m.get("vote_average", 0), 1),
                        "overview": m.get("overview", ""),
                        "year": (m.get("release_date") or "")[:4],
                    })
            if radar_movies:
                _RADAR_CACHE["data"] = radar_movies
                _RADAR_CACHE["timestamp"] = now_ts
                return radar_movies
    except Exception as e:
        logger_e = current_app.logger if current_app else None
        if logger_e:
            logger_e.debug(f"Notice fetching radar movies from TMDb: {e}")
    return _RADAR_CACHE["data"]


def _get_home_page_data(user_id):
    """
    Fetch all user-specific home data concurrently and cache in SimpleCache (300s TTL).
    Invalidated immediately when movies/watchlists change via _clear_user_cache().
    """
    cache_key = f"home_data_{user_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    now = datetime.datetime.now()
    current_year, month_now = now.year, now.month
    month_name = dict_months.get(month_now, now.strftime("%B")).upper()

    def _fetch_month():
        return get_monthly_movies(user_id, month_now)

    def _fetch_watchlist():
        try:
            wl = get_or_create_personal_watchlist(user_id)
            if wl:
                return get_watchlist_items(wl['id'])
        except Exception:
            pass
        return []

    def _fetch_year_counts():
        try:
            return get_yearly_movie_and_cinema_counts(user_id, current_year)
        except Exception:
            return 0, 0

    # Run Supabase queries in parallel on cold load
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_month = pool.submit(_fetch_month)
        f_wl = pool.submit(_fetch_watchlist)
        f_year = pool.submit(_fetch_year_counts)

        movies = f_month.result()
        watchlist_items = f_wl.result()
        yearly_count, yearly_cinema_count = f_year.result()

    def _get_sentiment_val(r):
        try:
            v = float(r)
            return math.ceil(v / 2.0) if v > 5 else v
        except (TypeError, ValueError):
            return 3.0

    total_this_month = len(movies)
    avg_rating = (
        round(sum(_get_sentiment_val(m["rating"]) for m in movies) / total_this_month, 1)
        if total_this_month > 0 else 0
    )
    cinema_trips = sum(1 for m in movies if int(m.get("cinema", 0)) == 1)

    yearly_count = yearly_count or total_this_month
    yearly_cinema_count = yearly_cinema_count or cinema_trips

    current_week = now.isocalendar()[1]
    yearly_target = 52
    cinema_target = 12
    pace_diff = yearly_count - current_week

    # Fetch cached radar movies (0.0ms if warm)
    radar_movies = _get_cached_now_playing_radar()

    # Determine Contextual Default Mode
    weekday = now.weekday()
    if weekday in (4, 5) and watchlist_items:
        default_mode = "watchlist"
    elif weekday in (2, 3) and radar_movies:
        default_mode = "radar"
    elif watchlist_items:
        default_mode = "watchlist"
    elif radar_movies:
        default_mode = "radar"
    else:
        default_mode = "goal"

    # Top-rated titles
    top_movies = []
    if movies:
        max_rating = max(_get_sentiment_val(m["rating"]) for m in movies)
        if max_rating >= 4.0:
            top_movies = [m for m in movies if _get_sentiment_val(m["rating"]) == max_rating]
    highest_rated = top_movies[0] if top_movies else None

    hero_data = {
        "default_mode": default_mode,
        "weekday": weekday,
        "month_name": month_name,
        "watchlist_items": watchlist_items,
        "radar_movies": radar_movies,
        "yearly_count": yearly_count,
        "yearly_target": yearly_target,
        "yearly_pct": min(100, int((yearly_count / float(yearly_target)) * 100)) if yearly_count > 0 else 0,
        "current_week": current_week,
        "pace_diff": pace_diff,
        "yearly_cinema_count": yearly_cinema_count,
        "cinema_target": cinema_target,
        "cinema_pct": min(100, int((yearly_cinema_count / float(cinema_target)) * 100)) if yearly_cinema_count > 0 else 0,
    }

    result = (movies, total_this_month, avg_rating, cinema_trips, highest_rated, top_movies, hero_data)
    cache.set(cache_key, result, timeout=300)
    return result


@main_bp.route("/home")
def hello():
    if not current_user.is_authenticated:
        return render_template("home.html", movies=[], total=0, avg_rating=0, cinema=0, highest_rated=None, top_movies=[], hero_data={})
    try:
        movies, total_this_month, avg_rating, cinema_trips, highest_rated, top_movies, hero_data = _get_home_page_data(current_user.id)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load home monthly movies")
        movies, total_this_month, avg_rating, cinema_trips, highest_rated, top_movies, hero_data = [], 0, 0, 0, None, [], {
            "default_mode": "watchlist", "watchlist_items": [], "radar_movies": [], "yearly_count": 0, "yearly_target": 52, "yearly_pct": 0, "yearly_cinema_count": 0, "cinema_target": 12, "cinema_pct": 0, "current_week": 1, "pace_diff": 0, "month_name": "MONTH"
        }
        flash("Something went wrong, please refresh the page", category="error")

    return render_template(
        "home.html",
        session=session,
        movies=movies,
        total=total_this_month,
        avg_rating=avg_rating,
        cinema=cinema_trips,
        highest_rated=highest_rated,
        top_movies=top_movies,
        hero_data=hero_data,
    )


# ---------------------------------------------------------------------------
# Movie list views
# ---------------------------------------------------------------------------

@main_bp.route("/lista")
@login_required
def lista():
    year_now, _ = get_current_year_month()
    try:
        movies, total_count = get_movies_paginated(current_user.id, page=1, limit=50)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load user list")
        movies = []
        total_count = 0
        flash("Something went wrong, please refresh the page", category="error")
    return render_template(
        "lista1.html", movies=movies, total_count=total_count, months=months, year_now=year_now, dict_months=dict_months
    )


@main_bp.route("/list/<username>")
def lista_user(username):
    user = get_user_id(username)
    if not user:
        from flask import current_app
        current_app.logger.warning("Friend list requested for unknown user: %s", username)
        flash("User not found", category="error")
        return redirect("/friends" if current_user.is_authenticated else "/")

    year_now, _ = get_current_year_month()
    try:
        movies, total_count = get_movies_paginated(user[0]["id"], page=1, limit=50)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load friend list for %s", username)
        movies = []
        total_count = 0
        flash("Something went wrong, please refresh the page", category="error")
    return render_template(
        "_lista1.html",
        movies=movies, total_count=total_count, months=months, year_now=year_now,
        dict_months=dict_months, username=username,
    )


# ---------------------------------------------------------------------------
# JSON / API endpoints
# ---------------------------------------------------------------------------

@main_bp.route("/api/movies")
@login_required
def api_movies():
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 50, type=int)
    username = request.args.get("username")
    user_id = current_user.id

    if username:
        user_data = get_user_id(username)
        if user_data:
            user_id = user_data[0]["id"]
        else:
            return jsonify({"movies": [], "has_next": False, "total_count": 0}), 404

    search = request.args.get("search")
    year = request.args.get("year", type=int)
    rating = request.args.get("rating", type=int)
    media_type = request.args.get("media_type")
    cinema = request.args.get("cinema", type=int)
    rewatch = request.args.get("rewatch", type=int)
    sort_by = request.args.get("sort_by", "v_date")
    order = request.args.get("order", "desc")
    desc = (order.lower() != "asc")

    valid_sorts = {"v_date", "rating", "p_year", "movie"}
    if sort_by not in valid_sorts:
        sort_by = "v_date"

    movies, total_count = get_movies_paginated(
        user_id,
        order_column=sort_by,
        desc=desc,
        page=page,
        limit=limit,
        search=search,
        rating=rating,
        media_type=media_type,
        cinema=cinema,
        rewatch=rewatch,
        year=year,
    )

    serialized = []
    for m in movies:
        m_copy = dict(m)
        if hasattr(m["v_date"], "isoformat"):
            m_copy["v_date"] = m["v_date"].isoformat()
        serialized.append(m_copy)

    return jsonify({
        "movies": serialized,
        "has_next": (page * limit) < total_count,
        "total_count": total_count,
    })


@main_bp.route("/api/watched_lookup")
@login_required
@cache.cached(timeout=300, key_prefix=make_user_cache_key)
def api_watched_lookup():
    watched_set = get_watched_title_year_lookup(current_user.id)
    return jsonify([{"title": t, "year": y} for t, y in watched_set])


@main_bp.route("/api/movie_details")
@login_required
@limiter.limit("3000 per hour")
def api_movie_details():
    title = (request.args.get("title") or "").strip()
    year_raw = (request.args.get("year") or "").strip()
    manual_director = (request.args.get("director") or "").strip() or None

    if not title:
        return jsonify({"error": "title is required"}), 400

    try:
        year = int(year_raw) if year_raw else None
    except ValueError:
        year = None

    details = tmdb_service.get_movie_details(title, year, manual_director)
    return jsonify(details or {
        "poster": "https://via.placeholder.com/200x300?text=No+Poster",
        "genre": "Unknown",
        "director": manual_director or "Unknown",
        "title": title,
        "rating": None,
    })


@main_bp.route("/api/now-playing")
@login_required
@cache.cached(timeout=3600)
def api_now_playing():
    """Return up to 8 movies currently playing in cinemas (TMDB now_playing)."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        return jsonify({"movies": []})
    try:
        url = (
            f"https://api.themoviedb.org/3/movie/now_playing"
            f"?api_key={api_key}&language=en-US&page=1"
        )
        resp = http_requests.get(url, timeout=5)
        data = resp.json()
        movies = []
        for m in (data.get("results") or []):
            poster = m.get("poster_path")
            if poster:
                movies.append({
                    "id": m.get("id"),
                    "title": m.get("title", ""),
                    "poster": f"https://image.tmdb.org/t/p/w185{poster}",
                    "rating": round(m.get("vote_average", 0), 1),
                    "year": (m.get("release_date") or "")[:4],
                })
        return jsonify({"movies": movies})
    except Exception:
        return jsonify({"movies": []})


@main_bp.route("/api/upcoming")
@login_required
@cache.cached(timeout=3600)
def api_upcoming():
    """Return up to 8 movies upcoming in cinemas (TMDB upcoming)."""
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        return jsonify({"movies": []})
    try:
        import datetime
        today = datetime.datetime.today()
        today_str = today.strftime("%Y-%m-%d")
        next_year_str = (today + datetime.timedelta(days=365)).strftime("%Y-%m-%d")
        
        url = (
            f"https://api.themoviedb.org/3/discover/movie"
            f"?api_key={api_key}&language=en-US&sort_by=popularity.desc"
            f"&primary_release_date.gte={today_str}&primary_release_date.lte={next_year_str}&page=1"
        )
        resp = http_requests.get(url, timeout=5)
        data = resp.json()
        movies = []
        for m in (data.get("results") or []):
            poster = m.get("poster_path")
            if poster:
                movies.append({
                    "id": m.get("id"),
                    "title": m.get("title", ""),
                    "poster": f"https://image.tmdb.org/t/p/w185{poster}",
                    "rating": round(m.get("vote_average", 0), 1),
                    "year": (m.get("release_date") or "")[:4],
                })
            if len(movies) >= 8:
                break
        return jsonify({"movies": movies})
    except Exception:
        return jsonify({"movies": []})


@main_bp.route("/tmdb_redirect")
def tmdb_redirect():
    title = request.args.get("title")
    is_tv_str = str(request.args.get("tv", "")).strip().lower()
    is_tv = is_tv_str in ["1", "true", "t", "yes"]
    
    if not title:
        return redirect("https://www.themoviedb.org/")
        
    search_title = title
    if is_tv:
        import re
        # Remove suffixes like " Season 1", " (Season 2)", " - Season 3", " S4"
        search_title = re.sub(r'(?i)[\s\-\(]*(season\s*\d+|s\d+)[\)]*$', '', search_title).strip()
        
    try:
        results = tmdb_service.search_titles(search_title, is_tv)
        if results:
            match = results[0]
            media_type = match.get("type", "tv" if is_tv else "movie")
            tmdb_id = match.get("id")
            if tmdb_id:
                return redirect(f"https://www.themoviedb.org/{media_type}/{tmdb_id}")
    except Exception:
        pass
        
    import urllib.parse
    safe_title = urllib.parse.quote(search_title)
    return redirect(f"https://www.themoviedb.org/search?query={safe_title}")


@main_bp.route("/api/media_details")
def api_media_details():
    import re
    import copy
    title = request.args.get("title")
    year = request.args.get("year")
    tmdb_id = request.args.get("tmdb_id")
    season = request.args.get("season")
    is_tv_str = str(request.args.get("tv") or request.args.get("is_tv") or "").strip().lower()
    is_tv = is_tv_str in ["1", "true", "t", "yes"]
    country = request.args.get("country", "IT").strip().upper()
    
    if not title and not tmdb_id:
        return jsonify({"success": False, "error": "Missing title or tmdb_id parameter"}), 400
        
    try:
        clean_title = title
        if is_tv and not season and title:
            from services.catalog_service import resolve_tv_season_number
            inferred = resolve_tv_season_number(title, tmdb_id=tmdb_id)
            if inferred and inferred > 1:
                season = inferred
            elif re.search(r'(?i)\b(?:season|series|volume|vol|part|bk|book|s)\s*1\b', title):
                season = 1
            clean_title = re.sub(r',?\s*(?:season|series|volume|vol|part|bk|book|the final season|final season)\s*\d*.*$', '', title, flags=re.IGNORECASE).strip()

        details = tmdb_service.get_full_media_details(
            tmdb_id=tmdb_id,
            title=clean_title or title,
            year=year,
            is_tv=is_tv,
            country=country
        )

        details = copy.deepcopy(details)

        # Augment with TV season-specific canonical data if viewing a season
        if details.get("success") and is_tv and details.get("media_type") != "movie":
            target_tmdb_id = details.get("tmdb_id") or details.get("id") or tmdb_id
            if target_tmdb_id:
                details["tmdb_id"] = int(target_tmdb_id)
            if not season and target_tmdb_id and title:
                from services.catalog_service import resolve_tv_season_number
                inferred = resolve_tv_season_number(title, tmdb_id=int(target_tmdb_id))
                if inferred and (inferred > 1 or re.search(r'(?i)\b(?:season|series|volume|vol|part|bk|book|s)\s*1\b', title)):
                    season = inferred

            if season and target_tmdb_id:
                try:
                    s_int = int(season)
                    from services.catalog_service import (
                        get_tv_season_catalog_item, 
                        fetch_and_enrich_tv_season, 
                        upsert_tv_season_catalog_item
                    )
                    season_item = get_tv_season_catalog_item(int(target_tmdb_id), s_int)
                    if not season_item:
                        season_item = fetch_and_enrich_tv_season(int(target_tmdb_id), s_int, show_title=details.get("title") or title)
                        if season_item:
                            upsert_tv_season_catalog_item(season_item, compute_embedding=True)
                    
                    if season_item:
                        details["season_number"] = s_int
                        s_name = season_item.get("season_name") or f"Season {s_int}"
                        details["season_name"] = s_name
                        raw_title = details.get("title") or clean_title or title
                        # Strip any pre-existing season suffixes from raw_title so season strings never accumulate
                        clean_show_title = re.sub(
                            r',?\s*-\s*(?:season|series|volume|vol|part|the final season|final season)\s*\d*.*$', 
                            '', 
                            raw_title, 
                            flags=re.IGNORECASE
                        ).strip()
                        clean_show_title = re.sub(
                            r',?\s*(?:season|series|volume|vol|part|the final season|final season)\s*\d*.*$', 
                            '', 
                            clean_show_title, 
                            flags=re.IGNORECASE
                        ).strip()
                        if s_name.lower() in clean_show_title.lower():
                            details["title"] = clean_show_title
                        else:
                            details["title"] = f"{clean_show_title} - {s_name}"
                        if season_item.get("overview"):
                            details["overview"] = season_item["overview"]
                        if season_item.get("poster") and "placeholder" not in season_item["poster"]:
                            details["poster"] = season_item["poster"]
                        if season_item.get("year"):
                            details["year"] = str(season_item["year"])
                        if season_item.get("director"):
                            details["director"] = season_item["director"]
                        if season_item.get("creator") and not details.get("creator"):
                            details["creator"] = season_item["creator"]
                        if season_item.get("episode_count"):
                            details["runtime"] = f"{season_item['episode_count']} Episodes"
                        if season_item.get("lead_actors"):
                            season_cast = [a.strip() for a in season_item["lead_actors"].split(",") if a.strip()]
                            if season_cast:
                                details["cast"] = [{"name": actor, "character": f"Season {s_int} Cast", "profile": None} for actor in season_cast]
                except Exception as se:
                    current_app.logger.debug(f"Notice augmenting media details with season info: {se}")
        
        # Add user library status if authenticated
        if details.get("success") and current_user.is_authenticated:
            try:
                watched_set = get_watched_title_year_lookup(current_user.id)
                m_title = (clean_title or details.get("title") or title or "").strip().lower()
                m_year = str(details.get("year") or year or "").strip()
                
                is_watched = any(
                    wt.strip().lower() == m_title and (not m_year or not wy or str(wy) == m_year)
                    for wt, wy in watched_set
                )
                details["user_status"] = {
                    "is_watched": is_watched,
                    "is_authenticated": True
                }
            except Exception:
                details["user_status"] = {"is_watched": False, "is_authenticated": True}
        else:
            details["user_status"] = {"is_watched": False, "is_authenticated": bool(current_user.is_authenticated)}
            
        return jsonify(details)
    except Exception as e:
        current_app.logger.exception("Error in /api/media_details")
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# PWA Endpoints
# ---------------------------------------------------------------------------

@main_bp.route("/manifest.json")
def manifest():
    """Serve the Web App Manifest."""
    response = make_response(
        send_from_directory(
            os.path.join(current_app.root_path, "static"),
            "manifest.json",
            mimetype="application/manifest+json",
        )
    )
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@main_bp.route("/sw.js")
def service_worker():
    """Serve the Service Worker with root scope permissions."""
    response = make_response(
        send_from_directory(
            os.path.join(current_app.root_path, "static", "js"),
            "sw.js",
            mimetype="application/javascript",
        )
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@main_bp.route("/offline")
def offline():
    """Render the offline fallback view."""
    return render_template("offline.html")



