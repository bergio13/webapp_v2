"""Profile blueprint — user profile and raw data endpoints."""
from flask import Blueprint, flash, jsonify, render_template
from flask_login import current_user, login_required

from database import get_movies, get_user_by_id, get_user_id, load_users_from_username
from utils import build_profile_stats, get_default_profile_stats

profile_bp = Blueprint("profile", __name__)


# ---------------------------------------------------------------------------
# Raw data (JSON)
# ---------------------------------------------------------------------------

@profile_bp.route("/users/<name>")
def show_user_profile(name):
    return jsonify(load_users_from_username(name))


@profile_bp.route("/data")
@login_required
def list_about():
    return jsonify(get_movies(current_user.id))


@profile_bp.route("/data/<username>")
@login_required
def list_about_friend(username):
    users = get_user_id(username)
    return jsonify(get_movies(users[0]["id"]))


# ---------------------------------------------------------------------------
# Profile pages
# ---------------------------------------------------------------------------

@profile_bp.route("/profile")
@login_required
def profile():
    users = get_user_by_id(current_user.id)
    profile_stats = get_default_profile_stats()
    try:
        profile_stats = build_profile_stats(current_user.id)
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load profile page")
        flash("Something went wrong, please refresh the page", category="error")
    return render_template("profile.html", user=users[0], **profile_stats)


@profile_bp.route("/profile/<username>")
@login_required
def profile_friend(username):
    users = get_user_id(username)
    profile_stats = get_default_profile_stats()
    try:
        profile_stats = build_profile_stats(users[0]["id"])
    except Exception:
        from flask import current_app
        current_app.logger.exception("Failed to load friend profile page for %s", username)
        flash("Something went wrong, please refresh the page", category="error")
    return render_template("_profile.html", username=username, user=users[0], **profile_stats)
