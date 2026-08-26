"""Analytics blueprint — director / genre / year / rating groupby views."""
import datetime

from flask import Blueprint, flash, redirect, render_template
from flask_login import current_user, login_required

from database import (
    get_movies_groupby_director,
    get_movies_groupby_genre,
    get_movies_groupby_rating,
    get_movies_groupby_year,
    get_user_id,
)
from extensions import cache
from utils import make_user_cache_key

analytics_bp = Blueprint("analytics", __name__)

_NOW = lambda: datetime.date.today().year  # noqa: E731


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_friend(username: str):
    """Return the user dict for *username* or None if not found."""
    user = get_user_id(username)
    return user[0] if user else None


def _extract_genres_from_movies(movies: list) -> list:
    """Return a sorted, deduplicated list of genre strings from movies."""
    tokens = set()
    for m in movies:
        raw = str(m.get("genre") or "")
        for t in raw.split(","):
            cleaned = t.strip()
            if cleaned and cleaned.lower() != "unknown":
                tokens.add(cleaned)
    return sorted(tokens)


def _extract_directors_from_movies(movies: list) -> list:
    """Return distinct directors list from movies."""
    names = {m.get("director") for m in movies if m.get("director") and str(m.get("director")).strip() != "Unknown"}
    return [{"name": d} for d in sorted(names)]


def _extract_years_from_movies(movies: list) -> list:
    """Return distinct years list from movies sorted descending."""
    years = {m.get("p_year") for m in movies if m.get("p_year")}
    sorted_years = sorted(years, key=lambda x: int(x) if str(x).isdigit() else 0, reverse=True)
    return [{"name": y} for y in sorted_years]


def _extract_ratings_from_movies(movies: list) -> list:
    """Return distinct ratings list from movies sorted descending."""
    ratings = {m.get("rating") for m in movies if m.get("rating") is not None}
    sorted_ratings = sorted(ratings, key=lambda x: float(x) if str(x).replace(".", "", 1).isdigit() else 0, reverse=True)
    return [{"name": r} for r in sorted_ratings]


# ---------------------------------------------------------------------------
# Directors
# ---------------------------------------------------------------------------

@analytics_bp.route("/directors", methods=["GET"])
@login_required
@cache.cached(timeout=300, key_prefix=make_user_cache_key)
def show_directors():
    try:
        movies = get_movies_groupby_director(current_user.id)
        directors = _extract_directors_from_movies(movies)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load directors page")
        movies, directors = [], []
        flash("Something went wrong, please refresh the page", category="error")
    return render_template(
        "_analytics_table.html",
        groupby="director", items=directors, movies=movies,
        allow_delete=True, now=_NOW(),
    )


@analytics_bp.route("/directors/<username>", methods=["GET"])
@login_required
def show_directors_friends(username):
    friend = _resolve_friend(username)
    if not friend:
        from flask import current_app
        current_app.logger.warning("Friend directors requested for unknown user: %s", username)
        flash("User not found", category="error")
        return redirect("/friends")
    try:
        movies = get_movies_groupby_director(friend["id"])
        directors = _extract_directors_from_movies(movies)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load friend directors page for %s", username)
        movies, directors = [], []
        flash("Something went wrong, please refresh the page", category="error")
    return render_template(
        "_analytics_table.html",
        groupby="director", items=directors, movies=movies,
        allow_delete=False, username=username, now=_NOW(),
    )


# ---------------------------------------------------------------------------
# Genres
# ---------------------------------------------------------------------------

@analytics_bp.route("/genres", methods=["GET"])
@login_required
@cache.cached(timeout=300, key_prefix=make_user_cache_key)
def show_genres():
    try:
        movies = get_movies_groupby_genre(current_user.id)
        final_genres = _extract_genres_from_movies(movies)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load genres page")
        movies, final_genres = [], []
        flash("Something went wrong, please refresh the page", category="error")
    return render_template(
        "_analytics_table.html",
        groupby="genre", items=final_genres, movies=movies,
        allow_delete=True, now=_NOW(),
    )


@analytics_bp.route("/genres/<username>", methods=["GET"])
@login_required
def show_genres_friends(username):
    friend = _resolve_friend(username)
    if not friend:
        from flask import current_app
        current_app.logger.warning("Friend genres requested for unknown user: %s", username)
        flash("User not found", category="error")
        return redirect("/friends")
    try:
        movies = get_movies_groupby_genre(friend["id"])
        final_genres = _extract_genres_from_movies(movies)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load friend genres page for %s", username)
        movies, final_genres = [], []
        flash("Something went wrong, please refresh the page", category="error")
    return render_template(
        "_analytics_table.html",
        groupby="genre", items=final_genres, movies=movies,
        allow_delete=False, username=username, now=_NOW(),
    )


# ---------------------------------------------------------------------------
# Years
# ---------------------------------------------------------------------------

@analytics_bp.route("/years", methods=["GET"])
@login_required
@cache.cached(timeout=300, key_prefix=make_user_cache_key)
def show_years():
    try:
        movies = get_movies_groupby_year(current_user.id)
        anni = _extract_years_from_movies(movies)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load years page")
        movies, anni = [], []
        flash("Something went wrong, please refresh the page", category="error")
    return render_template(
        "_analytics_table.html",
        groupby="year", items=anni, movies=movies,
        allow_delete=True, now=_NOW(),
    )


@analytics_bp.route("/years/<username>", methods=["GET"])
@login_required
def show_years_friends(username):
    friend = _resolve_friend(username)
    if not friend:
        from flask import current_app
        current_app.logger.warning("Friend years requested for unknown user: %s", username)
        flash("User not found", category="error")
        return redirect("/friends")
    try:
        movies = get_movies_groupby_year(friend["id"])
        anni = _extract_years_from_movies(movies)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load friend years page for %s", username)
        movies, anni = [], []
        flash("Something went wrong, please refresh the page", category="error")
    return render_template(
        "_analytics_table.html",
        groupby="year", items=anni, movies=movies,
        allow_delete=False, username=username, now=_NOW(),
    )


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------

@analytics_bp.route("/ratings", methods=["GET"])
@login_required
@cache.cached(timeout=300, key_prefix=make_user_cache_key)
def show_ratings():
    try:
        movies = get_movies_groupby_rating(current_user.id)
        ratings = _extract_ratings_from_movies(movies)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load ratings page")
        movies, ratings = [], []
        flash("Something went wrong, please refresh the page", category="error")
    return render_template(
        "_analytics_table.html",
        groupby="rating", items=ratings, movies=movies,
        allow_delete=True, now=_NOW(),
    )


@analytics_bp.route("/ratings/<username>", methods=["GET"])
@login_required
def show_ratings_friends(username):
    friend = _resolve_friend(username)
    if not friend:
        from flask import current_app
        current_app.logger.warning("Friend ratings requested for unknown user: %s", username)
        flash("User not found", category="error")
        return redirect("/friends")
    try:
        movies = get_movies_groupby_rating(friend["id"])
        ratings = _extract_ratings_from_movies(movies)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load friend ratings page for %s", username)
        movies, ratings = [], []
        flash("Something went wrong, please refresh the page", category="error")
    return render_template(
        "_analytics_table.html",
        groupby="rating", items=ratings, movies=movies,
        allow_delete=False, username=username, now=_NOW(),
    )
