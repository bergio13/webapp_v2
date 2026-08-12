"""Shared utility functions and constants used across the application.

Keeping these separate avoids circular imports: blueprints import from here,
not from each other.
"""
import datetime
import logging
import math
import re

from flask import request
from flask_login import current_user

from database import get_monthly_movies, get_movies
from recommendation_service import (
    build_user_watch_history_summary,
    build_watched_title_year_lookup,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Month constants
# ---------------------------------------------------------------------------

months = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

dict_months = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}

# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------

def clean_and_format(word: str) -> str:
    """Normalise and lowercase a movie title for storage."""
    return " ".join(word.strip().split()).lower()


def clean_and_capitalize_name(name: str) -> str:
    """Trim, lowercase, then title-case each word of a person's name."""
    return " ".join(w.capitalize() for w in name.strip().lower().split())


def split_genres(genre_value) -> list:
    """Split a comma-separated genre string into a clean list."""
    if not genre_value:
        return []
    return [g.strip() for g in str(genre_value).split(",") if g.strip()]


def normalize_title_for_match(title) -> str:
    """Collapse whitespace and lowercase a title for deterministic matching."""
    if not title:
        return ""
    return re.sub(r"\s+", " ", str(title)).strip().lower()


def parse_year(year_value):
    """Parse a year value to int, returning None on failure."""
    try:
        return int(str(year_value).strip())
    except (TypeError, ValueError):
        return None


def extract_title_year_from_heading(heading):
    """Return ``(title, year)`` from an AI heading like ``'Movie (2023)'``."""
    if not heading:
        return None, None
    match = re.match(r"^(.*?)\s*\((\d{4})\)", heading.strip())
    if not match:
        return None, None
    return match.group(1).strip(), int(match.group(2))


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def get_current_year_month():
    """Return ``(year, month)`` for today, computed at call time."""
    today = datetime.date.today()
    return today.year, today.month


# ---------------------------------------------------------------------------
# Cache key helper
# ---------------------------------------------------------------------------

def make_user_cache_key() -> str:
    """Per-user cache key based on the authenticated user's ID and request path."""
    user_id = current_user.id if current_user.is_authenticated else "anonymous"
    return f"user_{user_id}_{request.path}"


# ---------------------------------------------------------------------------
# Profile statistics
# ---------------------------------------------------------------------------

def get_default_profile_stats() -> dict:
    """Return a zeroed-out stats dict used as a safe fallback."""
    return {
        "movies": [],
        "length": 0,
        "length_month": 0,
        "avg_rating": 0,
        "favorite_genre": "No movies added",
        "rewatch_rate": 0,
        "cinema_count": 0,
        "unique_directors": 0,
        "unique_genres": 0,
        "avg_movies_per_month": 0,
        "ratings_distribution": {
            "loved": 0, "liked": 0, "ok": 0, "disliked": 0, "hated": 0,
            "high": 0, "mid": 0, "low": 0
        },
    }


def build_profile_stats(user_id) -> dict:
    """Compute full profile statistics for *user_id*."""
    stats = get_default_profile_stats()
    _, month_now = get_current_year_month()
    movies = get_movies(user_id)

    stats["movies"] = movies
    stats["length"] = len(movies)
    stats["length_month"] = len(get_monthly_movies(user_id, month_now))

    ratings: list = []
    genre_scores: dict = {}
    unique_genres: set = set()
    unique_directors: set = set()
    active_months: set = set()
    rewatch_count = 0
    cinema_count = 0

    for movie in movies:
        rating = movie.get("rating")
        if isinstance(rating, (int, float)):
            # Normalize legacy 6-10 ratings to 1-5 if any unmigrated exist
            r_val = float(rating)
            if r_val > 5:
                r_val = float(math.ceil(r_val / 2.0))
            ratings.append(r_val)
            
        if movie.get("rewatch"):
            rewatch_count += 1
        if movie.get("cinema"):
            cinema_count += 1

        director = str(movie.get("director") or "").strip()
        if director:
            unique_directors.add(director)

        watched_date = movie.get("v_date")
        if isinstance(watched_date, datetime.date):
            active_months.add((watched_date.year, watched_date.month))

        for genre in split_genres(movie.get("genre")):
            unique_genres.add(genre)
            genre_scores[genre] = genre_scores.get(genre, 0) + 1
            if isinstance(rating, (int, float)) and rating > 3:
                genre_scores[genre] += (rating - 3)

    stats["favorite_genre"] = (
        max(genre_scores, key=genre_scores.get) if genre_scores else "No movies added"
    )
    stats["avg_rating"] = round(sum(ratings) / len(ratings), 2) if ratings else 0
    stats["rewatch_rate"] = (
        round((rewatch_count / stats["length"]) * 100, 1) if stats["length"] else 0
    )
    stats["cinema_count"] = cinema_count
    stats["unique_directors"] = len(unique_directors)
    stats["unique_genres"] = len(unique_genres)
    stats["avg_movies_per_month"] = (
        round(stats["length"] / len(active_months), 2) if active_months else 0
    )
    stats["ratings_distribution"] = {
        "loved": sum(1 for r in ratings if r == 5),
        "liked": sum(1 for r in ratings if r == 4),
        "ok": sum(1 for r in ratings if r == 3),
        "disliked": sum(1 for r in ratings if r == 2),
        "hated": sum(1 for r in ratings if r == 1),
        "high": sum(1 for r in ratings if r == 5),
        "mid": sum(1 for r in ratings if 3 <= r <= 4),
        "low": sum(1 for r in ratings if r <= 2),
    }
    return stats


# ---------------------------------------------------------------------------
# Watch-history helpers
# ---------------------------------------------------------------------------

def get_watched_title_year_lookup(user_id) -> set:
    """Return a ``{(normalized_title, year)}`` set for movies already watched."""
    try:
        movies = get_movies(user_id)
    except Exception:
        logger.exception("Failed to build watched lookup for user %s", user_id)
        return set()
    return build_watched_title_year_lookup(movies)


def get_user_watch_history_summary(
    user_id,
    history_profile: str = "balanced",
    max_cap: int = 60,
    history_profile_labels: dict | None = None,
) -> str:
    """Return a formatted watch-history string for the AI prompt.

    *history_profile_labels* is injected by the caller (from ``ai_helpers``)
    to avoid a circular import at module load time.
    """
    if history_profile_labels is None:
        history_profile_labels = {
            "recent": "Recent Favorites",
            "balanced": "Balanced Mix",
            "all_time": "All-Time Profile",
        }
    try:
        movies = get_movies(user_id)
        return build_user_watch_history_summary(
            movies,
            history_profile=history_profile,
            max_cap=max_cap,
            history_profile_labels=history_profile_labels,
        )
    except Exception:
        logger.exception("Error building watch history for user %s", user_id)
        return "Unable to retrieve watch history."
