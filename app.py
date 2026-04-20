from flask import Flask, render_template, jsonify, request, flash, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
import requests
import re
import random
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from functools import wraps
from bs4 import BeautifulSoup
from tmdbv3api import TMDb, Movie, TV, Season
from flask_mail import Mail, Message
from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from auth.auth import auth # Import the auth blueprint
from auth.restore import restore # Import the restore blueprint
from dotenv import load_dotenv

# Load environment variables from .env before importing database module.
load_dotenv()

from database import *
import datetime

# ========================================
# APP CONFIGURATION
# ========================================

tmdb = TMDb()
tmdb.api_key = os.environ.get('TMDB_API_KEY')

app = Flask(__name__)
# Register the auth blueprint with the main app
app.register_blueprint(auth)

app.secret_key = os.environ.get('FLASK_SECRET_KEY')

# Enable CSRF protection for all forms
csrf = CSRFProtect(app)

# Rate limiting to prevent brute-force attacks
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["1000 per day", "50 per hour"],
    storage_uri="memory://"
)

# ========================================
# LOGIN REQUIRED DECORATOR
# ========================================

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedin' not in session:
            flash('Please log in to access this page', category='error')
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

# ========================================
# EMAIL CONFIGURATION
# ========================================

# Choose email provider based on environment variable
EMAIL_PROVIDER = os.environ.get('EMAIL_PROVIDER', 'gmail')  # 'sendgrid' or 'gmail'

if EMAIL_PROVIDER == 'sendgrid':
    # SendGrid configuration (RECOMMENDED for production)
    app.config['MAIL_SERVER'] = 'smtp.sendgrid.net'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USERNAME'] = 'apikey'  # literally the string "apikey"
    app.config['MAIL_PASSWORD'] = os.environ.get('SENDGRID_API_KEY')
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USE_SSL'] = False
    app.config['MAIL_DEFAULT_SENDER'] = 'kinetowebapp@gmail.com'
    app.config['MAIL_TIMEOUT'] = 10  # Shorter timeout for SendGrid
    
    if not os.environ.get('SENDGRID_API_KEY'):
        print("WARNING: SENDGRID_API_KEY environment variable not set!")
    else:
        print("✓ SendGrid email configuration loaded successfully")
else:
    # Gmail configuration (works locally, may timeout on Render)
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USERNAME'] = 'kinetowebapp@gmail.com'
    app.config['MAIL_PASSWORD'] = os.environ.get('KINETO_MAIL_PASSWORD')
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USE_SSL'] = False
    app.config['MAIL_DEFAULT_SENDER'] = 'kinetowebapp@gmail.com'
    app.config['MAIL_TIMEOUT'] = 30
    
    if not os.environ.get('KINETO_MAIL_PASSWORD'):
        print("WARNING: KINETO_MAIL_PASSWORD environment variable not set!")
    else:
        print("✓ Gmail configuration loaded successfully")

# Common mail settings
app.config['MAIL_MAX_EMAILS'] = None
app.config['MAIL_ASCII_ATTACHMENTS'] = False

print(f"Email Provider: {EMAIL_PROVIDER.upper()}")
print(f"SMTP Server: {app.config['MAIL_SERVER']}:{app.config['MAIL_PORT']}")
print(f"SMTP User: {app.config['MAIL_USERNAME']}")
print(f"TLS: {app.config['MAIL_USE_TLS']}, Timeout: {app.config['MAIL_TIMEOUT']}s")

mail = Mail(app)
app.register_blueprint(restore)

# ========================================
# CACHING CONFIGURATION
# ========================================

# Configure Flask-Caching
app.config['CACHE_TYPE'] = 'SimpleCache'  # Use 'RedisCache' for production with Redis
app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # 5 minutes default

cache = Cache(app)

def make_user_cache_key():
    """Create a cache key based on the current user's session ID"""
    user_id = session.get('id', 'anonymous')
    return f"user_{user_id}_{request.path}"

def clear_user_cache(user_id):
    """Clear all cached data for a specific user (call after add/edit/remove movie)"""
    # With SimpleCache, we clear everything. For Redis, you could be more selective
    cache.clear()

# ========================================
# GLOBAL VARIABLES & CONSTANTS
# ========================================

months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
dict_months = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June', 7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'}

movie_genres = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
    27: "Horror", 10402: "Musical", 9648: "Mystery", 10749: "Romance", 878: "Sci-Fi",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western"
}

tv_genres = {
    10759: "Action & Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 10762: "Kids", 9648: "Mystery",
    10763: "News", 10764: "Reality", 10765: "Sci-Fi & Fantasy", 10766: "Soap",
    10767: "Talk", 10768: "War & Politics", 37: "Western"
}

movie = Movie()
tv = TV()
season = Season()

OPENROUTER_SETTINGS_FILE = os.environ.get('OPENROUTER_SETTINGS_FILE', 'openrouter_settings.json')

def _load_openrouter_settings(path):
    """Load OpenRouter tuning values from JSON file if present."""
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
            print(f"WARNING: OpenRouter settings file {path} is not a JSON object; ignoring")
            return {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        print(f"WARNING: Failed to read OpenRouter settings file {path}: {exc}")
        return {}

OPENROUTER_FILE_SETTINGS = _load_openrouter_settings(OPENROUTER_SETTINGS_FILE)

def _setting_value(name, default=None):
    """Resolve setting from environment first, then JSON file, then default."""
    raw_env = os.environ.get(name)
    if raw_env is not None and raw_env.strip() != '':
        return raw_env.strip()

    file_value = OPENROUTER_FILE_SETTINGS.get(name, default)
    return default if file_value is None else file_value

def _env_bool(name, default=False):
    """Parse a boolean setting from environment/JSON file with a sensible default."""
    raw_value = _setting_value(name, default)
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, (int, float)):
        return raw_value != 0
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() in ('1', 'true', 'yes', 'on')

