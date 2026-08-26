"""Social blueprint — friends, follow/unfollow, compare, and AI discovery."""
import json
import os

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
    get_taste_match,
    get_user_name,
    insert_friends,
    remove_friend,
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
    friends = get_friends(current_user.id)

    if request.method == "POST":
        name = request.form["name"]
        users = get_user_name(name)
        if not users:
            flash("No user found", category="error")
        else:
            return render_template("friends.html", users=users, friends=friends, session=session)

    recent_activity = get_friend_activity(current_user.id, limit=25)
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
# AI Discovery
# ---------------------------------------------------------------------------

@social_bp.route("/discover", methods=["GET", "POST"])
@login_required
@limiter.limit("5 per hour", key_func=_get_limiter_user_key, methods=["POST"])
def discover():
    ai_response = None
    user_request = ""
    recommendation_mode = "similar"
    history_profile = "balanced"
    selected_genres = []

    if request.method == "POST":
        user_request = request.form.get("user_request", "").strip()
        recommendation_mode = request.form.get("recommendation_mode", "similar").strip().lower()
        if recommendation_mode not in DISCOVER_MODE_PROMPTS:
            recommendation_mode = "similar"

        history_profile = request.form.get("history_profile", "balanced").strip().lower()
        if history_profile not in DISCOVER_HISTORY_PROFILE_LABELS:
            history_profile = "balanced"

        selected_genres = []
        for genre in request.form.getlist("preferred_genres"):
            cleaned = genre.strip()
            if cleaned in DISCOVER_AVAILABLE_GENRES and cleaned not in selected_genres:
                selected_genres.append(cleaned)

        if user_request:
            user_history = get_user_watch_history_summary(
                current_user.id,
                history_profile=history_profile,
                history_profile_labels=DISCOVER_HISTORY_PROFILE_LABELS,
            )
            watched_lookup = get_watched_title_year_lookup(current_user.id)
            ai_response = get_ai_movie_recommendation(
                user_request, user_history,
                recommendation_mode=recommendation_mode,
                preferred_genres=selected_genres,
                watched_lookup=watched_lookup,
                history_profile=history_profile,
            )
        else:
            flash("Please enter a request for movie recommendations", "error")

    return render_template(
        "discover.html",
        ai_response=ai_response,
        user_request=user_request,
        recommendation_mode=recommendation_mode,
        history_profile=history_profile,
        selected_genres=selected_genres,
        discover_mode_labels=DISCOVER_MODE_LABELS,
        discover_history_profile_labels=DISCOVER_HISTORY_PROFILE_LABELS,
        discover_available_genres=DISCOVER_AVAILABLE_GENRES,
        session=session,
    )


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

