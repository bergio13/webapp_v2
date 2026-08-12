"""Analytics blueprint — director / genre / year / rating groupby views."""
import datetime

from flask import Blueprint, flash, redirect, render_template
from flask_login import current_user, login_required

from database import (
    get_directors,
    get_genres,
    get_movies_groupby_director,
    get_movies_groupby_genre,
    get_movies_groupby_rating,
    get_movies_groupby_year,
    get_ratings,
    get_user_id,
    get_years,
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


def _get_genres_list(user_id) -> list:
    """Return a sorted, deduplicated list of genre strings for *user_id*."""
    generi = get_genres(user_id)
    raw = ", ".join(g["name"] for g in generi)
    tokens = {t.strip() for t in raw.split(",") if t.strip()}
    return sorted(tokens)


# ---------------------------------------------------------------------------
# Directors
# ---------------------------------------------------------------------------

@analytics_bp.route("/directors", methods=["GET"])
@login_required
@cache.cached(timeout=300, key_prefix=make_user_cache_key)
def show_directors():
    try:
        movies = get_movies_groupby_director(current_user.id)
        directors = get_directors(current_user.id)
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
        directors = get_directors(friend["id"])
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
        final_genres = _get_genres_list(current_user.id)
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
        final_genres = _get_genres_list(friend["id"])
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
        anni = get_years(current_user.id)
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
        anni = get_years(friend["id"])
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
        ratings = get_ratings(current_user.id)
        ratings.sort(key=lambda x: str(x.get("name", "")), reverse=True)
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
        ratings = get_ratings(friend["id"])
        ratings.sort(key=lambda x: str(x.get("name", "")), reverse=True)
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
