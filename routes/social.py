"""Social blueprint — friends, follow/unfollow, compare, and AI discovery."""
import json
import os
import time

from flask import (
    Blueprint, Response, flash, jsonify, redirect,
    render_template, request, session, stream_with_context,
)
from flask_login import current_user, login_required

from ai_helpers import (
    DISCOVER_AVAILABLE_GENRES,
    DISCOVER_HISTORY_PROFILE_LABELS,
    DISCOVER_MODE_LABELS,
    DISCOVER_MODE_PROMPTS,
    build_discover_config,
    build_openrouter_settings,
    get_ai_movie_recommendation,
)
from database import (
    get_friend_activity,
    get_friends,
    get_enriched_friends,
    get_movies,
    get_taste_match,
    get_user_name,
    insert_friends,
    remove_friend,
    search_users_by_query,
)
from flask_limiter.util import get_remote_address
from extensions import cache, limiter
from utils import get_user_watch_history_summary, get_watched_title_year_lookup

social_bp = Blueprint("social", __name__)


# ---------------------------------------------------------------------------
# Friends
# ---------------------------------------------------------------------------

@social_bp.route("/friends", methods=["GET", "POST"])
@login_required
def search_friends():
    friends = get_enriched_friends(current_user.id)

    if request.method == "POST":
        name = request.form["name"]
        users = get_user_name(name)
        if not users:
            flash("No user found", category="error")
        else:
            return render_template("friends.html", users=users, friends=friends, session=session)

    recent_activity = get_friend_activity(current_user.id, limit=30)
    return render_template("friends.html", friends=friends, activity=recent_activity, session=session)


@social_bp.route("/follow", methods=["GET", "POST"])
@login_required
def follow():
    if request.method == "POST":
        friend_id = request.form["user_id"]
        friend_username = request.form["username"]
        insert_friends(friend_id, friend_username, current_user.id)
        flash(f"You are now following {friend_username}", "success")
    return redirect("/friends")


@social_bp.route("/unfollow", methods=["POST"])
@login_required
def unfollow():
    friend_id = request.form.get("user_id")
    friend_username = request.form.get("username")
    if friend_id:
        try:
            friend_id = int(friend_id)
        except ValueError:
            pass
        remove_friend(current_user.id, friend_id)
        flash(f"You unfollowed {friend_username}", "success")
    return redirect("/friends")


