import os
import random
import re
import time
from dataclasses import dataclass
from html import escape
from typing import Optional, Sequence

import requests

from services.tmdb_service import get_movie_details as tmdb_get_movie_details


@dataclass(frozen=True)
class OpenRouterSettings:
    api_url: str
    model_id: str
    model_fallbacks: Sequence[str]
    request_timeout: float
    total_timeout: float
    model_deadline: float
    max_completion_tokens: int
    max_attempts: int
    retry_base_delay: float
    retry_max_delay: float
    retry_429_max_delay: float
    retry_jitter: float
    provider_sort: str
    provider_allow_fallbacks: bool
    provider_require_parameters: bool
    provider_only: Sequence[str]
    provider_ignore: Sequence[str]
    preferred_max_latency: Optional[float]
    preferred_min_throughput: Optional[float]
    service_tier: str


@dataclass(frozen=True)
class DiscoverConfig:
    mode_labels: dict
    mode_prompts: dict
    history_profile_labels: dict
    history_profile_prompts: dict
    available_genres: Sequence[str]


class OpenRouterRateLimitError(RuntimeError):
    """Raised when OpenRouter keeps returning HTTP 429 after retries."""

    def __init__(self, wait_seconds=None):
        self.wait_seconds = wait_seconds
        if wait_seconds is None:
            message = "OpenRouter is rate-limiting requests"
        else:
            message = f"OpenRouter is rate-limiting requests (retry after ~{wait_seconds:.0f}s)"
        super().__init__(message)


def _log_info(logger, message, *args):
    if logger is not None and hasattr(logger, "info"):
        logger.info(message, *args)


def _log_warning(logger, message, *args):
    if logger is not None and hasattr(logger, "warning"):
        logger.warning(message, *args)


def _log_exception(logger, message, *args):
    if logger is not None and hasattr(logger, "exception"):
        logger.exception(message, *args)


def normalize_title_for_match(title):
    """Normalize titles for deterministic strict matching."""
    if not title:
        return ""
    return re.sub(r"\s+", " ", str(title)).strip().lower()


def parse_year(year_value):
    """Parse a year value to int when possible."""
    try:
        return int(str(year_value).strip())
    except (TypeError, ValueError):
        return None


def extract_title_year_from_heading(heading):
    """Extract title and year from recommendation heading text."""
    if not heading:
        return None, None

    match = re.match(r"^(.*?)\s*\((\d{4})\)", heading.strip())
    if not match:
        return None, None

    return match.group(1).strip(), int(match.group(2))


def extract_movie_details_from_heading(heading):
    """Extract title, year, and director from a recommendation heading text."""
    if not heading:
        return None, None, None

    match = re.match(r"^(.*?)\s*\((\d{4})\)\s*[-–—]\s*(.*?)\s*$", heading.strip())
    if match:
        return match.group(1).strip(), int(match.group(2)), match.group(3).strip()

    title, year = extract_title_year_from_heading(heading)
    return title, year, None


def _normalize_watch_lookup(watched_lookup):
    normalized = set()
    for item in watched_lookup or []:
        if not item:
            continue
        if isinstance(item, dict):
            title = item.get("title")
            year = item.get("year")
        else:
            try:
                title, year = item
            except Exception:
                continue

        normalized_title = normalize_title_for_match(title)
        parsed_year = parse_year(year)
        if normalized_title and parsed_year:
            normalized.add((normalized_title, parsed_year))
    return normalized


def _format_recommendation_rating(rating):
    if rating is None:
        return "Curated Pick"

    try:
        rating_value = float(rating)
    except (TypeError, ValueError):
        return "Curated Pick"

    if rating_value <= 0:
        return "Curated Pick"

    return f"TMDB {rating_value:.1f}/10"


def _render_recommendation_card(item, watched_lookup):
    title = item.get("title") or "Untitled Recommendation"
    year = item.get("year")
    director = item.get("director") or "Unknown Director"
    genre = item.get("genre") or "Genre unavailable"
    why = item.get("why") or "No rationale provided."

    poster_details = {}
    if title and year:
        try:
            poster_details = tmdb_get_movie_details(title, year, manual_director=director) or {}
        except Exception:
            poster_details = {}

    poster = poster_details.get("poster") or "https://via.placeholder.com/500x750?text=No+Poster"
    poster_title = poster_details.get("title") or title
    display_rating = _format_recommendation_rating(poster_details.get("rating"))
    normalized_lookup = watched_lookup or set()
    is_watched = False
    if title and year:
        is_watched = (normalize_title_for_match(title), parse_year(year)) in normalized_lookup

    watched_badge = ' <span class="already-watched-badge">Already watched</span>' if is_watched else ""
    year_text = str(year) if year else "Year unavailable"

    return (
        '<article class="movie-frame">'
        f'<img src="{escape(poster)}" alt="{escape(poster_title)}" class="movie-poster" loading="lazy">'
        '<div class="frame-overlay">'
        '<div class="overlay-content">'
        f'<h3 class="frame-title">{escape(title)}</h3>'
        f'<div class="frame-meta"><span class="meta-item">{escape(year_text)}</span><span class="meta-item divider">•</span><span class="meta-item">{escape(director)}</span></div>'
        f'<div class="frame-genre">{escape(genre)}</div>'
        f'<div class="frame-rating">{escape(display_rating)}</div>'
        f'<div class="frame-summary"><strong>Why it fits:</strong> {escape(why)}</div>'
        '<div class="frame-actions">'
        f'<button class="action-btn" type="button" title="Log Watch" aria-label="Log Watch for {escape(title)}"><i class="fa-solid fa-eye"></i></button>'
        f'<button class="action-btn" type="button" title="Like" aria-label="Like {escape(title)}"><i class="fa-solid fa-heart"></i></button>'
        f'<button class="action-btn" type="button" title="Add to List" aria-label="Add {escape(title)} to list"><i class="fa-solid fa-plus"></i></button>'
        '</div>'
        f'<div class="frame-badge-row">{watched_badge}</div>'
        '</div>'
        '</div>'
        '</article>'
    )


def build_watched_title_year_lookup(movies):
    """Build a strict (title, year) set for already watched movies."""
    watched_lookup = set()
    for movie in movies or []:
        normalized_title = normalize_title_for_match(movie.get("movie"))
        year = parse_year(movie.get("p_year"))
        if normalized_title and year:
            watched_lookup.add((normalized_title, year))
    return watched_lookup


