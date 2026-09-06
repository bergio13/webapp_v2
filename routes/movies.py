import logging
import os
import re
import threading

from flask import Blueprint, flash, jsonify, redirect, render_template, request
from flask_login import current_user, login_required

from database import insert_movies, remove_movie_by_id, update_movie
from extensions import cache, limiter
from services import tmdb_service
from utils import clean_and_capitalize_name, clean_and_format

logger = logging.getLogger(__name__)

movies_bp = Blueprint("movies", __name__)

_NO_POSTER = "https://via.placeholder.com/200x300?text=No+Poster"


def _clear_user_cache():
    """Invalidate all cached data (SimpleCache — clears everything) and cosmos galaxy cache."""
    cache.clear()
    try:
        from services.cosmos_service import invalidate_galaxy_cache
        if current_user and current_user.is_authenticated:
            invalidate_galaxy_cache(current_user.id)
        else:
            invalidate_galaxy_cache()
    except Exception:
        pass


def _async_catalog_enrichment(title: str, year: Any = None, tmdb_id: Any = None, is_tv: bool = False, season_num: Any = None, director: str = "", genre: str = ""):
    """
    Runs asynchronously in a detached background thread:
    - Fetches rich metadata (multi-genres, overview, keywords, craft crew, lead actors)
    - Computes 384D FastEmbed semantic embedding vector
    - Upserts to Supabase canonical movie_catalog
    - For TV shows, enriches season metadata and upserts tv_season_catalog
    """
    try:
        from services.catalog_service import (
            fetch_and_enrich_from_tmdb, upsert_catalog_item,
            fetch_and_enrich_tv_season, upsert_tv_season_catalog_item
        )
        safe_tmdb_id = int(tmdb_id) if tmdb_id and str(tmdb_id).isdigit() else None
        enriched = fetch_and_enrich_from_tmdb(title, year, tmdb_id=safe_tmdb_id, is_tv=is_tv)
        if director and director != "Unknown" and not enriched.get("director"):
            enriched["director"] = director
        if genre and genre != "Unknown" and not enriched.get("genres"):
            enriched["genres"] = genre
        upsert_catalog_item(enriched, compute_embedding=True)

        if is_tv:
            resolved_id = safe_tmdb_id or enriched.get("tmdb_id")
            if resolved_id:
                try:
                    s_num = int(season_num) if season_num and str(season_num).isdigit() else 1
                    season_enriched = fetch_and_enrich_tv_season(int(resolved_id), s_num, show_title=title)
                    if season_enriched:
                        if (not season_enriched.get("director") or season_enriched["director"] == "Unknown") and director and director != "Unknown":
                            season_enriched["director"] = director
                        upsert_tv_season_catalog_item(season_enriched, compute_embedding=True)
                except Exception as s_err:
                    logger.debug(f"TV season async enrichment notice: {s_err}")
    except Exception as err:
        logger.debug(f"Async catalog enrichment notice: {err}")


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
            manual_director = request.form.get("director", "").strip()
            year = request.form["year"]
            date = request.form["date"]
            rating = request.form["rating"]
            rewatch = request.form["rewatch"]
            tv_show = request.form["tv"]
            which_season = request.form["season"]
            cinema = request.form["cinema"]
            tmdb_id = request.form.get("tmdb_id", "").strip() or None
            form_poster = request.form.get("poster_url", "").strip() or None

            if manual_director:
                manual_director = clean_and_capitalize_name(manual_director)

            is_tv = (tv_show == "1")
            season_num = None
            if is_tv:
                from services.catalog_service import resolve_tv_season_number
                season_num = resolve_tv_season_number(title, tmdb_id=tmdb_id, current_season=which_season, poster_url=form_poster)
                # Clean title to pure series title before querying details
                title = re.sub(r',?\s*(?:season|series|volume|vol|part|bk|book|the final season|final season)\s*\d*.*$', '', title, flags=re.IGNORECASE).strip()

            # Fast-path 1: Check local SQLite catalog cache (<0.2ms)
            poster = form_poster
            director = manual_director
            genre = None
            resolved_tmdb_id = tmdb_id

            try:
                from services.catalog_service import get_catalog_item, get_tv_season_catalog_item
                safe_int_tmdb = int(tmdb_id) if tmdb_id and str(tmdb_id).isdigit() else None
                catalog_item = get_catalog_item(title, year, tmdb_id=safe_int_tmdb)
                if catalog_item:
                    if not poster or "placeholder" in str(poster).lower() or poster == _NO_POSTER:
                        poster = catalog_item.get("poster")
                    if not director or director == "Unknown":
                        director = catalog_item.get("director")
                    genre = catalog_item.get("genres")
                    resolved_tmdb_id = resolved_tmdb_id or catalog_item.get("tmdb_id")

                # If this is a TV show and a season is chosen, check if local season catalog has the season poster, director, and year
                if is_tv and season_num and (safe_int_tmdb or resolved_tmdb_id):
                    tid = safe_int_tmdb or resolved_tmdb_id
                    s_cat = get_tv_season_catalog_item(int(tid), int(season_num))
                    if s_cat:
                        if s_cat.get("poster") and "placeholder" not in str(s_cat["poster"]).lower():
                            poster = s_cat["poster"]
                        if not manual_director and s_cat.get("director"):
                            s_dir = s_cat["director"].strip()
                            if s_dir.lower() not in {"unknown", "various directors", "various", "showrunner"}:
                                director = s_dir
                        if not manual_director and is_tv and s_cat.get("creator") and (not director or director == "Unknown"):
                            director = s_cat["creator"].strip()
                        if s_cat.get("year"):
                            year = str(s_cat["year"])
            except Exception as cat_read_err:
                logger.debug(f"Fast local catalog read notice: {cat_read_err}")

            # Fast-path 2: Only query TMDb synchronously if we still lack basic display details
            if not poster or "placeholder" in str(poster).lower() or poster == _NO_POSTER or not genre or not resolved_tmdb_id:
                if is_tv:
                    details = tmdb_service.get_tv_details(title, year, season_num, director, tmdb_id=resolved_tmdb_id)
                else:
                    details = tmdb_service.get_movie_details(title, year, director, tmdb_id=resolved_tmdb_id)

                if details:
                    if not poster or "placeholder" in str(poster).lower() or poster == _NO_POSTER:
                        poster = details.get("poster")
                    if form_poster and ("placeholder" in str(poster).lower() or "placehold.co" in str(poster).lower()):
                        poster = form_poster
                    genre = genre or details.get("genre")
                    if not manual_director and details.get("director"):
                        d_cand = details["director"].strip()
                        if d_cand.lower() not in {"unknown", "various directors", "various", "showrunner"}:
                            director = d_cand
                    if not manual_director and is_tv and details.get("creator") and (not director or director == "Unknown"):
                        director = details["creator"].strip()
                    matched_title = details.get("title") or title
                    if is_tv:
                        matched_title = re.sub(r',?\s*season\s*\d+.*$', '', matched_title, flags=re.IGNORECASE).strip()
                    title = matched_title
                    resolved_tmdb_id = resolved_tmdb_id or details.get("tmdb_id")

            poster = poster or form_poster or _NO_POSTER
            genre = genre or ("TV Series" if is_tv else "Feature Film")
            director = director or manual_director or "Unknown"

            # Insert into user's personal list immediately
            insert_movies(title, director, genre, year, date, rating, rewatch, tv_show, poster, current_user.id, cinema, season=season_num, tmdb_id=resolved_tmdb_id)
            _clear_user_cache()

            # Offload heavy catalog enrichment, FastEmbed 384D embedding, and Supabase catalog upsert to background thread
            threading.Thread(
                target=_async_catalog_enrichment,
                args=(title, year, resolved_tmdb_id, is_tv, season_num, director, genre),
                daemon=True
            ).start()

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