def _env_optional_float(name):
    """Parse an optional float setting from environment/JSON file."""
    raw_value = _setting_value(name, None)
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None

def _env_list(name):
    """Parse list setting from environment CSV or JSON array."""
    raw_value = _setting_value(name, [])
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    if isinstance(raw_value, str):
        return [item.strip() for item in raw_value.split(',') if item.strip()]
    return []

def _env_int(name, default):
    """Parse integer setting from environment/JSON file."""
    raw_value = _setting_value(name, default)
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default

def _env_float(name, default):
    """Parse float setting from environment/JSON file."""
    raw_value = _setting_value(name, default)
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL_ID = str(_setting_value('OPENROUTER_MODEL_ID', 'google/gemma-3-12b-it:free')).strip()
OPENROUTER_MODEL_FALLBACKS = _env_list('OPENROUTER_MODEL_FALLBACKS')
OPENROUTER_REQUEST_TIMEOUT = _env_float('OPENROUTER_REQUEST_TIMEOUT', 30)
OPENROUTER_TOTAL_TIMEOUT = _env_float('OPENROUTER_TOTAL_TIMEOUT', 20)
OPENROUTER_MAX_COMPLETION_TOKENS = _env_int('OPENROUTER_MAX_COMPLETION_TOKENS', _env_int('OPENROUTER_MAX_TOKENS', 550))
OPENROUTER_MAX_ATTEMPTS = _env_int('OPENROUTER_MAX_ATTEMPTS', 3)
OPENROUTER_RETRY_BASE_DELAY = _env_float('OPENROUTER_RETRY_BASE_DELAY', 0.35)
OPENROUTER_RETRY_MAX_DELAY = _env_float('OPENROUTER_RETRY_MAX_DELAY', 1.5)
OPENROUTER_RETRY_429_MAX_DELAY = _env_float('OPENROUTER_RETRY_429_MAX_DELAY', 6)
OPENROUTER_RETRY_JITTER = _env_float('OPENROUTER_RETRY_JITTER', 0.15)
OPENROUTER_PROVIDER_SORT = str(_setting_value('OPENROUTER_PROVIDER_SORT', 'latency')).strip()
OPENROUTER_PROVIDER_ALLOW_FALLBACKS = _env_bool('OPENROUTER_PROVIDER_ALLOW_FALLBACKS', True)
OPENROUTER_PROVIDER_REQUIRE_PARAMETERS = _env_bool('OPENROUTER_PROVIDER_REQUIRE_PARAMETERS', False)
OPENROUTER_PROVIDER_ONLY = _env_list('OPENROUTER_PROVIDER_ONLY')
OPENROUTER_PROVIDER_IGNORE = _env_list('OPENROUTER_PROVIDER_IGNORE')
OPENROUTER_PREFERRED_MAX_LATENCY = _env_optional_float('OPENROUTER_PREFERRED_MAX_LATENCY')
OPENROUTER_PREFERRED_MIN_THROUGHPUT = _env_optional_float('OPENROUTER_PREFERRED_MIN_THROUGHPUT')
OPENROUTER_SERVICE_TIER = str(_setting_value('OPENROUTER_SERVICE_TIER', '')).strip()

DISCOVER_MODE_LABELS = {
    "explore": "Explore",
    "similar": "Similar",
    "comfort": "Comfort",
}

DISCOVER_MODE_PROMPTS = {
    "explore": "Prioritize discovery and variety. Suggest movies that can expand the user's usual taste while still being relevant.",
    "similar": "Recommend movies strongly aligned with the user's existing favorites, genres, and rating patterns.",
    "comfort": "Lean into comfort choices: familiar tones, trusted genres, and easy-to-love picks likely to be crowd-pleasing.",
}

DISCOVER_HISTORY_PROFILE_LABELS = {
    "recent": "Recent Favorites",
    "balanced": "Balanced Mix",
    "all_time": "All-Time Profile",
}

DISCOVER_HISTORY_PROFILE_PROMPTS = {
    "recent": "Use the user's most recent watch behavior as the strongest signal and emphasize current taste shifts.",
    "balanced": "Blend recent behavior with long-term preferences so recommendations feel both relevant and varied.",
    "all_time": "Use the full history footprint and prioritize recommendations that match enduring preferences.",
}

DISCOVER_AVAILABLE_GENRES = [
    "Action",
    "Adventure",
    "Animation",
    "Comedy",
    "Crime",
    "Documentary",
    "Drama",
    "Fantasy",
    "History",
    "Horror",
    "Mystery",
    "Romance",
    "Sci-Fi",
    "Thriller",
    "War",
    "Western",
]

# ========================================
# UTILITY FUNCTIONS
# ========================================

def clean_and_format(word):
    """Clean and format movie titles"""
    word = word.strip()
    word = " ".join(word.split())
    word = word.lower()
    return word

def clean_and_capitalize_name(name):
    """Clean and capitalize names (directors, etc.)"""
    cleaned_name = name.strip().lower()
    capitalized_name = ' '.join(word.capitalize() for word in cleaned_name.split())
    return capitalized_name

def get_current_year_month():
    """Return current year and month computed at request time."""
    today = datetime.date.today()
    return today.year, today.month

def get_movie_poster(movie_title):
    """Get movie poster from Wikipedia (fallback method)"""
    movie_title = movie_title.replace(' ', '_')
    url = f'https://en.wikipedia.org/wiki/{movie_title}'
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    img_tag = soup.find('a', {'class': 'image'})
    return str(img_tag)

def split_genres(genre_value):
    """Split comma-separated genre values into normalized genre names."""
    if not genre_value:
        return []
    return [genre.strip() for genre in str(genre_value).split(',') if genre.strip()]