def build_user_taste_genome(movies):
    """Extract an articulated Taste Genome & Cinematic DNA profile from user watch history."""
    if not movies:
        return {
            "summary": "No watch history available.",
            "top_directors": [],
            "top_genres": [],
            "primary_era": "Balanced",
            "anti_preferences": [],
            "anchor_favorites": [],
        }

    positive_movies = []
    disliked_movies = []
    director_counts = {}
    genre_ratings = {}
    era_counts = {"Pre-1980s": 0, "80s-90s": 0, "2000s-2010s": 0, "2020+ Contemporary": 0}
    tv_count = 0
    movie_count = 0
    rewatch_count = 0
    cinema_count = 0

    total_logged = len(movies)

    for m in movies:
        title = m.get("movie") or ""
        year = parse_year(m.get("p_year"))
        raw_r = m.get("rating")
        director = (m.get("director") or "").strip()
        genres_raw = m.get("genre") or ""

        if m.get("tv_show"):
            tv_count += 1
        else:
            movie_count += 1

        if str(m.get("rewatch") or "").strip() in ("1", "true", "True") or m.get("rewatch") in (1, True):
            rewatch_count += 1
        if str(m.get("cinema") or "").strip() in ("1", "true", "True") or m.get("cinema") in (1, True):
            cinema_count += 1

        if year:
            if year < 1980:
                era_counts["Pre-1980s"] += 1
            elif 1980 <= year < 2000:
                era_counts["80s-90s"] += 1
            elif 2000 <= year < 2020:
                era_counts["2000s-2010s"] += 1
            else:
                era_counts["2020+ Contemporary"] += 1

        r_val = None
        if raw_r is not None:
            try:
                r_val = float(raw_r)
                if r_val > 5.0:
                    r_val = r_val / 2.0  # Normalize legacy 1-10 to 1-5 scale
            except (TypeError, ValueError):
                r_val = None

        if director and director.lower() != "unknown":
            if r_val is None or r_val >= 3.5:
                director_counts[director] = director_counts.get(director, 0) + 1

        for g in [x.strip() for x in genres_raw.split(",") if x.strip()]:
            if r_val is not None:
                genre_ratings.setdefault(g, []).append(r_val)

        raw_vdate = m.get("v_date")
        v_date_str = ""
        if raw_vdate:
            try:
                v_date_str = raw_vdate.isoformat() if hasattr(raw_vdate, "isoformat") else str(raw_vdate).strip()
            except Exception:
                v_date_str = str(raw_vdate).strip()

        if r_val is not None:
            if r_val >= 4.0:
                positive_movies.append((title, year, director, r_val, v_date_str))
            elif r_val <= 2.5:
                disliked_movies.append((title, year, director, r_val, v_date_str))
        else:
            positive_movies.append((title, year, director, None, v_date_str))

    top_directors = [d[0] for d in sorted(director_counts.items(), key=lambda x: x[1], reverse=True)[:5]]

    import math
    genre_affinities = []
    disliked_genres = []
    min_count_req = 2 if total_logged >= 5 else 1

    for g, ratings in genre_ratings.items():
        count = len(ratings)
        avg = sum(ratings) / count
        if count >= 2 and avg <= 2.5:
            disliked_genres.append(g)
        elif avg >= 3.5 and count >= min_count_req:
            weighted_score = avg * math.log2(1 + count)
            genre_affinities.append((g, avg, count, weighted_score))

    sorted_genres = sorted(genre_affinities, key=lambda x: x[3], reverse=True)[:5]
    top_genre_strs = [f"{g[0]} ({g[1]:.1f}★)" for g in sorted_genres]

    top_eras = [era for era, count in sorted(era_counts.items(), key=lambda x: x[1], reverse=True) if count > 0]
    primary_era = top_eras[0] if top_eras else "Balanced"

    sorted_pos = sorted([m for m in positive_movies if m[3] is not None], key=lambda x: (x[3], x[4]), reverse=True)
    anchor_favorites = [f"{m[0]} ({m[1] or 'N/A'}) - {m[2]}" for m in sorted_pos[:5]]

    summary_lines = []
    summary_lines.append(f"CINEMATIC PROFILE: {total_logged} total items logged ({movie_count} movies, {tv_count} TV shows). Primary Era: {primary_era}.")
    
    if top_genre_strs:
        summary_lines.append(f"TOP GENRE AFFINITIES: {', '.join(top_genre_strs)}")
    if top_directors:
        summary_lines.append(f"FAVORITE DIRECTORS/CREATORS: {', '.join(top_directors)}")
    if anchor_favorites:
        summary_lines.append(f"ANCHOR FAVORITES (User Loved & Rated Highest Recently): {'; '.join(anchor_favorites)}")
    
    engagement_traits = []
    if rewatch_count > 2:
        engagement_traits.append(f"High Rewatch Propensity ({rewatch_count} rewatches logged)")
    if cinema_count > 2:
        engagement_traits.append(f"Theatrical Cinema Enthusiast ({cinema_count} theatrical viewings)")
    if engagement_traits:
        summary_lines.append(f"WATCHING HABITS: {'; '.join(engagement_traits)}")

    if disliked_movies or disliked_genres:
        dislike_str = []
        if disliked_genres:
            dislike_str.append(f"Low-rated genres: {', '.join(disliked_genres)}")
        if disliked_movies:
            dislike_str.append(f"Disliked titles: {', '.join([m[0] for m in disliked_movies[:4]])}")
        summary_lines.append(f"ANTI-PREFERENCES (AVOID THESE TROPES/STYLES): {'; '.join(dislike_str)}")

    summary = "\n".join(summary_lines)

    return {
        "summary": summary,
        "top_directors": top_directors,
        "top_genres": [g[0] for g in sorted_genres],
        "primary_era": primary_era,
        "anti_preferences": disliked_movies,
        "anchor_favorites": anchor_favorites,
    }


def build_vibe_matrix_instructions(media_type="both", tone=3, pace=3, distance=3):
    """Convert quantitative vibe slider values into structured LLM instructions."""
    mt = str(media_type or "both").lower()
    mt_instructions = {
        "movie": "Target ONLY Feature Films (Movies). Do NOT recommend TV Series or Shows.",
        "tv": "Target ONLY TV Shows, Series, or Limited Series. Do NOT recommend Feature Films.",
        "both": "Feel free to recommend a balanced mix of Feature Films and TV Series.",
    }.get(mt, "Recommend Feature Films or TV Series.")

    try:
        tone_val = int(tone)
    except Exception:
        tone_val = 3
    if tone_val <= 2:
        tone_str = "Atmosphere: Dark, gritty, unsettling, intense, or noir."
    elif tone_val >= 4:
        tone_str = "Atmosphere: Light, comforting, uplifting, cozy, or feel-good."
    else:
        tone_str = "Atmosphere: Balanced tone."

    try:
        pace_val = int(pace)
    except Exception:
        pace_val = 3
    if pace_val <= 2:
        pace_str = "Narrative Pace: Slow-burn, atmospheric, meditative, deep character focus."
    elif pace_val >= 4:
        pace_str = "Narrative Pace: High-octane, fast-paced, relentless, adrenaline-packed."
    else:
        pace_str = "Narrative Pace: Standard cinematic pacing."

    try:
        dist_val = int(distance)
    except Exception:
        dist_val = 3
    if dist_val <= 2:
        dist_str = "Discovery Distance: Stay in user's familiar comfort zone."
    elif dist_val >= 4:
        dist_str = "Discovery Distance: Deep Cuts & Uncharted Gems. Prioritize lesser-known, cult, or underrated titles over massive mainstream blockbusters."
    else:
        dist_str = "Discovery Distance: Balanced blend of acclaimed hits and fresh discoveries."

    return f"- Media Format Constraint: {mt_instructions}\n- {tone_str}\n- {pace_str}\n- {dist_str}"