@movies_bp.route("/api/tv_seasons", methods=["GET"])
@login_required
@limiter.limit("200 per hour")
def api_tv_seasons():
    tmdb_id = request.args.get("id") or request.args.get("tmdb_id")
    title = request.args.get("title", "")
    if not tmdb_id:
        return jsonify([])
    try:
        seasons = tmdb_service.get_tv_seasons_list(int(tmdb_id), title=title)
        return jsonify(seasons)
    except Exception as e:
        logger.debug(f"Error fetching TV seasons for {tmdb_id}: {e}")
        return jsonify([])



# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------

@movies_bp.route("/remove_movie", methods=["GET", "POST"])
@login_required
@limiter.limit("150 per hour")
def remove_movie():
    if request.method == "POST":
        movie_id = request.form.get("movie_id")
        if not movie_id and request.is_json:
            movie_id = request.json.get("movie_id")

        if movie_id:
            try:
                movie_id = int(movie_id)
            except (ValueError, TypeError):
                pass
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
    season_num = None

    resolved_tmdb_id = None
    if tv_show == "1":
        from services.catalog_service import resolve_tv_season_number
        season_num = resolve_tv_season_number(title)
        title = re.sub(r',?\s*(?:season|series|volume|vol|part|bk|book|the final season|final season)\s*\d*.*$', '', title, flags=re.IGNORECASE).strip()
        details = tmdb_service.get_tv_details(title, p_year, season_num or 1)
        if details and details.get("tmdb_id"):
            resolved_tmdb_id = details["tmdb_id"]
            # Immediately synchronize user's manual director update into tv_season_catalog
            try:
                from services.catalog_service import get_tv_season_catalog_item, upsert_tv_season_catalog_item
                s_item = get_tv_season_catalog_item(int(resolved_tmdb_id), season_num or 1) or {}
                if director and director != "Unknown":
                    s_item["director"] = director
                if s_item:
                    s_item["tmdb_id"] = int(resolved_tmdb_id)
                    s_item["season_number"] = season_num or 1
                    s_item["show_title"] = title
                    upsert_tv_season_catalog_item(s_item, compute_embedding=False)
            except Exception as se:
                logger.debug(f"Notice syncing edit to tv_season_catalog: {se}")

            threading.Thread(
                target=_async_catalog_enrichment,
                args=(title, p_year, details["tmdb_id"], True, season_num or 1, director, details.get("genre", "")),
                daemon=True
            ).start()
    else:
        details = tmdb_service.get_movie_details(title, p_year)
        if details and details.get("tmdb_id"):
            resolved_tmdb_id = details["tmdb_id"]

    poster = details["poster"] if details else _NO_POSTER

    update_movie(movie_id, title, director, p_year, rating, poster, season=season_num, tmdb_id=resolved_tmdb_id)
    _clear_user_cache()
    flash("Movie updated", category="success")
    return redirect("/home")
