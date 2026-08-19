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
    if not users:
        return jsonify([])
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


@profile_bp.route("/api/export_csv")
@login_required
def export_csv():
    """Export the user's full watched movie database as a CSV attachment."""
    import csv
    import io
    from flask import Response

    movies = get_movies(current_user.id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Title", "Year", "Director", "Genre", "Rating", "Watched Date", "Cinema", "Rewatch", "TV Show"])

    for m in movies:
        writer.writerow([
            m.get("movie", ""),
            m.get("p_year", ""),
            m.get("director", ""),
            m.get("genre", ""),
            m.get("rating", ""),
            str(m.get("v_date", "")),
            1 if m.get("cinema") else 0,
            1 if m.get("rewatch") else 0,
            1 if m.get("tv_show") else 0,
        ])

    username = getattr(current_user, "username", "my")
    filename = f"{username}_kineto_library.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