def build_user_watch_history_summary(
    movies,
    history_profile="balanced",
    max_cap=60,
    history_profile_labels=None,
):
    """Build a formatted watch-history summary based on the selected lens profile."""
    if not movies:
        return "No movies watched yet."

    labels = history_profile_labels or {
        "recent": "Recent Favorites",
        "balanced": "Balanced Mix",
        "all_time": "All-Time Profile",
    }

    profile = (history_profile or "balanced").strip().lower()
    if profile not in labels:
        profile = "balanced"

    # Work with a copy so callers keep their original ordering.
    ordered_movies = list(movies)
    ordered_movies.sort(key=lambda x: x["v_date"], reverse=True)

    total_movies = len(ordered_movies)

    recent_pool = ordered_movies[:24]
    rated_movies = [movie for movie in ordered_movies if isinstance(movie.get("rating"), (int, float))]
    top_rated_pool = sorted(rated_movies, key=lambda x: x.get("rating", 0), reverse=True)

    selected_movies = []
    selected_keys = set()

    def append_unique(candidate):
        key = (
            normalize_title_for_match(candidate.get("movie")),
            parse_year(candidate.get("p_year")),
            candidate.get("v_date"),
        )
        if key in selected_keys:
            return
        selected_keys.add(key)
        selected_movies.append(candidate)

    if profile == "recent":
        for movie in recent_pool[:24]:
            append_unique(movie)
    elif profile == "all_time":
        for movie in ordered_movies[:max_cap]:
            append_unique(movie)
    else:
        for movie in recent_pool[:16]:
            append_unique(movie)
        for movie in top_rated_pool[:12]:
            append_unique(movie)
        selected_movies = selected_movies[:24]

    if not selected_movies:
        selected_movies = ordered_movies[: min(total_movies, 15)]

    lens_label = labels.get(profile, "Balanced Mix")
    summary = (
        f"Watch history lens: {lens_label} "
        f"({len(selected_movies)} picked from {total_movies} total entries):\n"
    )
    sentiment_map = {1: "Trash (1/5)", 2: "Skippable (2/5)", 3: "Mid (3/5)", 4: "Great (4/5)", 5: "Masterpiece (5/5)"}
    for idx, movie in enumerate(selected_movies, 1):
        raw_r = movie.get("rating")
        r_val = int(raw_r) if isinstance(raw_r, (int, float)) else None
        if r_val and r_val > 5:
            r_val = math.ceil(r_val / 2.0)
        rating_text = sentiment_map.get(r_val, "unrated") if r_val else "unrated"
        summary += (
            f"{idx}. {movie['movie']} ({movie['p_year']}) | "
            f"dir: {movie['director']} | genres: {movie['genre']} | rating: {rating_text}\n"
        )

    rated_selected_movies = [movie for movie in selected_movies if isinstance(movie.get("rating"), (int, float))]
    if selected_movies:
        avg_rating = 0
        if rated_selected_movies:
            avg_rating = sum(movie["rating"] for movie in rated_selected_movies) / len(rated_selected_movies)
        genres = {}
        for movie in selected_movies:
            if movie["genre"]:
                for genre in movie["genre"].split(", "):
                    genres[genre.strip()] = genres.get(genre.strip(), 0) + 1

        top_genres = sorted(genres.items(), key=lambda x: x[1], reverse=True)[:3]
        summary += f"\nAverage rating in this lens: {avg_rating:.1f}/5 stars\n"
        if top_genres:
            summary += f"Most watched genres in this lens: {', '.join([genre[0] for genre in top_genres])}\n"

    return summary


def _extract_text_from_openrouter_content(content):
    """Extract plain text from OpenRouter content variants (string/list/dict)."""
    if content is None:
        return None

    if isinstance(content, str):
        cleaned = content.strip()
        return cleaned if cleaned else None

    if isinstance(content, dict):
        for key in ("text", "output_text", "content", "value"):
            value = content.get(key)
            extracted = _extract_text_from_openrouter_content(value)
            if extracted:
                return extracted
        return None

    if isinstance(content, list):
        parts = []
        for item in content:
            extracted = _extract_text_from_openrouter_content(item)
            if extracted:
                parts.append(extracted)
        return "\n".join(parts).strip() if parts else None

    return None


def _extract_openrouter_message_text(payload):
    """Extract assistant text from OpenRouter payload and raise meaningful errors."""
    error_payload = payload.get("error")
    if error_payload:
        if isinstance(error_payload, dict):
            message = error_payload.get("message") or error_payload.get("code") or str(error_payload)
        else:
            message = str(error_payload)
        raise ValueError(f"OpenRouter error: {message}")

    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("OpenRouter response missing choices")

    choice = choices[0] or {}
    message = choice.get("message") or {}

    response_text = _extract_text_from_openrouter_content(message.get("content"))
    if not response_text:
        response_text = _extract_text_from_openrouter_content(choice.get("text"))
    if not response_text:
        response_text = _extract_text_from_openrouter_content(message.get("reasoning"))
    if not response_text:
        response_text = _extract_text_from_openrouter_content(payload.get("output"))

    if not response_text:
        finish_reason = choice.get("finish_reason")
        if finish_reason:
            raise ValueError(f"OpenRouter returned empty content (finish_reason={finish_reason})")
        raise ValueError("OpenRouter response missing message content")

    return response_text


def _build_openrouter_provider_preferences(settings):
    return {
        "allow_fallbacks": getattr(settings, "provider_allow_fallbacks", True)
    }


def _is_retryable_openrouter_status(status_code):
    return status_code in {408, 429, 500, 502, 503, 504}


def _build_openrouter_model_candidates(settings):
    """Build ordered model candidates: primary first, then configured fallbacks."""
    candidates = []
    for model_id in [settings.model_id, *settings.model_fallbacks]:
        cleaned = str(model_id).strip()
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)
    return candidates