def normalize_title_for_match(title):
    """Normalize titles for deterministic strict matching."""
    if not title:
        return ""
    return re.sub(r'\s+', ' ', str(title)).strip().lower()

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

    match = re.match(r'^(.*?)\s*\((\d{4})\)', heading.strip())
    if not match:
        return None, None

    return match.group(1).strip(), int(match.group(2))

def get_watched_title_year_lookup(user_id):
    """Build a strict (title, year) set for already watched movies."""
    watched_lookup = set()
    try:
        movies = get_movies(user_id)
    except Exception as e:
        app.logger.exception("Failed to build watched lookup for user %s: %s", user_id, e)
        return watched_lookup

    for movie in movies:
        normalized_title = normalize_title_for_match(movie.get('movie'))
        year = parse_year(movie.get('p_year'))
        if normalized_title and year:
            watched_lookup.add((normalized_title, year))

    return watched_lookup

def get_default_profile_stats():
    """Return a default stats payload used by both profile views."""
    return {
        'movies': [],
        'length': 0,
        'length_month': 0,
        'avg_rating': 0,
        'favorite_genre': 'No movies added',
        'rewatch_rate': 0,
        'cinema_count': 0,
        'unique_directors': 0,
        'unique_genres': 0,
        'avg_movies_per_month': 0,
        'ratings_distribution': {
            'high': 0,
            'mid': 0,
            'low': 0,
        },
    }

def build_profile_stats(user_id):
    """Build profile statistics for a user with defensive handling for empty or partial data."""
    profile_stats = get_default_profile_stats()

    _, month_now = get_current_year_month()
    movies = get_movies(user_id)

    profile_stats['movies'] = movies
    profile_stats['length'] = len(movies)
    profile_stats['length_month'] = len(get_monthly_movies(user_id, month_now))

    ratings = []
    genre_scores = {}
    unique_genres = set()
    unique_directors = set()
    active_months = set()
    rewatch_count = 0
    cinema_count = 0

    for movie in movies:
        rating = movie.get('rating')
        if isinstance(rating, (int, float)):
            ratings.append(float(rating))

        if movie.get('rewatch'):
            rewatch_count += 1

        if movie.get('cinema'):
            cinema_count += 1

        director = str(movie.get('director') or '').strip()
        if director:
            unique_directors.add(director)

        watched_date = movie.get('v_date')
        if isinstance(watched_date, datetime.date):
            active_months.add((watched_date.year, watched_date.month))

        for genre in split_genres(movie.get('genre')):
            unique_genres.add(genre)
            genre_scores[genre] = genre_scores.get(genre, 0) + 1
            if isinstance(rating, (int, float)) and rating > 5:
                genre_scores[genre] += (rating - 5) / 2

    profile_stats['favorite_genre'] = max(genre_scores, key=genre_scores.get) if genre_scores else 'No movies added'
    profile_stats['avg_rating'] = round(sum(ratings) / len(ratings), 2) if ratings else 0
    profile_stats['rewatch_rate'] = round((rewatch_count / profile_stats['length']) * 100, 1) if profile_stats['length'] else 0
    profile_stats['cinema_count'] = cinema_count
    profile_stats['unique_directors'] = len(unique_directors)
    profile_stats['unique_genres'] = len(unique_genres)
    profile_stats['avg_movies_per_month'] = round(profile_stats['length'] / len(active_months), 2) if active_months else 0
    profile_stats['ratings_distribution'] = {
        'high': sum(1 for rating in ratings if rating >= 8),
        'mid': sum(1 for rating in ratings if 5 <= rating <= 7),
        'low': sum(1 for rating in ratings if rating < 5),
    }

    return profile_stats

def get_user_watch_history_summary(user_id, history_profile='balanced', max_cap=60):
    """Get a formatted summary of user's watch history for AI analysis based on a history lens profile."""
    try:
        movies = get_movies(user_id)
        if not movies:
            return "No movies watched yet."

        profile = (history_profile or 'balanced').strip().lower()
        if profile not in DISCOVER_HISTORY_PROFILE_LABELS:
            profile = 'balanced'

        # Sort by watch date so recency-sensitive profiles remain deterministic.
        movies.sort(key=lambda x: x['v_date'], reverse=True)

        total_movies = len(movies)

        recent_pool = movies[:24]
        rated_movies = [movie for movie in movies if isinstance(movie.get('rating'), (int, float))]
        top_rated_pool = sorted(rated_movies, key=lambda x: x.get('rating', 0), reverse=True)

        selected_movies = []
        selected_keys = set()

        def append_unique(candidate):
            key = (
                normalize_title_for_match(candidate.get('movie')),
                parse_year(candidate.get('p_year')),
                candidate.get('v_date'),
            )
            if key in selected_keys:
                return
            selected_keys.add(key)
            selected_movies.append(candidate)

        if profile == 'recent':
            for movie in recent_pool[:24]:
                append_unique(movie)
        elif profile == 'all_time':
            for movie in movies[:max_cap]:
                append_unique(movie)
        else:
            for movie in recent_pool[:16]:
                append_unique(movie)
            for movie in top_rated_pool[:12]:
                append_unique(movie)
            selected_movies = selected_movies[:24]

        if not selected_movies:
            selected_movies = movies[: min(total_movies, 15)]

        lens_label = DISCOVER_HISTORY_PROFILE_LABELS.get(profile, 'Balanced Mix')
        summary = f"Watch history lens: {lens_label} ({len(selected_movies)} picked from {total_movies} total entries):\n"
        for i, movie in enumerate(selected_movies, 1):
            rating_text = f"{movie['rating']}/10" if movie['rating'] else "unrated"
            summary += f"{i}. {movie['movie']} ({movie['p_year']}) | dir: {movie['director']} | genres: {movie['genre']} | rating: {rating_text}\n"

        # Add some statistics
        rated_selected_movies = [movie for movie in selected_movies if isinstance(movie.get('rating'), (int, float))]
        if selected_movies:
            avg_rating = 0
            if rated_selected_movies:
                avg_rating = sum(movie['rating'] for movie in rated_selected_movies) / len(rated_selected_movies)
            genres = {}
            for movie in selected_movies:
                if movie['genre']:
                    for genre in movie['genre'].split(', '):
                        genres[genre.strip()] = genres.get(genre.strip(), 0) + 1

            top_genres = sorted(genres.items(), key=lambda x: x[1], reverse=True)[:3]
            summary += f"\nAverage rating in this lens: {avg_rating:.1f}/10\n"
            if top_genres:
                summary += f"Most watched genres in this lens: {', '.join([genre[0] for genre in top_genres])}\n"

        return summary
    except Exception as e:
        print(f"Error getting watch history: {e}")
        return "Unable to retrieve watch history."

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
    """Extract assistant text from OpenRouter payload and raise meaningful errors on invalid payloads."""
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