@social_bp.route("/api/users/search", methods=["GET"])
@login_required
def search_users_ajax():
    q = request.args.get("q", "").strip()
    if len(q) < 1:
        return jsonify([])
    
    matching_users = search_users_by_query(q, limit=8)
    current_friends = get_friends(current_user.id)
    following_ids = {f["user_id"] for f in current_friends}
    
    results = []
    for u in matching_users:
        if u["id"] == current_user.id:
            continue
        u_movies = get_movies(u["id"])
        results.append({
            "id": u["id"],
            "username": u["username"],
            "film_count": len(u_movies),
            "cinephile_level": max(1, len(u_movies) // 20),
            "is_following": u["id"] in following_ids
        })
    return jsonify(results)


@social_bp.route("/api/follow_ajax", methods=["POST"])
@login_required
def follow_ajax():
    data = request.get_json() or {}
    friend_id = data.get("user_id")
    friend_username = data.get("username")
    if not friend_id or not friend_username:
        return jsonify({"error": "Missing user_id or username"}), 400
    insert_friends(friend_id, friend_username, current_user.id)
    return jsonify({"success": True, "username": friend_username, "user_id": friend_id})


@social_bp.route("/api/unfollow_ajax", methods=["POST"])
@login_required
def unfollow_ajax():
    data = request.get_json() or {}
    friend_id = data.get("user_id")
    friend_username = data.get("username")
    if not friend_id:
        return jsonify({"error": "Missing user_id"}), 400
    try:
        friend_id = int(friend_id)
    except ValueError:
        pass
    remove_friend(current_user.id, friend_id)
    return jsonify({"success": True, "username": friend_username, "user_id": friend_id})


@social_bp.route("/compare/<username>")
@login_required
def compare_taste(username):
    friend_data = get_user_name(username)
    if not friend_data:
        flash("User not found.", "error")
        return redirect("/friends")
    match_data = get_taste_match(current_user.id, friend_data[0]["id"])
    return render_template(
        "compare.html",
        friend_username=username,
        friend_user=friend_data[0],
        current_user=current_user,
        match_data=match_data,
        session=session
    )


def _get_limiter_user_key():
    if current_user and current_user.is_authenticated:
        return f"user:{current_user.id}"
    return get_remote_address()


# ---------------------------------------------------------------------------
# Cinephile Cosmos — Autonomous Mathematical Discovery Engine
# ---------------------------------------------------------------------------

@social_bp.route("/discover")
@login_required
def discover():
    """
    Renders the interactive 2D Cinephile Cosmos star-map.
    Autonomous, vector-embedded galaxy of watched and recommended films.
    """
    print(f"[COSMOS BACKEND] >>> GET /discover requested by user_id={current_user.id}", flush=True)
    from services.cosmos_service import build_taste_cosmos_data, _GALAXY_CACHE
    cached = _GALAXY_CACHE.get(current_user.id)
    needs_refresh = True
    if cached and (time.time() - cached[0] < 3600):
        initial_data = cached[1]
        stars = initial_data.get("stars", []) if initial_data else []
        tv_missing = any(s.get("tv_show") in [1, "1", True] and not (s.get("poster") and str(s.get("poster")).startswith("http")) for s in stars)
        watched_count = sum(1 for s in stars if s.get("is_watched"))
        is_cache_valid = not tv_missing and len(stars) > 0
        if is_cache_valid:
            if watched_count == 0:
                from database import get_movies
                user_db_movies = get_movies(current_user.id) or []
                if len(user_db_movies) > 0:
                    is_cache_valid = False
                    print(f"[COSMOS BACKEND] Stale 0-watched cache detected for user_id={current_user.id} who has {len(user_db_movies)} movies in DB. Refreshing...", flush=True)
                elif cached[0] > time.time() - 300:
                    is_cache_valid = True
                else:
                    is_cache_valid = False

        if is_cache_valid:
            needs_refresh = False
            print(f"[COSMOS BACKEND] Found valid cached galaxy in memory for user_id={current_user.id} ({watched_count} watched)", flush=True)

    if needs_refresh:
        try:
            print(f"[COSMOS BACKEND] Computing fresh galaxy on initial load for user_id={current_user.id}...", flush=True)
            initial_data = build_taste_cosmos_data(current_user.id, force_refresh=True)
        except Exception as e:
            print(f"[COSMOS BACKEND] Error pre-building galaxy on initial load: {e}", flush=True)
            initial_data = None

    if initial_data:
        stats = initial_data.get("stats", {})
        sectors = initial_data.get("sectors", [])
    else:
        stats = {"watched_stars": 0, "uncharted_beacons": 0, "watchlist_stars": 0, "total_celestial_bodies": 0, "active_sectors": 0}
        sectors = []

    return render_template(
        "discover.html",
        stats=stats,
        sectors=sectors,
        initial_data=initial_data,
        session=session,
    )


@social_bp.route("/api/cosmos/galaxy", methods=["GET"])
@login_required
def cosmos_galaxy():
    """
    Returns full mathematical star-map payload: stars, constellation links,
    galactic sectors, and telemetry stats for the 2D Cosmos Canvas.
    """
    from services.cosmos_service import build_taste_cosmos_data
    force_refresh = request.args.get("refresh", "0") in ["1", "true", "True"]
    print(f"[COSMOS BACKEND] >>> GET /api/cosmos/galaxy requested by user_id={current_user.id} (force_refresh={force_refresh})", flush=True)
    try:
        t0 = time.time()
        payload = build_taste_cosmos_data(current_user.id, force_refresh=force_refresh)
        elapsed = round(time.time() - t0, 4)
        print(f"[COSMOS BACKEND] <<< Galaxy payload built in {elapsed}s: {len(payload.get('stars', []))} stars, {len(payload.get('sectors', []))} sectors", flush=True)
        return jsonify(payload)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[COSMOS BACKEND] ERROR building galaxy: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


@social_bp.route("/api/cosmos/probe", methods=["POST"])
@login_required
def cosmos_probe():
    """
    Retrieves the closest unwatched recommendation beacons to a probe point (x, y).
    """
    from services.cosmos_service import get_probe_recommendations
    data = request.get_json() or {}
    try:
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        limit = int(data.get("limit", 6))
        probe_res = get_probe_recommendations(x, y, current_user.id, limit=limit)
        return jsonify(probe_res)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@social_bp.route("/api/recommend_stream", methods=["POST"])
@login_required
@limiter.limit("5 per hour", key_func=_get_limiter_user_key)
def recommend_stream():
    from recommendation_service import get_ai_movie_recommendation_stream
    from database import get_movies

    data = request.get_json() or {}
    user_request = (data.get("user_request") or "").strip()
    recommendation_mode = (data.get("recommendation_mode") or "similar").strip().lower()
    history_profile = (data.get("history_profile") or "balanced").strip().lower()
    selected_genres = data.get("preferred_genres") or []

    media_type = (data.get("media_type") or "both").strip().lower()
    tone = data.get("tone") or 3
    pace = data.get("pace") or 3
    distance = data.get("distance") or 3
    mood_preset = (data.get("mood_preset") or "").strip()

    if not user_request:
        user_request = mood_preset or "Surprise me with top recommendations matching my vibe profile"

    active_titles = data.get("active_titles") or []
    print(f"[DEBUG] recommend_stream called: request='{user_request}', mode='{recommendation_mode}', active={active_titles}")

    user_history = get_user_watch_history_summary(
        current_user.id,
        history_profile=history_profile,
        history_profile_labels=DISCOVER_HISTORY_PROFILE_LABELS,
    )
    watched_lookup = get_watched_title_year_lookup(current_user.id)
    raw_movies = get_movies(current_user.id)
    settings = build_openrouter_settings()
    discover_config = build_discover_config()
    api_key = os.environ.get("OPENROUTER_API_KEY")

    def _generate():
        from flask import current_app
        accumulated = ""
        try:
            for chunk in get_ai_movie_recommendation_stream(
                user_request, user_history,
                recommendation_mode=recommendation_mode,
                preferred_genres=selected_genres,
                watched_lookup=watched_lookup,
                history_profile=history_profile,
                media_type=media_type,
                tone=tone,
                pace=pace,
                distance=distance,
                mood_preset=mood_preset,
                active_titles=active_titles,
                raw_movies=raw_movies,
                api_key=api_key,
                app_base_url=os.environ.get("APP_BASE_URL", "http://localhost:5000"),
                settings=settings,
                discover_config=discover_config,
                logger=current_app.logger,
            ):
                if chunk.startswith("Error:"):
                    yield f"data: {json.dumps({'error': chunk})}\n\n"
                    return
                accumulated += chunk
                yield f"data: {json.dumps({'token': chunk})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return Response(stream_with_context(_generate()), mimetype="text/event-stream")


@social_bp.route("/api/recommend_swap", methods=["POST"])
@login_required
@limiter.limit("15 per minute")
def recommend_swap():
    from recommendation_service import get_single_card_replacement_stream
    from database import get_movies

    data = request.get_json() or {}
    user_request = (data.get("user_request") or "").strip()
    if not user_request:
        user_request = "Top recommendations matching my vibe profile"

    active_titles = data.get("active_titles") or []
    rejected_title = (data.get("rejected_title") or "").strip()
    media_type = (data.get("media_type") or "both").strip().lower()
    tone = data.get("tone") or 3
    pace = data.get("pace") or 3
    distance = data.get("distance") or 3
    history_profile = (data.get("history_profile") or "balanced").strip().lower()

    print(f"[DEBUG] recommend_swap called: rejected='{rejected_title}', active={active_titles}")

    user_history = get_user_watch_history_summary(
        current_user.id,
        history_profile=history_profile,
        history_profile_labels=DISCOVER_HISTORY_PROFILE_LABELS,
    )
    watched_lookup = get_watched_title_year_lookup(current_user.id)
    raw_movies = get_movies(current_user.id)
    settings = build_openrouter_settings()
    discover_config = build_discover_config()
    api_key = os.environ.get("OPENROUTER_API_KEY")

    def _generate():
        from flask import current_app
        try:
            for chunk in get_single_card_replacement_stream(
                user_request,
                user_history,
                active_titles=active_titles,
                rejected_title=rejected_title,
                media_type=media_type,
                tone=tone,
                pace=pace,
                distance=distance,
                watched_lookup=watched_lookup,
                raw_movies=raw_movies,
                api_key=api_key,
                app_base_url=os.environ.get("APP_BASE_URL", "http://localhost:5000"),
                settings=settings,
                discover_config=discover_config,
                logger=current_app.logger,
            ):
                if chunk.startswith("Error:"):
                    yield f"data: {json.dumps({'error': chunk})}\n\n"
                    return
                yield f"data: {json.dumps({'token': chunk})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return Response(stream_with_context(_generate()), mimetype="text/event-stream")


@social_bp.route("/api/watchlist/add_ajax", methods=["POST"])
@login_required
def watchlist_add_ajax():
    from database import add_to_watchlist, get_or_create_personal_watchlist
    from services import tmdb_service
    from utils import clean_and_format, clean_and_capitalize_name

    data = request.get_json() or {}
    title = clean_and_format(data.get("title") or "")
    manual_director = (data.get("director") or "").strip()
    year = data.get("year") or ""
    tv_show = "1" if (data.get("media_type") or "") == "tv" else "0"

    if not title:
        return jsonify({"error": "Title required"}), 400

    if manual_director:
        manual_director = clean_and_capitalize_name(manual_director)

    try:
        if tv_show == "1":
            details = tmdb_service.get_tv_details(title, year, 1, manual_director)
        else:
            details = tmdb_service.get_movie_details(title, year, manual_director)

        if details:
            poster = details.get("poster") or "https://via.placeholder.com/200x300?text=No+Poster"
            director = details.get("director") or manual_director or "Unknown"
            title = details.get("title") or title
        else:
            poster = "https://via.placeholder.com/200x300?text=No+Poster"
            director = manual_director or "Unknown"

        wl = get_or_create_personal_watchlist(current_user.id)
        if wl:
            add_to_watchlist(wl['id'], current_user.id, title, director, year, poster)
            return jsonify({"success": True, "title": title})
        return jsonify({"error": "Failed to access watchlist"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