def _extract_json_array_from_text(text):
    """Extract and parse a JSON array from LLM response text, with trailing comma cleaning and regex object fallback."""
    if not text:
        return None

    cleaned = re.sub(r"<think>.*?</think>", "", str(text), flags=re.DOTALL)
    cleaned = re.sub(r"```json", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, list) and len(data) > 0:
            return data
    except Exception:
        pass

    # Find slice from first '[' to last ']'
    start_idx = cleaned.find("[")
    end_idx = cleaned.rfind("]")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_candidate = cleaned[start_idx : end_idx + 1]
        # Clean trailing commas
        json_candidate = re.sub(r",\s*([\]}])", r"\1", json_candidate)
        try:
            data = json.loads(json_candidate)
            if isinstance(data, list) and len(data) > 0:
                return data
        except Exception:
            pass

    # Robust regex object extractor fallback
    items = []
    for match in re.finditer(r'\{\s*"title"\s*:\s*"([^"]+)"\s*,\s*"year"\s*:\s*"?(\d{4})?"?\s*,\s*"director"\s*:\s*"([^"]+)"\s*\}', str(text)):
        items.append({
            "title": match.group(1).strip(),
            "year": match.group(2).strip() if match.group(2) else "",
            "director": match.group(3).strip()
        })
    if items:
        return items

    # General regex fallback for any JSON object containing "title"
    for match in re.finditer(r'\{\s*"title"\s*:\s*"([^"]+)"[^\}]*\}', str(text)):
        obj_str = match.group(0)
        try:
            obj_str = re.sub(r",\s*\}", "}", obj_str)
            obj = json.loads(obj_str)
            if obj.get("title"):
                items.append(obj)
        except Exception:
            pass

    return items if items else None


CURATED_FALLBACK_POOL = [
    {"title": "Parasite", "year": "2019", "director": "Bong Joon-ho", "media_type": "movie"},
    {"title": "Whiplash", "year": "2014", "director": "Damien Chazelle", "media_type": "movie"},
    {"title": "Blade Runner 2049", "year": "2017", "director": "Denis Villeneuve", "media_type": "movie"},
    {"title": "Everything Everywhere All at Once", "year": "2022", "director": "Daniel Kwan, Daniel Scheinert", "media_type": "movie"},
    {"title": "Drive", "year": "2011", "director": "Nicolas Winding Refn", "media_type": "movie"},
    {"title": "Dune: Part Two", "year": "2024", "director": "Denis Villeneuve", "media_type": "movie"},
    {"title": "Pulp Fiction", "year": "1994", "director": "Quentin Tarantino", "media_type": "movie"},
    {"title": "The Grand Budapest Hotel", "year": "2014", "director": "Wes Anderson", "media_type": "movie"},
    {"title": "Portrait of a Lady on Fire", "year": "2019", "director": "Céline Sciamma", "media_type": "movie"},
    {"title": "No Country for Old Men", "year": "2007", "director": "Joel Coen, Ethan Coen", "media_type": "movie"},
    {"title": "Nightcrawler", "year": "2014", "director": "Dan Gilroy", "media_type": "movie"},
    {"title": "Ex Machina", "year": "2014", "director": "Alex Garland", "media_type": "movie"},
    {"title": "Severance", "year": "2022", "director": "Dan Erickson", "media_type": "tv"},
    {"title": "Succession", "year": "2018", "director": "Jesse Armstrong", "media_type": "tv"},
    {"title": "The Bear", "year": "2022", "director": "Christopher Storer", "media_type": "tv"},
    {"title": "Chernobyl", "year": "2019", "director": "Craig Mazin", "media_type": "tv"},
    {"title": "Fargo", "year": "2014", "director": "Noah Hawley", "media_type": "tv"},
    {"title": "True Detective", "year": "2014", "director": "Nic Pizzolatto", "media_type": "tv"},
    {"title": "Dark", "year": "2017", "director": "Baran bo Odar", "media_type": "tv"},
    {"title": "Mindhunter", "year": "2017", "director": "Joe Penhall", "media_type": "tv"}
]

def _generate_fallback_candidates(user_request, raw_movies, media_type="both"):
    """Generate smart local candidates from curated pool excluding user watch history."""
    import random
    candidates = []

    watched_titles = set()
    for m in (raw_movies or []):
        t = (m.get("movie") or "").strip().lower()
        if t:
            watched_titles.add(t)

    pool = []
    for item in CURATED_FALLBACK_POOL:
        t_clean = item["title"].strip().lower()
        if t_clean not in watched_titles:
            if media_type == "movie" and item.get("media_type") == "tv":
                continue
            if media_type == "tv" and item.get("media_type") == "movie":
                continue
            pool.append({"title": item["title"], "year": item["year"], "director": item["director"]})

    if pool:
        random.shuffle(pool)
        candidates = pool[:12]

    return candidates


def _is_fallback_worthy_openrouter_payload_error(exc):
    """Determine whether a structured OpenRouter payload error should trigger model fallback."""
    message = str(exc).lower()
    fallback_signals = (
        "no provider",
        "not available",
        "temporarily unavailable",
        "rate limit",
        "too many requests",
        "overloaded",
        "capacity",
        "quota",
    )
    return any(signal in message for signal in fallback_signals)


def _extract_openrouter_retry_after_seconds(response):
    """Extract Retry-After seconds from headers or error payload when available."""
    if response is None:
        return None

    retry_after_header = None
    try:
        retry_after_header = response.headers.get("Retry-After")
    except Exception:
        retry_after_header = None

    if retry_after_header:
        try:
            parsed = float(str(retry_after_header).strip())
            if parsed >= 0:
                return parsed
        except (TypeError, ValueError):
            pass

    try:
        payload = response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        error_payload = payload.get("error")
        if isinstance(error_payload, dict):
            message = str(error_payload.get("message") or "")
        elif error_payload is not None:
            message = str(error_payload)
        else:
            message = ""

        retry_match = re.search(r"retry(?:\s+after)?\s*(\d+(?:\.\d+)?)\s*s", message, flags=re.IGNORECASE)
        if retry_match:
            try:
                parsed = float(retry_match.group(1))
                if parsed >= 0:
                    return parsed
            except (TypeError, ValueError):
                return None

    return None