def _build_openrouter_provider_preferences():
    """Build provider routing preferences for faster and more reliable responses."""
    provider = {
        "allow_fallbacks": OPENROUTER_PROVIDER_ALLOW_FALLBACKS,
        "require_parameters": OPENROUTER_PROVIDER_REQUIRE_PARAMETERS,
    }

    if OPENROUTER_PROVIDER_SORT:
        provider["sort"] = OPENROUTER_PROVIDER_SORT
    if OPENROUTER_PROVIDER_ONLY:
        provider["only"] = OPENROUTER_PROVIDER_ONLY
    if OPENROUTER_PROVIDER_IGNORE:
        provider["ignore"] = OPENROUTER_PROVIDER_IGNORE
    if OPENROUTER_PREFERRED_MAX_LATENCY is not None:
        provider["preferred_max_latency"] = OPENROUTER_PREFERRED_MAX_LATENCY
    if OPENROUTER_PREFERRED_MIN_THROUGHPUT is not None:
        provider["preferred_min_throughput"] = OPENROUTER_PREFERRED_MIN_THROUGHPUT

    return provider

def _is_retryable_openrouter_status(status_code):
    return status_code in {408, 429, 500, 502, 503, 504}

def _build_openrouter_model_candidates():
    """Build ordered model candidates: primary first, then configured fallbacks."""
    candidates = []
    for model_id in [OPENROUTER_MODEL_ID, *OPENROUTER_MODEL_FALLBACKS]:
        cleaned = str(model_id).strip()
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)
    return candidates

def _is_fallback_worthy_openrouter_payload_error(exc):
    """Determine whether a structured OpenRouter payload error should trigger model fallback."""
    message = str(exc).lower()
    fallback_signals = (
        'no provider',
        'not available',
        'temporarily unavailable',
        'rate limit',
        'too many requests',
        'overloaded',
        'capacity',
        'quota',
    )
    return any(signal in message for signal in fallback_signals)

class OpenRouterRateLimitError(RuntimeError):
    """Raised when OpenRouter keeps returning HTTP 429 after retries."""

    def __init__(self, wait_seconds=None):
        self.wait_seconds = wait_seconds
        if wait_seconds is None:
            message = "OpenRouter is rate-limiting requests"
        else:
            message = f"OpenRouter is rate-limiting requests (retry after ~{wait_seconds:.0f}s)"
        super().__init__(message)

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

def _post_openrouter_request(headers, payload):
    """Perform OpenRouter request(s) with retry/backoff for transient provider errors."""
    for attempt in range(1, OPENROUTER_MAX_ATTEMPTS + 1):
        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=OPENROUTER_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            response_obj = getattr(exc, 'response', None)
            status_code = getattr(response_obj, 'status_code', None)
            retry_after_seconds = _extract_openrouter_retry_after_seconds(response_obj)
            retryable = (
                isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError))
                or _is_retryable_openrouter_status(status_code)
            )

            if not retryable or attempt >= OPENROUTER_MAX_ATTEMPTS:
                if status_code == 429:
                    raise OpenRouterRateLimitError(wait_seconds=retry_after_seconds) from exc
                raise

            base_delay = min(
                OPENROUTER_RETRY_MAX_DELAY,
                OPENROUTER_RETRY_BASE_DELAY * (2 ** (attempt - 1)),
            )
            sleep_base = base_delay
            if status_code == 429:
                if retry_after_seconds is None:
                    retry_after_seconds = max(1.0, base_delay * 2)
                sleep_base = min(
                    OPENROUTER_RETRY_429_MAX_DELAY,
                    max(base_delay, retry_after_seconds),
                )

            sleep_for = sleep_base + random.uniform(0, OPENROUTER_RETRY_JITTER)
            app.logger.warning(
                "OpenRouter request failed (attempt %s/%s, status=%s): %s. Retrying in %.2fs",
                attempt,
                OPENROUTER_MAX_ATTEMPTS,
                status_code,
                exc,
                sleep_for,
            )
            time.sleep(sleep_for)

def _post_openrouter_with_deadline(headers, payload):
    """Apply a hard deadline so AI calls cannot outlive Gunicorn worker timeout."""
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_post_openrouter_request, headers, payload)
    try:
        return future.result(timeout=OPENROUTER_TOTAL_TIMEOUT)
    except FutureTimeoutError as exc:
        future.cancel()
        raise TimeoutError(
            f"OpenRouter request exceeded {OPENROUTER_TOTAL_TIMEOUT:.0f}s deadline"
        ) from exc
    finally:
        # Do not block shutdown waiting for a hung request thread.
        executor.shutdown(wait=False, cancel_futures=True)

