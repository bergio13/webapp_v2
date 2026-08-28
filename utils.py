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

from database import get_movies
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

def format_display_title(title: str) -> str:
    """
    Format a media title cleanly for display, capitalizing lowercased titles or TV show names
    (e.g., 'superstore, Season 4' -> 'Superstore, Season 4', 'marty supreme' -> 'Marty Supreme').
    """
    if not title or not isinstance(title, str):
        return title or ""
    
    t = title.strip()
    if not t:
        return ""

    if ',' in t:
        parts = t.split(',', 1)
        show_name = parts[0].strip()
        season_part = parts[1].strip()
        if show_name and show_name[0].islower():
            words = show_name.split()
            show_name = " ".join(
                w.capitalize() if not (w.lower() in {'a', 'an', 'the', 'of', 'in', 'on', 'at', 'to', 'for', 'and'} and i > 0) else w
                for i, w in enumerate(words)
            )
            if show_name:
                show_name = show_name[0].upper() + show_name[1:]
        return f"{show_name}, {season_part}"
    elif t[0].islower():
        words = t.split()
        res = " ".join(
            w.capitalize() if not (w.lower() in {'a', 'an', 'the', 'of', 'in', 'on', 'at', 'to', 'for', 'and'} and i > 0) else w
            for i, w in enumerate(words)
        )
        return (res[0].upper() + res[1:]) if res else t
    
    return t