def _post_openrouter_request(headers, payload, settings, logger=None, deadline_seconds=None):
    """Perform OpenRouter request(s) with retry/backoff for transient provider errors."""
    started_at = time.monotonic()

    def _remaining_seconds():
        if deadline_seconds is None:
            return None
        return deadline_seconds - (time.monotonic() - started_at)

    for attempt in range(1, settings.max_attempts + 1):
        remaining_before_call = _remaining_seconds()
        if remaining_before_call is not None and remaining_before_call <= 0:
            raise TimeoutError(
                f"OpenRouter request exceeded {deadline_seconds:.0f}s deadline"
            )

        request_timeout = settings.request_timeout
        if remaining_before_call is not None:
            request_timeout = max(1.0, min(settings.request_timeout, remaining_before_call))

        try:
            response = requests.post(
                settings.api_url,
                headers=headers,
                json=payload,
                timeout=request_timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            response_obj = getattr(exc, "response", None)
            status_code = getattr(response_obj, "status_code", None)
            retry_after_seconds = _extract_openrouter_retry_after_seconds(response_obj)
            retryable = (
                isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError))
                or _is_retryable_openrouter_status(status_code)
            )

            if not retryable or attempt >= settings.max_attempts:
                if status_code == 429:
                    raise OpenRouterRateLimitError(wait_seconds=retry_after_seconds) from exc
                raise

            base_delay = min(
                settings.retry_max_delay,
                settings.retry_base_delay * (2 ** (attempt - 1)),
            )
            sleep_base = base_delay
            if status_code == 429:
                if retry_after_seconds is None:
                    retry_after_seconds = max(1.0, base_delay * 2)
                sleep_base = min(
                    settings.retry_429_max_delay,
                    max(base_delay, retry_after_seconds),
                )

            sleep_for = sleep_base + random.uniform(0, settings.retry_jitter)

            remaining_before_sleep = _remaining_seconds()
            if remaining_before_sleep is not None:
                if remaining_before_sleep <= 0:
                    raise TimeoutError(
                        f"OpenRouter request exceeded {deadline_seconds:.0f}s deadline"
                    )

                # Leave a small buffer before the deadline.
                sleep_for = min(sleep_for, max(0.0, remaining_before_sleep - 0.05))
                if sleep_for <= 0:
                    raise TimeoutError(
                        f"OpenRouter request exceeded {deadline_seconds:.0f}s deadline"
                    )

            _log_warning(
                logger,
                "OpenRouter request failed (attempt %s/%s, status=%s): %s. Retrying in %.2fs",
                attempt,
                settings.max_attempts,
                status_code,
                exc,
                sleep_for,
            )
            time.sleep(sleep_for)


def _post_openrouter_with_deadline(headers, payload, settings, logger=None, deadline_seconds=None):
    """Apply a hard deadline so AI calls cannot outlive Gunicorn worker timeout."""
    effective_deadline = settings.total_timeout if deadline_seconds is None else float(deadline_seconds)
    if effective_deadline <= 0:
        raise TimeoutError("OpenRouter request deadline must be greater than 0 seconds")
    return _post_openrouter_request(
        headers=headers,
        payload=payload,
        settings=settings,
        logger=logger,
        deadline_seconds=effective_deadline,
    )