def get_ai_movie_recommendation(
    user_request,
    user_history,
    recommendation_mode='similar',
    preferred_genres=None,
    watched_lookup=None,
    history_profile='balanced',
):
    """Get AI-powered movie recommendations using OpenRouter."""
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        return "<p>Sorry, recommendation service is not configured.</p><p><strong>Error:</strong> OPENROUTER_API_KEY is not configured.</p>"

    recommendation_mode = (recommendation_mode or 'similar').strip().lower()
    if recommendation_mode not in DISCOVER_MODE_PROMPTS:
        recommendation_mode = 'similar'

    selected_genres = []
    for genre in preferred_genres or []:
        cleaned_genre = str(genre).strip()
        if cleaned_genre and cleaned_genre in DISCOVER_AVAILABLE_GENRES and cleaned_genre not in selected_genres:
            selected_genres.append(cleaned_genre)

    mode_label = DISCOVER_MODE_LABELS.get(recommendation_mode, 'Similar')
    mode_prompt = DISCOVER_MODE_PROMPTS[recommendation_mode]
    genre_prompt = ', '.join(selected_genres) if selected_genres else 'No explicit genre pre-filter selected.'
    history_profile = (history_profile or 'balanced').strip().lower()
    if history_profile not in DISCOVER_HISTORY_PROFILE_PROMPTS:
        history_profile = 'balanced'
    history_label = DISCOVER_HISTORY_PROFILE_LABELS.get(history_profile, 'Balanced Mix')
    history_prompt = DISCOVER_HISTORY_PROFILE_PROMPTS[history_profile]

    try:
        # Create a comprehensive prompt for movie recommendations
        prompt = f"""You are a movie recommendation expert. Based on the user's watch history and their request, provide 3-5 specific movie recommendations.

User's Recent Watch History:
{user_history}

User's Request: {user_request}

Recommendation Mode: {mode_label}
Mode Instructions: {mode_prompt}
History Lens: {history_label}
History Lens Instructions: {history_prompt}
Preferred Genres: {genre_prompt}

Please provide movie recommendations in the following format:
1. **Movie Title (Year) - Director**
   Genre: [genres]
   Why I recommend it: [brief explanation based on their history and request]

2. **Movie Title (Year) - Director**
   Genre: [genres]
   Why I recommend it: [brief explanation based on their history and request]

[Continue for 3-5 movies]

Keep recommendations diverse and consider the user's rating patterns and favorite genres.
If preferred genres are provided, prioritize those genres in all recommendations.
Avoid recommending exact title+year combinations already listed in watch history when possible.
Explain why each movie fits their taste based on their watch history."""

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.environ.get('APP_BASE_URL', 'http://localhost:5000'),
            "X-Title": "Kineto",
        }
        model_candidates = _build_openrouter_model_candidates()
        if not model_candidates:
            raise RuntimeError("No OpenRouter model candidates configured")

        last_rate_limit_exc = None
        last_exc = None

        for model_index, model_id in enumerate(model_candidates):
            request_payload = {
                "model": model_id,
                "messages": [{"role": "user", "content": prompt}],
                "max_completion_tokens": OPENROUTER_MAX_COMPLETION_TOKENS,
                # Keep max_tokens as a compatibility fallback for providers that still expect it.
                "max_tokens": OPENROUTER_MAX_COMPLETION_TOKENS,
            }
            request_payload["provider"] = _build_openrouter_provider_preferences()
            if OPENROUTER_SERVICE_TIER:
                request_payload["service_tier"] = OPENROUTER_SERVICE_TIER

            has_more_models = model_index < len(model_candidates) - 1

            try:
                response_payload = _post_openrouter_with_deadline(
                    headers=headers,
                    payload=request_payload,
                )
                response_text = _extract_openrouter_message_text(response_payload)

                if model_index > 0:
                    app.logger.info(
                        "OpenRouter succeeded with fallback model %s after %s prior failure(s)",
                        model_id,
                        model_index,
                    )

                # Convert markdown-style formatting to HTML for better display
                formatted_response = format_ai_response_to_html(response_text, watched_lookup=watched_lookup)
                return formatted_response

            except OpenRouterRateLimitError as exc:
                last_rate_limit_exc = exc
                last_exc = exc
                if has_more_models:
                    app.logger.warning(
                        "OpenRouter model %s hit rate limit. Trying fallback model %s",
                        model_id,
                        model_candidates[model_index + 1],
                    )
                    continue
                raise

            except requests.exceptions.RequestException as exc:
                last_exc = exc
                status_code = getattr(getattr(exc, 'response', None), 'status_code', None)
                if has_more_models and _is_retryable_openrouter_status(status_code):
                    app.logger.warning(
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
                    app.logger.warning(
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
        app.logger.warning("OpenRouter rate-limit while generating recommendations: %s", rate_limit_exc)
        wait_seconds = rate_limit_exc.wait_seconds
        if wait_seconds is None:
            hint = "Please wait a few seconds and try again."
        else:
            hint = f"Please wait about {max(1, int(round(wait_seconds)))} seconds and try again."
        return (
            "<p>Sorry, recommendation service is temporarily rate-limited.</p>"
            f"<p><strong>Details:</strong> {hint}</p>"
        )
        
    except Exception as e:
        app.logger.exception("Error getting AI recommendations from OpenRouter: %s", e)
        return f"<p>Sorry, I couldn't generate recommendations at the moment.</p><p><strong>Error:</strong> {str(e)}</p>"

def format_ai_response_to_html(text, watched_lookup=None):
    """Convert AI response text to HTML with better formatting"""

    watched_lookup = watched_lookup or set()

    # Split the text into lines for processing
    lines = text.split('\n')
    html_lines = []
    in_list = False
    current_item_open = False

    for raw_line in lines:
        line = raw_line.strip()

        # Check for numbered list items
        title_match = re.match(r'^\d+\.\s*\*\*(.*?)\*\*', line)
        if title_match:
            if not in_list:
                html_lines.append('<ol>')
                in_list = True

            if current_item_open:
                html_lines.append('</li>')

            heading = title_match.group(1)
            recommended_title, recommended_year = extract_title_year_from_heading(heading)
            normalized_title = normalize_title_for_match(recommended_title)
            show_dedup_badge = (
                normalized_title
                and recommended_year
                and (normalized_title, recommended_year) in watched_lookup
            )
            dedup_badge = ' <span class="already-watched-badge">Already watched</span>' if show_dedup_badge else ''

            html_lines.append(f'<li><strong>{heading}</strong>{dedup_badge}')
            current_item_open = True
        elif line.startswith('Genre:') or line.startswith('Why I recommend it:'):
            # Handle metadata lines
            line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
            line = re.sub(r'\*(.*?)\*', r'<em>\1</em>', line)
            html_lines.append(f'<p>{line}</p>')
        elif line and not re.match(r'^\d+\.', line):
            # Handle regular text lines
            line = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', line)
            line = re.sub(r'\*(.*?)\*', r'<em>\1</em>', line)
            if line:
                html_lines.append(f'<p>{line}</p>')
    
    # Close any open list at the end
    if current_item_open:
        html_lines.append('</li>')
    if in_list:
        html_lines.append('</ol>')
    
    return '\n'.join(html_lines)

# ========================================
# MAIN NAVIGATION ROUTES
# ========================================

@app.route('/home')
def hello():
    if 'loggedin' in session:
        try:
            _, month_now = get_current_year_month()
            movies = get_monthly_movies(session['id'], month_now)
        except Exception as e:
            app.logger.exception("Failed to load home monthly movies: %s", e)
            movies = []
            flash('Something went wrong, please refresh the page', category='error')
    else:
        return render_template('home.html', movies=[])
    return render_template('home.html', session=session, movies=movies)

@app.route('/')
def animation():
    return render_template('animation.html', session=session)

@app.route('/lista')
@login_required
@cache.cached(timeout=120, key_prefix=make_user_cache_key)
def lista():
    year_now, _ = get_current_year_month()
    try:
        movies = get_movies(session['id'])
        # sort movies in descendig order by v_date
        movies.sort(key=lambda movie: movie["v_date"], reverse=True)
    except Exception as e:
        app.logger.exception("Failed to load user list: %s", e)
        movies = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('lista1.html', movies=movies, months=months, year_now=year_now, dict_months=dict_months)

@app.route('/list/<username>')
def lista_user(username):
    user = get_user_id(username)
    print(user)
    id = user[0]['id']
    print(id)
    year_now, _ = get_current_year_month()
    try:
        movies = get_movies(id)
        movies.sort(key=lambda movie: movie["v_date"], reverse=True)
    except Exception as e:
        app.logger.exception("Failed to load friend list for %s: %s", username, e)
        movies = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_lista1.html', movies=movies, months=months, year_now=year_now, dict_months=dict_months, username=username)


@app.route('/directors', methods=['GET'])
@login_required
@cache.cached(timeout=300, key_prefix=make_user_cache_key)
def show_directors():
    try:
        movies = get_movies_groupby_director(session['id'])
        directors = get_directors(session['id'])
    except Exception as e:
        app.logger.exception("Failed to load directors page: %s", e)
        movies = []
        directors = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('directors.html', movies=movies, directors=directors)

@app.route('/directors/<username>', methods=['GET'])
@login_required
def show_directors_friends(username):
    try:
        id = get_user_id(username)
        id = id[0]['id']
        movies = get_movies_groupby_director(id)
        directors = get_directors(id)
    except Exception as e:
        app.logger.exception("Failed to load friend directors page for %s: %s", username, e)
        movies = []
        directors = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_directors.html', movies=movies, directors=directors)

@app.route('/genres', methods=['GET'])
@login_required
@cache.cached(timeout=300, key_prefix=make_user_cache_key)
def show_genres():
    final_genres = set()
    try:
        movies = get_movies_groupby_genre(session['id'])
        in_genres = ""
        generi = get_genres(session['id'])
        for genre in generi:
            in_genres += genre['name'] + ', '
        mid_genres = in_genres.split(', ')
        final_genres = set([genre for genre in mid_genres if genre != ''])
        print(final_genres)
    except Exception as e:
        app.logger.exception("Failed to load genres page: %s", e)
        movies = []
        generi = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('genres.html', movies=movies, genres=final_genres)

@app.route('/genres/<username>', methods=['GET'])
@login_required
def show_genres_friends(username):
    final_genres = set()
    try:
        id = get_user_id(username)
        id = id[0]['id']
        movies = get_movies_groupby_genre(id)
        in_genres = ""
        generi = get_genres(id)
        for genre in generi:
            in_genres += genre['name'] + ', '
        mid_genres = in_genres.split(', ')
        final_genres = set([genre for genre in mid_genres if genre != ''])
        print(final_genres)
    except Exception as e:
        app.logger.exception("Failed to load friend genres page for %s: %s", username, e)
        movies = []
        generi = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_genres.html', movies=movies, genres=final_genres)


@app.route('/years', methods=['GET'])
@login_required
@cache.cached(timeout=300, key_prefix=make_user_cache_key)
def show_years():
    try:
        movies = get_movies_groupby_year(session['id'])
        anni = get_years(session['id'])
    except Exception as e:
        app.logger.exception("Failed to load years page: %s", e)
        movies = []
        anni = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('years.html', movies=movies, years=anni)

@app.route('/years/<username>', methods=['GET'])
@login_required
def show_years_friends(username):
    try:
        id = get_user_id(username)
        id = id[0]['id']
        movies = get_movies_groupby_year(id)
        anni = get_years(id)
    except Exception as e:
        app.logger.exception("Failed to load friend years page for %s: %s", username, e)
        movies = []
        anni = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_years.html', movies=movies, years=anni)

# ========================================
# STATISTICS & ANALYTICS ROUTES
# ========================================

@app.route('/ratings', methods=['GET'])
@login_required
@cache.cached(timeout=300, key_prefix=make_user_cache_key)
def show_ratings():
    try:
        movies = get_movies_groupby_year(session['id'])
        ratings = get_ratings(session['id'])
    except Exception as e:
        app.logger.exception("Failed to load ratings page: %s", e)
        movies = []
        ratings = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('ratings.html', movies=movies, ratings=ratings)

@app.route('/ratings/<username>', methods=['GET'])
@login_required
def show_ratings_friends(username):
    try:
        id = get_user_id(username)
        id = id[0]['id']
        movies = get_movies_groupby_year(id)
        ratings = get_ratings(id)
    except Exception as e:
        app.logger.exception("Failed to load friend ratings page for %s: %s", username, e)
        movies = []
        ratings = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_ratings.html', movies=movies, ratings=ratings)

# ========================================
# USER PROFILE & DATA ROUTES
# ========================================

@app.route("/users/<name>")
def show_user_profile(name):
    user = load_users_from_username(name)
    return jsonify(user)

@app.route('/data')
@login_required
def list_about():
    users = get_user_by_id(session['id'])
    movies = get_movies(session['id'])
    return jsonify(movies)

@app.route('/data/<username>')
@login_required
def list_about_friend(username):
    users = get_user_id(username)
    movies = get_movies(users[0]['id'])
    return jsonify(movies)

@app.route('/profile')
@login_required
def profile():
    users = get_user_by_id(session['id'])
    profile_stats = get_default_profile_stats()
    try:
        profile_stats = build_profile_stats(session['id'])
    except Exception as e:
        app.logger.exception("Failed to load profile page: %s", e)
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('profile.html', user=users[0], **profile_stats)

@app.route('/profile/<username>')
@login_required
def profile_friend(username):
    users = get_user_id(username)
    profile_stats = get_default_profile_stats()
    try:
        profile_stats = build_profile_stats(users[0]['id'])
    except Exception as e:
        app.logger.exception("Failed to load friend profile page for %s: %s", username, e)
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_profile.html', username=username, user=users[0], **profile_stats)

# ========================================
# SOCIAL FEATURES (FRIENDS & DISCOVERY)
# ========================================

@app.route('/friends', methods=['GET', 'POST'])
@login_required
def search_friends():
    friends = get_friends(session['id'])
    if request.method == "POST":
        name = request.form['name']
        users = get_user_name(name)
        if users == []:
            flash('No user found', category='error')
        else:
            return render_template('friends.html', users=users, friends=friends, session=session) 
    liked = []   
    for friend in friends:
        movies = get_movies(friend['user_id'])
        for movie in movies:
            if movie['rating'] >= 8 and datetime.date.today() - movie['v_date'] < datetime.timedelta(days=30):
                liked.append(movie)                  
    return render_template('friends.html', friends=friends, liked=liked, session=session)

@app.route('/follow', methods=['GET', 'POST'])
@login_required
def follow():
    if request.method == "POST":
        friend_id = request.form['user_id']
        friend_username = request.form['username']
        insert_friends(friend_id, friend_username, session['id'])
        return redirect('/friends')
    return redirect('/friends')


@app.route('/discover', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per minute")  # Rate limit AI recommendations
def discover():
    ai_response = None
    user_request = ""
    recommendation_mode = 'similar'
    history_profile = 'balanced'
    selected_genres = []
    
    if request.method == 'POST':
        user_request = request.form.get('user_request', '').strip()
        recommendation_mode = request.form.get('recommendation_mode', 'similar').strip().lower()
        if recommendation_mode not in DISCOVER_MODE_PROMPTS:
            recommendation_mode = 'similar'

        history_profile = request.form.get('history_profile', 'balanced').strip().lower()
        if history_profile not in DISCOVER_HISTORY_PROFILE_LABELS:
            history_profile = 'balanced'

        selected_genres = []
        for genre in request.form.getlist('preferred_genres'):
            cleaned_genre = genre.strip()
            if cleaned_genre in DISCOVER_AVAILABLE_GENRES and cleaned_genre not in selected_genres:
                selected_genres.append(cleaned_genre)

        if user_request:
            # Get user's watch history using the selected lens profile.
            user_history = get_user_watch_history_summary(session['id'], history_profile=history_profile)
            watched_lookup = get_watched_title_year_lookup(session['id'])
            
            # Get AI recommendations
            ai_response = get_ai_movie_recommendation(
                user_request,
                user_history,
                recommendation_mode=recommendation_mode,
                preferred_genres=selected_genres,
                watched_lookup=watched_lookup,
                history_profile=history_profile,
            )
        else:
            flash('Please enter a request for movie recommendations', 'error')
    
    return render_template(
        'discover.html',
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

# ========================================
# MOVIE MANAGEMENT (ADD/EDIT/REMOVE)
# ========================================

@app.route('/add_movie', methods=['GET', 'POST'])
@login_required
@limiter.limit("100 per hour")  # Rate limit movie additions
def add_movie():
    if request.method == "POST":
        try:
            parent_id = get_user_by_id(session['id'])
            title = request.form["title"]
            title = clean_and_format(title)
            manual_director = request.form["director"].strip()
            year = request.form["year"]
            date = request.form["date"]
            genre = ""
            director = ""
            rating = request.form["rating"]
            rewatch = request.form["rewatch"] # 0 false, 1 true
            tv_show = request.form["tv"] # 0 if movie, 1 if tv show
            which_season = request.form["season"]
            cinema = request.form["cinema"]
            
            # Use manual director if provided, otherwise auto-fetch
            if manual_director:
                director = clean_and_capitalize_name(manual_director)
            
            try:
                if tv_show == '1':
                    res = tv.search(title)
                    for i, result in enumerate(res):
                        print(f"Result_{i}", result)
                        if result['first_air_date'][:4] == str(year):
                            ids = result['id']
                            show_season = season.details(ids, which_season)
                            poster = "https://image.tmdb.org/t/p/w200" + show_season.poster_path
                            title = title + ', ' + show_season.name
                            genre_ids = result['genre_ids']
                            genre = genre.join([tv_genres[genre_id] + ", " for genre_id in genre_ids])
                            genre = genre[:-2]
                            
                            # Get TV show creator/director only if not manually provided
                            if not director:
                                try:
                                    tv_details = tv.details(ids)
                                    print(tv_details)
                                    if hasattr(tv_details, 'created_by') and tv_details.created_by:
                                        director = tv_details.created_by[0]['name']
                                    else:
                                        # Try to get credits for TV show
                                        try:
                                            api_key = tmdb.api_key
                                            credits_url = f"https://api.themoviedb.org/3/tv/{ids}/credits?api_key={api_key}"
                                            credits_response = requests.get(credits_url)
                                            if credits_response.status_code == 200:
                                                credits_data = credits_response.json()
                                                for crew_member in credits_data.get('crew', []):
                                                    if crew_member['job'] in ['Director', 'Creator', 'Executive Producer']:
                                                        director = crew_member['name']
                                                        break
                                        except:
                                            pass
                                        
                                        if not director:
                                            director = "Various Directors"
                                except:
                                    director = "Unknown"
                            print(genre)
                            break
                else:
                    res = movie.search(title)
                    for i, result in enumerate(res):
                        print(f"Result_{i}", result)
                        if result['release_date'][:4] == str(year):
                            poster = "https://image.tmdb.org/t/p/w200/" + result['poster_path']
                            genre_ids = result['genre_ids']
                            genre = genre.join([movie_genres[genre_id] + ", " for genre_id in genre_ids])
                            genre = genre[:-2]
                            
                            # Get movie director only if not manually provided
                            if not director:
                                try:
                                    movie_details = movie.details(result['id'])
                                    # Try to get credits using the tmdbv3api
                                    credits = movie_details.credits
                                    if credits and 'crew' in credits:
                                        for crew_member in credits['crew']:
                                            if crew_member['job'] == 'Director':
                                                director = crew_member['name']
                                                break
                                except:
                                    # Fallback: try manual API call for credits
                                    try:
                                        api_key = tmdb.api_key
                                        credits_url = f"https://api.themoviedb.org/3/movie/{result['id']}/credits?api_key={api_key}"
                                        credits_response = requests.get(credits_url)
                                        if credits_response.status_code == 200:
                                            credits_data = credits_response.json()
                                            for crew_member in credits_data.get('crew', []):
                                                if crew_member['job'] == 'Director':
                                                    director = crew_member['name']
                                                    break
                                    except:
                                        pass

                                if not director:
                                    director = "Unknown"
                            break
            except:
                html = get_movie_poster(title)
                if html != 'None':
                    soup = BeautifulSoup(html, 'html.parser')
                    img_tag = soup.find('img')
                    src_link = img_tag['src']   
                    poster = src_link
                else: 
                    res = movie.search(title)
                    poster = res[0]['poster_path']
            
            print(title, director, year, date, genre, rating, rewatch, tv_show, session['id'])
            insert_movies(title, director, genre, year, date, rating, rewatch, tv_show, poster, session['id'], cinema)
            clear_user_cache(session['id'])  # Clear cache after adding movie
            flash('Movie added', category='success')
        except Exception as e:
            print(f"Error adding movie: {e}")
            flash('Something went wrong, please try again', category='error')
            return redirect('/add_movie')
                
    return render_template('add_movie.html')

@app.route('/remove_movie', methods=['GET', 'POST'])
@login_required
@limiter.limit("30 per hour")  # Rate limit movie removals
def remove_movie():
    if request.method == "POST":
        movie_id = request.form['movie_id']
        remove_movie_by_id(movie_id)
        clear_user_cache(session['id'])  # Clear cache after removing movie
        flash('Movie removed', category='success')
        return redirect('/home')
    return redirect('/home')

@app.route('/edit_movie', methods=['GET', 'POST'])
@login_required
@limiter.limit("30 per hour")  # Rate limit movie edits
def edit_movie():
    if request.method == "GET":
        return render_template('edit_movie.html')
    else:
        movie_id = request.form['movie_id']
        title = request.form['movie']
        director = request.form['director']
        p_year = request.form['year']
        rating = request.form['rating']
        tv_show = request.form['tv']
        try:
            if tv_show == '1':
                res = tv.search(title)
            else:
                res = movie.search(title)
            poster = "https://image.tmdb.org/t/p/w200/" + res[0]['poster_path']
        except:
            html = get_movie_poster(title)
            if html != 'None':
                soup = BeautifulSoup(html, 'html.parser')
                img_tag = soup.find('img')
                src_link = img_tag['src']   
                poster = src_link
            else: 
                res = movie.search(title)
                poster = res[0]['poster_path']
        update_movie(movie_id, title, director, p_year, rating, poster)
        clear_user_cache(session['id'])  # Clear cache after updating movie
        flash('Movie updated', category='success')
        return redirect('/home')

# ========================================
# APPLICATION ENTRY POINT
# ========================================

if __name__ == '__main__':
    # Use environment variable to control debug mode
    # Set FLASK_DEBUG=1 for development, omit or set to 0 for production
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug_mode)
    
    
#@app.route('/lista_<year_selected>')
#def lista_year(year_selected):
#    if 'loggedin' in session:
#        try:
#            movies = get_movies(session['id'])
#        except:
#            movies = []
#            flash('Something went wrong, please refresh the page', category='error')
#    else:
#        return redirect('/login')
#    return render_template('lista_year.html', year=int(year_selected), movies=movies, months=months, dict_months=dict_months)