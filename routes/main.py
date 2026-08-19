"""Main blueprint — home, list, and API endpoints."""
import datetime
import math
import os

import requests as http_requests
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session
from flask_login import current_user, login_required

from database import get_monthly_movies, get_movies_paginated, get_user_id
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


@main_bp.route("/home")
def hello():
    if not current_user.is_authenticated:
        return render_template("home.html", movies=[], total=0, avg_rating=0, cinema=0, highest_rated=None)
    try:
        _, month_now = get_current_year_month()
        movies = get_monthly_movies(current_user.id, month_now)
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
        cinema_trips = sum(1 for m in movies if int(m["cinema"]) == 1)
        highest_rated = max(movies, key=lambda m: _get_sentiment_val(m["rating"])) if movies else None
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load home monthly movies")
        movies, total_this_month, avg_rating, cinema_trips, highest_rated = [], 0, 0, 0, None
        flash("Something went wrong, please refresh the page", category="error")

    return render_template(
        "home.html",
        session=session,
        movies=movies,
        total=total_this_month,
        avg_rating=avg_rating,
        cinema=cinema_trips,
        highest_rated=highest_rated,
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
        for m in (data.get("results") or [])[:8]:
            poster = m.get("poster_path")
            if poster:
                movies.append({
                    "id": m.get("id"),
                    "title": m.get("title", ""),
                    "poster": f"https://image.tmdb.org/t/p/w185{poster}",
                    "rating": round(m.get("vote_average", 0), 1),
                })
        return jsonify({"movies": movies})
    except Exception:
        return jsonify({"movies": []})


@main_bp.route("/api/upcoming")
@login_required
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