def get_ai_movie_recommendation_stream(
    user_request,
    user_history,
    recommendation_mode="similar",
    preferred_genres=None,
    watched_lookup=None,
    history_profile="balanced",
    media_type="both",
    tone=3,
    pace=3,
    distance=3,
    mood_preset="",
    active_titles=None,
    raw_movies=None,
    *,
    api_key,
    app_base_url,
    settings,
    discover_config,
    logger=None,
):
    """Yield AI-powered media recommendation tokens using OpenRouter streaming with Taste Genome & Vibe Matrix."""
    if not api_key:
        yield "Error: OPENROUTER_API_KEY is not configured."
        return

    recommendation_mode = (recommendation_mode or "similar").strip().lower()
    if recommendation_mode not in discover_config.mode_prompts:
        recommendation_mode = "similar"

    selected_genres = []
    for genre in preferred_genres or []:
        cleaned_genre = str(genre).strip()
        if (
            cleaned_genre
            and cleaned_genre in discover_config.available_genres
            and cleaned_genre not in selected_genres
        ):
            selected_genres.append(cleaned_genre)

    mode_label = discover_config.mode_labels.get(recommendation_mode, "Similar")
    mode_prompt = discover_config.mode_prompts[recommendation_mode]

    history_profile = (history_profile or "balanced").strip().lower()
    if history_profile not in discover_config.history_profile_prompts:
        history_profile = "balanced"
    history_label = discover_config.history_profile_labels.get(history_profile, "Balanced Mix")
    history_prompt = discover_config.history_profile_prompts[history_profile]

    watched_set = _normalize_watch_lookup(watched_lookup)
    vibe_instructions = build_vibe_matrix_instructions(media_type, tone, pace, distance)
    genome_info = build_user_taste_genome(raw_movies or [])
    genome_summary = genome_info.get("summary", "Standard taste profile.")

    prompt_step1 = f"""You are a world-class film & TV curator.

PRIMARY MANDATE - USER SPECIFIC PROMPT:
"{user_request}" (CRITICAL: Every candidate generated MUST match this specific theme, genre, mood, or request above. If the request asks for "mind-bending sci-fi", ALL candidates must be mind-bending sci-fi!)

CRITICAL NEGATIVE CONSTRAINT:
DO NOT recommend any titles listed in USER RECENT WATCH HISTORY below:
{user_history}

USER TASTE GENOME & HISTORY MATRIX:
{genome_summary}

VIBE MATRIX PARAMETERS:
{vibe_instructions}

RECOMMENDATION MODE: {mode_label} ({mode_prompt})
HISTORY LENS: {history_label} ({history_prompt})

Return ONLY a valid JSON array of 12 candidate objects. Do not include markdown formatting, backticks, or text before/after the JSON.
Format:
[
  {{"title": "Exact Title", "year": "YYYY", "director": "Director or Creator Name"}}
]

Generate exactly 12 diverse candidates matching the user prompt and format ({media_type})."""

    import json
    import requests
    import re

    candidates = []
    gemini_api_key = os.environ.get("GEMINI_API_KEY")

    # Primary: Google Gemini API
    print(f"[DEBUG] GEMINI_API_KEY present: {bool(gemini_api_key)}")
    gemini_models = ["gemini-flash-lite-latest", "gemini-2.5-flash"]
    if gemini_api_key:
        for g_model in gemini_models:
            try:
                gem_payload = {
                    "model": g_model,
                    "messages": [{"role": "user", "content": prompt_step1}],
                    "max_tokens": 2000,
                }
                gem_headers = {
                    "Authorization": f"Bearer {gemini_api_key}",
                    "Content-Type": "application/json",
                }
                resp = requests.post(
                    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                    headers=gem_headers,
                    json=gem_payload,
                    timeout=25,
                )
                print(f"[DEBUG] Step 1 model={g_model} status={resp.status_code}")
                if resp.status_code == 200:
                    content = _extract_openrouter_message_text(resp.json())
                    print(f"[DEBUG] Step 1 raw LLM response text:\n{content}")
                    parsed = _extract_json_array_from_text(content)
                    print(f"[DEBUG] Step 1 JSON array parse result: {parsed}")
                    if parsed and isinstance(parsed, list) and len(parsed) > 0:
                        candidates = parsed
                        print(f"[DEBUG] Successfully loaded {len(candidates)} candidates via Gemini model {g_model}")
                        break
                    else:
                        print(f"[DEBUG] Could not parse JSON array from Gemini model {g_model} text")
                else:
                    print(f"[DEBUG] Gemini API Step 1 status error: {resp.text}")
                    if logger:
                        logger.warning(f"Gemini API Step 1 ({g_model}) status {resp.status_code}: {resp.text}")
            except Exception as e:
                print(f"[DEBUG] Gemini API Step 1 exception: {e}")
                if logger:
                    logger.warning(f"Gemini API Step 1 ({g_model}) candidate generation failed: {e}")

    if not candidates:
        print("[DEBUG] Gemini candidate generation returned no candidates! Triggering curated fallback pool...")
        candidates = _generate_fallback_candidates(user_request, raw_movies, media_type)
        print(f"[DEBUG] Generated {len(candidates)} fallback candidates: {[c.get('title') for c in candidates]}")
        if not candidates:
            print("[DEBUG] Failed to generate candidates")
            yield "Error: Failed to generate candidates."
            return

    watched_titles_only = set([re.sub(r'[^a-z0-9\s]', '', (m.get("movie") or "").lower()).strip() for m in (raw_movies or []) if m.get("movie")])
    active_set = set([re.sub(r'[^a-z0-9\s]', '', (t or "").lower()).strip() for t in (active_titles or []) if t])

    # Validate candidates with TMDB
    valid_movies = []
    for candidate in candidates:
        title = candidate.get("title", "")
        year = candidate.get("year", "")
        director = candidate.get("director", "")
        if not title:
            continue

        try:
            details = tmdb_get_movie_details(title, year, manual_director=director)
            if details:
                real_title = details.get("title") or title
                real_year = str(details.get("p_year") or year or "")
                real_director = details.get("director") or director or "Unknown"
            else:
                real_title = title
                real_year = str(year or "")
                real_director = director or "Unknown"

            title_clean = re.sub(r'[^a-z0-9\s]', '', real_title.lower()).strip()
            title_clean = re.sub(r'\s+', ' ', title_clean)
            lookup_key = f"{title_clean}::{real_year}"

            if lookup_key not in watched_set and title_clean not in watched_titles_only and title_clean not in active_set:
                valid_movies.append({
                    "title": real_title,
                    "year": real_year,
                    "director": real_director
                })
        except Exception:
            valid_movies.append({
                "title": title,
                "year": str(year or ""),
                "director": director or "Unknown"
            })

        if len(valid_movies) == 4:
            break

    print(f"[DEBUG] Validated {len(valid_movies)} movies for Step 2 streaming: {[m['title'] for m in valid_movies]}")

    if not valid_movies:
        yield "Error: Could not validate any candidates against TMDB."
        return

    # Step 2: Stream the validated movies with Counterfactual Rationale
    validated_list_str = ""
    for idx, vm in enumerate(valid_movies, 1):
        dir_name = vm.get('director', '').strip() or 'Unknown Director'
        validated_list_str += f"{idx}. {vm['title']} ({vm.get('year', '')}) - {dir_name}\n"

    prompt_step2 = f"""User Request: {user_request}
Vibe Matrix Parameters:
{vibe_instructions}

I have found {len(valid_movies)} verified candidates matching the user request and constraints:
{validated_list_str}

Your task is to write a Score (e.g. 96/100) and a 1-liner comment with a Counterfactual Rationale for EACH of these {len(valid_movies)} EXACT candidates.
CRITICAL: You MUST ONLY use the {len(valid_movies)} items listed above. DO NOT invent, hallucinate, or swap titles.

Format EXACTLY like this for each item:
1. **[Exact Title from list] ([Exact Year from list]) - [Exact Director/Creator from list]**
   Score: [Score e.g. 95/100]
   Comment: [Punchy 1-liner explanation + Counterfactual Rationale: "Chosen over [Mainstream Alternative] because..."]

2. **[Next Title] ([Year]) - [Director]**
...
"""

    # Primary: Stream via Google Gemini API
    if gemini_api_key:
        for g_model in gemini_models:
            try:
                gem_payload = {
                    "model": g_model,
                    "messages": [{"role": "user", "content": prompt_step2}],
                    "max_tokens": getattr(settings, "max_completion_tokens", 1000),
                    "stream": True,
                }
                gem_headers = {
                    "Authorization": f"Bearer {gemini_api_key}",
                    "Content-Type": "application/json",
                }
                response = requests.post(
                    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                    headers=gem_headers,
                    json=gem_payload,
                    timeout=30,
                    stream=True,
                )
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if line:
                            decoded_line = line.decode('utf-8')
                            if decoded_line.startswith('data: '):
                                data_str = decoded_line[6:].strip()
                                if data_str == '[DONE]':
                                    break
                                try:
                                    data_json = json.loads(data_str)
                                    choices = data_json.get('choices', [])
                                    if choices:
                                        delta = choices[0].get('delta', {})
                                        token = delta.get('content', '')
                                        if token:
                                            yield token
                                except Exception:
                                    pass
                    return
                else:
                    if logger:
                        logger.warning(f"Gemini Step 2 ({g_model}) status {response.status_code}: {response.text}")
            except Exception as e:
                if logger:
                    logger.warning(f"Gemini API Step 2 ({g_model}) streaming failed: {e}")


