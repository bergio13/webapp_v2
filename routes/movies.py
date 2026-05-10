"""Movies blueprint — add, edit, and remove movie entries."""
import os

from flask import Blueprint, flash, jsonify, redirect, render_template, request
from flask_login import current_user, login_required

from database import insert_movies, remove_movie_by_id, update_movie
from extensions import cache, limiter
from services import tmdb_service
from utils import clean_and_capitalize_name, clean_and_format

movies_bp = Blueprint("movies", __name__)

_NO_POSTER = "https://via.placeholder.com/200x300?text=No+Poster"


def _clear_user_cache():
    """Invalidate all cached data (SimpleCache — clears everything)."""
    cache.clear()


# ---------------------------------------------------------------------------
# Add
# ---------------------------------------------------------------------------

@movies_bp.route("/add_movie", methods=["GET", "POST"])
@login_required
@limiter.limit("100 per hour")
def add_movie():
    if request.method == "POST":
        try:
            title = clean_and_format(request.form["title"])
            manual_director = request.form["director"].strip()
            year = request.form["year"]
            date = request.form["date"]
            rating = request.form["rating"]
            rewatch = request.form["rewatch"]
            tv_show = request.form["tv"]
            which_season = request.form["season"]
            cinema = request.form["cinema"]

            if manual_director:
                manual_director = clean_and_capitalize_name(manual_director)

            if tv_show == "1":
                try:
                    season_num = int(which_season) if which_season else 1
                except ValueError:
                    season_num = 1
                details = tmdb_service.get_tv_details(title, year, season_num, manual_director)
            else:
                details = tmdb_service.get_movie_details(title, year, manual_director)

            if details:
                poster = details["poster"]
                genre = details["genre"]
                director = details["director"]
                title = details["title"]
            else:
                poster = _NO_POSTER
                genre = "Unknown"
                director = manual_director or "Unknown"

            insert_movies(title, director, genre, year, date, rating, rewatch, tv_show, poster, current_user.id, cinema)
            _clear_user_cache()
            flash("Movie added", category="success")
        except Exception:
            from flask import current_app
            current_app.logger.exception("Error adding movie")
            flash("Something went wrong, please try again", category="error")
            return redirect("/add_movie")

    return render_template("add_movie.html")

@movies_bp.route("/search_tmdb", methods=["GET"])
@login_required
@limiter.limit("100 per hour")
def search_tmdb():
    query = request.args.get("q", "")
    tv_show = request.args.get("tv", "0")
    if not query or len(query) < 2:
        return jsonify([])
    
    results = tmdb_service.search_titles(query, is_tv=(tv_show == "1"))
    return jsonify(results)

@movies_bp.route("/api/director", methods=["GET"])
@login_required
@limiter.limit("200 per hour")
def api_director():
    media_id = request.args.get("id")
    media_type = request.args.get("type")
    if not media_id or not media_type:
        return jsonify({"director": ""})
    director = tmdb_service.get_director_by_id(media_id, media_type)
    return jsonify({"director": director})



# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------

@movies_bp.route("/remove_movie", methods=["GET", "POST"])
@login_required
@limiter.limit("30 per hour")
def remove_movie():
    if request.method == "POST":
        movie_id = request.form.get("movie_id")
        if not movie_id and request.is_json:
            movie_id = request.json.get("movie_id")

        remove_movie_by_id(movie_id)
        _clear_user_cache()

        if request.is_json or request.accept_mimetypes.accept_json:
            return jsonify({"success": True, "message": "Movie removed"})

        flash("Movie removed", category="success")
        return redirect("/home")
    return redirect("/home")


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------

@movies_bp.route("/edit_movie", methods=["GET", "POST"])
@login_required
@limiter.limit("30 per hour")
def edit_movie():
    if request.method == "GET":
        return render_template("edit_movie.html")

    movie_id = request.form["movie_id"]
    title = request.form["movie"]
    director = request.form["director"]
    p_year = request.form["year"]
    rating = request.form["rating"]
    tv_show = request.form["tv"]

    if tv_show == "1":
        details = tmdb_service.get_tv_details(title, p_year, 1)
    else:
        details = tmdb_service.get_movie_details(title, p_year)

    poster = details["poster"] if details else _NO_POSTER

    update_movie(movie_id, title, director, p_year, rating, poster)
    _clear_user_cache()
    flash("Movie updated", category="success")
    return redirect("/home")
