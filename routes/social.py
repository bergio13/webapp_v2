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
    return render_template("compare.html", friend_username=username, match_data=match_data, session=session)


# ---------------------------------------------------------------------------
# AI Discovery
# ---------------------------------------------------------------------------

@social_bp.route("/discover", methods=["GET", "POST"])
@login_required
@limiter.limit("10 per minute")
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
@limiter.limit("10 per minute")
def recommend_stream():
    from recommendation_service import get_ai_movie_recommendation_stream

    data = request.get_json() or {}
    user_request = data.get("user_request", "").strip()
    recommendation_mode = data.get("recommendation_mode", "similar").strip().lower()
    history_profile = data.get("history_profile", "balanced").strip().lower()
    selected_genres = data.get("preferred_genres", [])

    if not user_request:
        return jsonify({"error": "Prompt required"}), 400

    if not user_request:
        return jsonify({"error": "Prompt required"}), 400

    user_history = get_user_watch_history_summary(
        current_user.id,
        history_profile=history_profile,
        history_profile_labels=DISCOVER_HISTORY_PROFILE_LABELS,
    )
    watched_lookup = get_watched_title_year_lookup(current_user.id)
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

            # No caching to ensure fresh recommendations every time
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return Response(stream_with_context(_generate()), mimetype="text/event-stream")