def get_single_card_replacement_stream(
    user_request,
    user_history,
    active_titles=None,
    rejected_title="",
    media_type="both",
    tone=3,
    pace=3,
    distance=3,
    watched_lookup=None,
    raw_movies=None,
    *,
    api_key,
    app_base_url,
    settings,
    discover_config,
    logger=None,
):
    watched_set = _normalize_watch_lookup(watched_lookup)
    active_set = set([normalize_title_for_match(t) for t in (active_titles or []) if t])
    if rejected_title:
        active_set.add(normalize_title_for_match(rejected_title))

    vibe_instructions = build_vibe_matrix_instructions(media_type, tone, pace, distance)
    avoid_str = ", ".join(active_titles or []) if active_titles else "None"

    prompt_step1 = f"""You are a movie & TV recommendation expert. Generate 5 replacement candidates for a user who rejected "{rejected_title}".

User Request: {user_request}
Vibe Matrix:
{vibe_instructions}

DO NOT recommend any of the following titles: {avoid_str} or previously watched items.

Return ONLY a valid JSON array:
[
  {{"title": "Title", "year": "2023", "director": "Director/Creator"}}
]"""

    import json
    import requests
    import re

    candidates = []
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    gemini_models = ["gemini-flash-lite-latest", "gemini-2.5-flash"]

    if gemini_api_key:
        for g_model in gemini_models:
            try:
                gem_payload = {
                    "model": g_model,
                    "messages": [{"role": "user", "content": prompt_step1}],
                    "max_tokens": 500,
                }
                gem_headers = {
                    "Authorization": f"Bearer {gemini_api_key}",
                    "Content-Type": "application/json",
                }
                resp = requests.post(
                    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                    headers=gem_headers,
                    json=gem_payload,
                    timeout=15,
                )
                if resp.status_code == 200:
                    content = _extract_openrouter_message_text(resp.json())
                    parsed = _extract_json_array_from_text(content)
                    if parsed and isinstance(parsed, list) and len(parsed) > 0:
                        candidates = parsed
                        break
            except Exception as e:
                if logger:
                    logger.warning(f"Gemini Swap Step 1 ({g_model}) failed: {e}")

    print(f"[DEBUG] recommend_swap candidates from Step 1: {[c.get('title') for c in (candidates or [])]}")

    if not candidates:
        if raw_movies:
            candidates = _generate_fallback_candidates(user_request, raw_movies, media_type)
        if not candidates:
            yield "Error: Could not generate replacement candidate."
            return

    valid_item = None
    for candidate in candidates:
        title = candidate.get("title", "")
        year = candidate.get("year", "")
        director = candidate.get("director", "")
        if not title or normalize_title_for_match(title) in active_set:
            continue
        try:
            details = tmdb_get_movie_details(title, year, manual_director=director)
            real_title = (details.get("title") if details else None) or title
            real_year = str((details.get("p_year") if details else None) or year or "")
            real_director = (details.get("director") if details else None) or director or "Unknown"

            lookup_key = f"{normalize_title_for_match(real_title)}::{real_year}"
            if lookup_key not in watched_set:
                valid_item = {
                    "title": real_title,
                    "year": real_year,
                    "director": real_director
                }
                break
        except Exception:
            valid_item = {
                "title": title,
                "year": str(year or ""),
                "director": director or "Unknown"
            }
            break

    if not valid_item:
        # Pick first candidate not in active_set
        for candidate in candidates:
            title = candidate.get("title", "")
            if title and normalize_title_for_match(title) not in active_set:
                valid_item = {
                    "title": title,
                    "year": str(candidate.get("year", "")),
                    "director": candidate.get("director", "Unknown")
                }
                break

    print(f"[DEBUG] recommend_swap valid_item chosen: {valid_item}")

    if not valid_item:
        yield "Error: Could not validate replacement candidate against TMDB."
        return

    prompt_step2 = f"""User Request: {user_request}

Provide a score and a 1-liner comment for this single verified replacement candidate:
1. **{valid_item['title']} ({valid_item['year']}) - {valid_item['director']}**

Format:
1. **{valid_item['title']} ({valid_item['year']}) - {valid_item['director']}**
   Score: [Score e.g. 95/100]
   Comment: [Punchy 1-liner replacement rationale]
"""

    if gemini_api_key:
        for g_model in gemini_models:
            try:
                gem_payload = {
                    "model": g_model,
                    "messages": [{"role": "user", "content": prompt_step2}],
                    "max_tokens": 300,
                    "stream": True,
                }
                gem_headers = {
                    "Authorization": f"Bearer {gemini_api_key}",
                    "Content-Type": "application/json",
                }
                response = requests.post(
                    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                    headers=gem_headers,
                    json=gem_payload,
                    timeout=20,
                    stream=True,
                )
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if line:
                            decoded_line = line.decode('utf-8')
                            if decoded_line.startswith('data: '):
                                data_str = decoded_line[6:].strip()
                                if data_str == '[DONE]':
                                    break
                                try:
                                    data_json = json.loads(data_str)
                                    choices = data_json.get('choices', [])
                                    if choices:
                                        delta = choices[0].get('delta', {})
                                        token = delta.get('content', '')
                                        if token:
                                            yield token
                                except Exception:
                                    pass
                    return
            except Exception as e:
                if logger:
                    logger.warning(f"Gemini Swap Step 2 ({g_model}) streaming failed: {e}")