def clean_and_format(word: str) -> str:
    """Normalise whitespace and clean a movie or TV title for storage."""
    if not word:
        return ""
    cleaned = " ".join(word.strip().split())
    if cleaned.islower():
        return format_display_title(cleaned)
    return cleaned


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
    year_now, month_now = get_current_year_month()
    movies = get_movies(user_id)

    stats["movies"] = movies
    stats["length"] = len(movies)

    # Calculate monthly movies count directly in memory without extra network query
    month_movies_count = 0
    for m in movies:
        v_d = m.get("v_date")
        if isinstance(v_d, datetime.date):
            if v_d.year == year_now and v_d.month == month_now:
                month_movies_count += 1
        elif isinstance(v_d, str) and len(v_d) >= 7:
            try:
                dt = datetime.datetime.strptime(v_d[:10], "%Y-%m-%d").date()
                if dt.year == year_now and dt.month == month_now:
                    month_movies_count += 1
            except Exception:
                pass

    stats["length_month"] = month_movies_count

    ratings: list = []
    genre_scores: dict = {}
    unique_genres: set = set()
    unique_directors: set = set()
    active_months: set = set()
    rewatch_count = 0
    cinema_count = 0

    director_counts: dict = {}
    for movie in movies:
        raw_rating = movie.get("rating")
        if raw_rating is not None and str(raw_rating).strip() != "":
            try:
                r_val = float(raw_rating)
                if r_val > 5:
                    r_val = float(math.ceil(r_val / 2.0))
                r_val = max(1.0, min(5.0, r_val))
                ratings.append(r_val)
            except (ValueError, TypeError):
                pass
            
        if str(movie.get("rewatch") or "").strip() in ("1", "true", "True") or movie.get("rewatch") in (1, True):
            rewatch_count += 1
        if str(movie.get("cinema") or "").strip() in ("1", "true", "True") or movie.get("cinema") in (1, True):
            cinema_count += 1

        director = str(movie.get("director") or "").strip()
        if director and director != "Unknown":
            unique_directors.add(director)
            director_counts[director] = director_counts.get(director, 0) + 1

        watched_date = movie.get("v_date")
        if isinstance(watched_date, datetime.date):
            active_months.add((watched_date.year, watched_date.month))

        for genre in split_genres(movie.get("genre")):
            unique_genres.add(genre)
            genre_scores[genre] = genre_scores.get(genre, 0) + 1
            if raw_rating is not None:
                try:
                    num_r = float(raw_rating)
                    if num_r > 3:
                        genre_scores[genre] += (num_r - 3)
                except (ValueError, TypeError):
                    pass

    fav_genre = max(genre_scores, key=genre_scores.get) if genre_scores else "No movies added"
    stats["favorite_genre"] = fav_genre
    stats["avg_rating"] = round(sum(ratings) / len(ratings), 2) if ratings else 0
    stats["rewatch_rate"] = (
        round((rewatch_count / stats["length"]) * 100, 1) if stats["length"] else 0
    )
    stats["rewatch_count"] = rewatch_count
    stats["cinema_count"] = cinema_count
    stats["cinema_rate"] = (
        round((cinema_count / stats["length"]) * 100, 1) if stats["length"] else 0
    )
    stats["unique_directors"] = len(unique_directors)
    stats["unique_genres"] = len(unique_genres)
    stats["avg_movies_per_month"] = (
        round(stats["length"] / len(active_months), 2) if active_months else 0
    )

    # Top directors
    sorted_directors = sorted(director_counts.items(), key=lambda x: x[1], reverse=True)
    stats["top_directors_ranked"] = [
        {"director": d, "count": c} for d, c in sorted_directors[:5]
    ]

    # Hours & Level
    total_films = stats["length"]
    stats["total_hours_watched"] = round((total_films * 115) / 60)
    stats["cinephile_level"] = max(1, total_films // 20)

    # Cinephile Persona Archetype
    if total_films == 0:
        stats["cinephile_archetype"] = "NEOPHYTE LOG INITIATE"
    elif stats["cinema_rate"] >= 35:
        stats["cinephile_archetype"] = "SILVER SCREEN DEVOTEE"
    elif stats["rewatch_rate"] >= 25:
        stats["cinephile_archetype"] = "COMFORT CANON ARCHIVIST"
    elif fav_genre in ["Sci-Fi", "Fantasy"]:
        stats["cinephile_archetype"] = "WORLDBUILDER EXPLORER"
    elif fav_genre == "Horror":
        stats["cinephile_archetype"] = "MIDNIGHT DREAD SEEKER"
    elif fav_genre in ["Drama", "Crime", "Mystery"]:
        stats["cinephile_archetype"] = "AUTEUR SPECIALIST"
    elif fav_genre == "Animation":
        stats["cinephile_archetype"] = "ANIMA VISIONARY"
    elif fav_genre in ["Comedy", "Romance"]:
        stats["cinephile_archetype"] = "FEEL-GOOD CINETASTE"
    elif total_films >= 250:
        stats["cinephile_archetype"] = "CINEPHILE VETERAN"
    else:
        stats["cinephile_archetype"] = "CYBER CINEPHILE OPERATOR"

    # Rating distribution & histogram
    total_rated = len(ratings) or 1
    c5 = sum(1 for r in ratings if round(r) == 5)
    c4 = sum(1 for r in ratings if round(r) == 4)
    c3 = sum(1 for r in ratings if round(r) == 3)
    c2 = sum(1 for r in ratings if round(r) == 2)
    c1 = sum(1 for r in ratings if round(r) == 1)

    stats["ratings_histogram"] = [
        {"stars": 5, "label": "5★", "count": c5, "pct": round((c5 / total_rated) * 100, 1)},
        {"stars": 4, "label": "4★", "count": c4, "pct": round((c4 / total_rated) * 100, 1)},
        {"stars": 3, "label": "3★", "count": c3, "pct": round((c3 / total_rated) * 100, 1)},
        {"stars": 2, "label": "2★", "count": c2, "pct": round((c2 / total_rated) * 100, 1)},
        {"stars": 1, "label": "1★", "count": c1, "pct": round((c1 / total_rated) * 100, 1)},
    ]

    stats["ratings_distribution"] = {
        "loved": c5,
        "liked": c4,
        "ok": c3,
        "disliked": c2,
        "hated": c1,
        "high": c5,
        "mid": c3 + c4,
        "low": c1 + c2,
    }

    # Milestones
    stats["milestone_badges"] = [
        {
            "id": "century",
            "name": "Century Club",
            "desc": "Logged 100+ titles",
            "icon": "💯",
            "earned": total_films >= 100,
            "progress": f"{min(100, total_films)}/100" if total_films < 100 else "UNLOCKED"
        },
        {
            "id": "cinema",
            "name": "Cinema Pioneer",
            "desc": "10+ theatre viewings",
            "icon": "🎟️",
            "earned": cinema_count >= 10,
            "progress": f"{min(10, cinema_count)}/10" if cinema_count < 10 else "UNLOCKED"
        },
        {
            "id": "rewatch",
            "name": "Rewatch Master",
            "desc": "15+ cherished rewatches",
            "icon": "🔄",
            "earned": rewatch_count >= 15,
            "progress": f"{min(15, rewatch_count)}/15" if rewatch_count < 15 else "UNLOCKED"
        },
        {
            "id": "diverse",
            "name": "Genre Voyager",
            "desc": "Explored 8+ unique genres",
            "icon": "🪐",
            "earned": len(unique_genres) >= 8,
            "progress": f"{min(8, len(unique_genres))}/8" if len(unique_genres) < 8 else "UNLOCKED"
        }
    ]

    return stats


# ---------------------------------------------------------------------------
# Watch-history helpers
# ---------------------------------------------------------------------------

def get_watched_title_year_lookup(user_id) -> set:
    """Return a ``{(normalized_title, year)}`` set for movies already watched."""
    try:
        from database import get_movies
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
        from database import get_movies
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
