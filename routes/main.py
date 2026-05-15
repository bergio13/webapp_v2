"""Main blueprint — home, list, and API endpoints."""
import datetime
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
        total_this_month = len(movies)
        avg_rating = (
            round(sum(float(m["rating"]) for m in movies) / total_this_month, 1)
            if total_this_month > 0 else 0
        )
        cinema_trips = sum(1 for m in movies if int(m["cinema"]) == 1)
        highest_rated = max(movies, key=lambda m: float(m["rating"])) if movies else None
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
@cache.cached(timeout=120, key_prefix=make_user_cache_key)
def lista():
    year_now, _ = get_current_year_month()
    try:
        movies, _ = get_movies_paginated(current_user.id, page=1, limit=50)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load user list")
        movies = []
        flash("Something went wrong, please refresh the page", category="error")
    return render_template(
        "lista1.html", movies=movies, months=months, year_now=year_now, dict_months=dict_months
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
        movies, _ = get_movies_paginated(user[0]["id"], page=1, limit=50)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load friend list for %s", username)
        movies = []
        flash("Something went wrong, please refresh the page", category="error")
    return render_template(
        "_lista1.html",
        movies=movies, months=months, year_now=year_now,
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
            return jsonify({"movies": [], "has_next": False}), 404

    search = request.args.get("search")
    movies, total_count = get_movies_paginated(user_id, page=page, limit=limit, search=search)

    serialized = []
    for m in movies:
        m_copy = dict(m)
        if hasattr(m["v_date"], "isoformat"):
            m_copy["v_date"] = m["v_date"].isoformat()
        serialized.append(m_copy)

    return jsonify({"movies": serialized, "has_next": (page * limit) < total_count})


@main_bp.route("/api/watched_lookup")
@login_required
def api_watched_lookup():
    watched_set = get_watched_title_year_lookup(current_user.id)
    return jsonify([{"title": t, "year": y} for t, y in watched_set])


@main_bp.route("/api/movie_details")
@login_required
@limiter.limit("300 per hour")
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
        url = (
            f"https://api.themoviedb.org/3/movie/upcoming"
            f"?api_key={api_key}&language=en-US&page=1"
        )
        resp = http_requests.get(url, timeout=5)
        data = resp.json()
        movies = []
        import datetime
        today = datetime.datetime.today().strftime('%Y-%m-%d')
        for m in (data.get("results") or []):
            release_date = m.get("release_date", "")
            if release_date and release_date > today:
                poster = m.get("poster_path")
                if poster:
                    movies.append({
                        "title": m.get("title", ""),
                        "poster": f"https://image.tmdb.org/t/p/w185{poster}",
                        "rating": round(m.get("vote_average", 0), 1),
                    })
            if len(movies) >= 8:
                break
        return jsonify({"movies": movies})
    except Exception:
        return jsonify({"movies": []})