def get_ai_movie_recommendation(
    user_request,
    user_history,
    recommendation_mode="similar",
    preferred_genres=None,
    watched_lookup=None,
    history_profile="balanced",
    *,
    api_key,
    app_base_url,
    settings,
    discover_config,
    logger=None,
):
    """Get AI-powered movie recommendations using OpenRouter."""
    if not api_key:
        return (
            "<p>Sorry, recommendation service is not configured.</p>"
            "<p><strong>Error:</strong> OPENROUTER_API_KEY is not configured.</p>"
        )

    recommendation_mode = (recommendation_mode or "similar").strip().lower()
    if recommendation_mode not in discover_config.mode_prompts:
        recommendation_mode = "similar"

    selected_genres = []
    for genre in preferred_genres or []:
        cleaned_genre = str(genre).strip()
        if (
            cleaned_genre
            and cleaned_genre in discover_config.available_genres
            and cleaned_genre not in selected_genres
        ):
            selected_genres.append(cleaned_genre)

    mode_label = discover_config.mode_labels.get(recommendation_mode, "Similar")
    mode_prompt = discover_config.mode_prompts[recommendation_mode]
    genre_prompt = ", ".join(selected_genres) if selected_genres else "No explicit genre pre-filter selected."

    history_profile = (history_profile or "balanced").strip().lower()
    if history_profile not in discover_config.history_profile_prompts:
        history_profile = "balanced"
    history_label = discover_config.history_profile_labels.get(history_profile, "Balanced Mix")
    history_prompt = discover_config.history_profile_prompts[history_profile]

    prompt = f"""You are a movie recommendation expert. Based on the user's watch history and their request, provide 3-5 specific movie recommendations.

User's Recent Watch History:
{user_history}

User's Request: {user_request}

Recommendation Mode: {mode_label}
Mode Instructions: {mode_prompt}
History Lens: {history_label}
History Lens Instructions: {history_prompt}
Preferred Genres: {genre_prompt}

Please provide exactly 4 movie recommendations in the following format:
1. **[Movie Title] ([Year]) - [Director]**
   Score: [Your Score e.g. 95/100]
   Comment: [A brief, punchy one-liner explaining why it fits perfectly]

2. **[Movie Title] ([Year]) - [Director]**
   Score: [Your Score e.g. 95/100]
   Comment: [A brief, punchy one-liner explaining why it fits perfectly]

[Continue for exactly 4 movies]

Keep recommendations diverse and consider the user's rating patterns and favorite genres.
If preferred genres are provided, prioritize those genres in all recommendations.
Avoid recommending exact title+year combinations already listed in watch history when possible."""

    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if gemini_api_key:
        gemini_models = ["gemini-2.5-flash", "gemini-2.0-flash"]
        for g_model in gemini_models:
            try:
                gem_payload = {
                    "model": g_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": getattr(settings, "max_completion_tokens", 1000),
                }
                gem_headers = {
                    "Authorization": f"Bearer {gemini_api_key}",
                    "Content-Type": "application/json",
                }
                resp = requests.post(
                    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                    headers=gem_headers,
                    json=gem_payload,
                    timeout=15,
                )
                if resp.status_code == 200:
                    response_text = _extract_openrouter_message_text(resp.json())
                    if response_text and response_text.strip():
                        return format_ai_recommendation(response_text)
            except Exception as e:
                if logger:
                    logger.warning(f"Gemini API non-stream ({g_model}) failed: {e}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": app_base_url,
        "X-Title": "Kineto",
        "Content-Type": "application/json",
    }
    model_candidates = [settings.model_id, *settings.model_fallbacks]
    try:
        overall_started_at = time.monotonic()
        overall_deadline = max(1.0, float(settings.total_timeout))
        last_rate_limit_exc = None
        last_exc = None

        for model_index, model_id in enumerate(model_candidates):
            elapsed = time.monotonic() - overall_started_at
            remaining_overall = overall_deadline - elapsed
            if remaining_overall <= 0:
                raise TimeoutError(
                    f"OpenRouter request exceeded {overall_deadline:.0f}s deadline"
                )

            model_deadline = remaining_overall
            if len(model_candidates) > 1:
                model_deadline = min(remaining_overall, max(1.0, settings.model_deadline))

            request_payload = {
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "max_completion_tokens": settings.max_completion_tokens,
                # Keep max_tokens as a compatibility fallback for providers that still expect it.
                "max_tokens": settings.max_completion_tokens,
            }
            request_payload["provider"] = _build_openrouter_provider_preferences(settings)
            if settings.service_tier:
                request_payload["service_tier"] = settings.service_tier

            has_more_models = model_index < len(model_candidates) - 1

            try:
                response_payload = _post_openrouter_with_deadline(
                    headers=headers,
                    payload=request_payload,
                    settings=settings,
                    logger=logger,
                    deadline_seconds=model_deadline,
                )
                response_text = _extract_openrouter_message_text(response_payload)

                if model_index > 0:
                    _log_info(
                        logger,
                        "OpenRouter succeeded with fallback model %s after %s prior failure(s)",
                        model_id,
                        model_index,
                    )

                return format_ai_response_to_html(response_text, watched_lookup=watched_lookup)

            except OpenRouterRateLimitError as exc:
                last_rate_limit_exc = exc
                last_exc = exc
                if has_more_models:
                    _log_warning(
                        logger,
                        "OpenRouter model %s hit rate limit. Trying fallback model %s",
                        model_id,
                        model_candidates[model_index + 1],
                    )
                    continue
                raise

            except TimeoutError as exc:
                last_exc = exc
                if has_more_models:
                    _log_warning(
                        logger,
                        "OpenRouter model %s timed out after %.2fs. Trying fallback model %s",
                        model_id,
                        model_deadline,
                        model_candidates[model_index + 1],
                    )
                    continue
                raise

            except requests.exceptions.RequestException as exc:
                last_exc = exc
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if has_more_models and _is_retryable_openrouter_status(status_code):
                    _log_warning(
                        logger,
                        "OpenRouter model %s failed with status=%s. Trying fallback model %s",
                        model_id,
                        status_code,
                        model_candidates[model_index + 1],
                    )
                    continue
                raise

            except ValueError as exc:
                last_exc = exc
                if has_more_models and _is_fallback_worthy_openrouter_payload_error(exc):
                    _log_warning(
                        logger,
                        "OpenRouter model %s returned payload error (%s). Trying fallback model %s",
                        model_id,
                        exc,
                        model_candidates[model_index + 1],
                    )
                    continue
                raise

        if last_rate_limit_exc is not None:
            raise last_rate_limit_exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("OpenRouter request failed without a specific error")

    except OpenRouterRateLimitError as rate_limit_exc:
        _log_warning(logger, "OpenRouter rate-limit while generating recommendations: %s", rate_limit_exc)
        wait_seconds = rate_limit_exc.wait_seconds
        if wait_seconds is None:
            hint = "Please wait a few seconds and try again."
        else:
            hint = f"Please wait about {max(1, int(round(wait_seconds)))} seconds and try again."
        return (
            "<p>Sorry, recommendation service is temporarily rate-limited.</p>"
            f"<p><strong>Details:</strong> {hint}</p>"
        )

    except TimeoutError as timeout_exc:
        _log_warning(logger, "OpenRouter timeout while generating recommendations: %s", timeout_exc)
        return (
            "<p>Sorry, recommendation service is taking too long right now.</p>"
            "<p><strong>Details:</strong> Please try again in a moment.</p>"
        )

    except Exception as exc:
        _log_exception(logger, "Error getting AI recommendations from OpenRouter: %s", exc)
        return (
            "<p>Sorry, I couldn't generate recommendations at the moment.</p>"
            f"<p><strong>Error:</strong> {str(exc)}</p>"
        )


def format_ai_response_to_html(text, watched_lookup=None):
    """Convert AI response text into glass-frame movie cards."""
    watched_lookup = _normalize_watch_lookup(watched_lookup)

    items = []
    footer_lines = []
    current_item = None

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        title_match = re.match(r"^\d+\.\s*\*\*(.*?)\*\*", line)
        if title_match:
            if current_item:
                items.append(current_item)

            heading = title_match.group(1).strip()
            title, year, director = extract_movie_details_from_heading(heading)
            current_item = {
                "title": title or heading,
                "year": year,
                "director": director,
                "genre": "",
                "why": "",
                "extra": [],
            }
            continue

        if current_item is None:
            footer_lines.append(line)
            continue

        if line.startswith("Score:"):
            current_item["rating"] = line.split(":", 1)[1].strip()
        elif line.startswith("Comment:"):
            current_item["why"] = line.split(":", 1)[1].strip()
        else:
            current_item["extra"].append(line)

    if current_item:
        items.append(current_item)

    items = items[:4]

    if not items:
        return f'<div class="movie-gallery movie-gallery-empty"><p class="recommendation-empty">{escape(text or "")}</p></div>'

    html_cards = []
    for item in items:
        if len(html_cards) >= 4:
            break
        if item["extra"]:
            extra_text = " ".join(item["extra"]).strip()
            if extra_text:
                item["why"] = f"{item['why']} {extra_text}".strip() if item["why"] else extra_text
        html_cards.append(_render_recommendation_card(item, watched_lookup))

    html_output = ["<section class=\"movie-gallery\">", *html_cards, "</section>"]

    if footer_lines:
        footer = " ".join(footer_lines).strip()
        if footer:
            html_output.append(f'<p class="recommendation-epilogue">{escape(footer)}</p>')

    return "\n".join(html_output)
