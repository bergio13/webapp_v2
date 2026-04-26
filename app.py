from flask import Flask, render_template, jsonify, request, flash, redirect, session, Response, stream_with_context
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
import requests
import re
from functools import wraps
from bs4 import BeautifulSoup
from services import tmdb_service
from flask_mail import Mail, Message
from flask_caching import Cache
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from auth.auth import auth # Import the auth blueprint
from auth.restore import restore # Import the restore blueprint
from dotenv import load_dotenv
from recommendation_service import (
    DiscoverConfig,
    OpenRouterSettings,
    build_user_watch_history_summary,
    build_watched_title_year_lookup,
    format_ai_response_to_html as service_format_ai_response_to_html,
    get_ai_movie_recommendation as service_get_ai_movie_recommendation,
)

# Load environment variables from .env before importing database module.
load_dotenv()

from database import *
import datetime

# ========================================
# APP CONFIGURATION
# ========================================

# TMDB initialized in services/tmdb_service.py

app = Flask(__name__)
# Register the auth blueprint with the main app
app.register_blueprint(auth)

app.secret_key = os.environ.get('FLASK_SECRET_KEY')

# Enable CSRF protection for all forms
csrf = CSRFProtect(app)

from flask_login import LoginManager, login_required
from auth.models import User

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = "Please log in to access this page"
login_manager.login_message_category = "error"

@login_manager.user_loader
def load_user(user_id):
    users = get_user_by_id(user_id)
    if users:
        user_data = users[0]
        return User(id=user_data['id'], username=user_data['username'], email=user_data['email'])
    return None

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

# login_required decorator is imported from flask_login

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

# Genres and clients moved to services/tmdb_service.py

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
OPENROUTER_MODEL_DEADLINE = _env_float('OPENROUTER_MODEL_DEADLINE', 8)
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

# Wikipedia fallback removed

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

    return build_watched_title_year_lookup(movies)

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

def _build_openrouter_settings():
    """Create OpenRouter settings payload for the recommendation service."""
    return OpenRouterSettings(
        api_url=OPENROUTER_API_URL,
        model_id=OPENROUTER_MODEL_ID,
        model_fallbacks=OPENROUTER_MODEL_FALLBACKS,
        request_timeout=OPENROUTER_REQUEST_TIMEOUT,
        total_timeout=OPENROUTER_TOTAL_TIMEOUT,
        model_deadline=OPENROUTER_MODEL_DEADLINE,
        max_completion_tokens=OPENROUTER_MAX_COMPLETION_TOKENS,
        max_attempts=OPENROUTER_MAX_ATTEMPTS,
        retry_base_delay=OPENROUTER_RETRY_BASE_DELAY,
        retry_max_delay=OPENROUTER_RETRY_MAX_DELAY,
        retry_429_max_delay=OPENROUTER_RETRY_429_MAX_DELAY,
        retry_jitter=OPENROUTER_RETRY_JITTER,
        provider_sort=OPENROUTER_PROVIDER_SORT,
        provider_allow_fallbacks=OPENROUTER_PROVIDER_ALLOW_FALLBACKS,
        provider_require_parameters=OPENROUTER_PROVIDER_REQUIRE_PARAMETERS,
        provider_only=OPENROUTER_PROVIDER_ONLY,
        provider_ignore=OPENROUTER_PROVIDER_IGNORE,
        preferred_max_latency=OPENROUTER_PREFERRED_MAX_LATENCY,
        preferred_min_throughput=OPENROUTER_PREFERRED_MIN_THROUGHPUT,
        service_tier=OPENROUTER_SERVICE_TIER,
    )


def _build_discover_config():
    """Create discover prompt/label config for the recommendation service."""
    return DiscoverConfig(
        mode_labels=DISCOVER_MODE_LABELS,
        mode_prompts=DISCOVER_MODE_PROMPTS,
        history_profile_labels=DISCOVER_HISTORY_PROFILE_LABELS,
        history_profile_prompts=DISCOVER_HISTORY_PROFILE_PROMPTS,
        available_genres=DISCOVER_AVAILABLE_GENRES,
    )


def get_user_watch_history_summary(user_id, history_profile='balanced', max_cap=60):
    """Get a formatted summary of user's watch history for AI analysis based on a history lens profile."""
    try:
        movies = get_movies(user_id)
        return build_user_watch_history_summary(
            movies,
            history_profile=history_profile,
            max_cap=max_cap,
            history_profile_labels=DISCOVER_HISTORY_PROFILE_LABELS,
        )
    except Exception as e:
        print(f"Error getting watch history: {e}")
        return "Unable to retrieve watch history."


def get_ai_movie_recommendation(
    user_request,
    user_history,
    recommendation_mode='similar',
    preferred_genres=None,
    watched_lookup=None,
    history_profile='balanced',
):
    """Get AI-powered movie recommendations using the recommendation service."""
    # Check cache
    genres_str = ','.join(sorted(preferred_genres or []))
    cache_key = f"ai_rec_{user_request}_{recommendation_mode}_{history_profile}_{genres_str}"
    cached_val = cache.get(cache_key)
    if cached_val:
        return cached_val

    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        return "<p>Sorry, recommendation service is not configured.</p><p><strong>Error:</strong> OPENROUTER_API_KEY is not configured.</p>"

    result = service_get_ai_movie_recommendation(
        user_request,
        user_history,
        recommendation_mode=recommendation_mode,
        preferred_genres=preferred_genres,
        watched_lookup=watched_lookup,
        history_profile=history_profile,
        api_key=api_key,
        app_base_url=os.environ.get('APP_BASE_URL', 'http://localhost:5000'),
        settings=_build_openrouter_settings(),
        discover_config=_build_discover_config(),
        logger=app.logger,
    )
    if result and not "Error:" in result and not "rate-limited" in result:
        cache.set(cache_key, result, timeout=3600)
    return result


def format_ai_response_to_html(text, watched_lookup=None):
    """Convert AI response text to HTML with better formatting."""
    return service_format_ai_response_to_html(text, watched_lookup=watched_lookup)

# ========================================
# MAIN NAVIGATION ROUTES
# ========================================

@app.route('/api/now-playing')
@login_required
def api_now_playing():
    """Return a list of movies currently in cinemas this week (TMDB now_playing)."""
    import requests as http_requests
    api_key = os.environ.get('TMDB_API_KEY')
    if not api_key:
        return jsonify({'movies': []})
    try:
        url = f'https://api.themoviedb.org/3/movie/now_playing?api_key={api_key}&language=en-US&page=1'
        resp = http_requests.get(url, timeout=5)
        data = resp.json()
        movies = []
        for m in (data.get('results') or [])[:8]:
            poster = m.get('poster_path')
            if poster:
                movies.append({
                    'title': m.get('title', ''),
                    'poster': f'https://image.tmdb.org/t/p/w185{poster}',
                    'rating': round(m.get('vote_average', 0), 1),
                })
        return jsonify({'movies': movies})
    except Exception:
        return jsonify({'movies': []})

@app.route('/home')
def hello():
    if 'loggedin' in session:
        try:
            _, month_now = get_current_year_month()
            movies = get_monthly_movies(session['id'], month_now)
            
            # Calculate Monthly Stats
            total_this_month = len(movies)
            avg_rating = round(sum(float(m['rating']) for m in movies) / total_this_month, 1) if total_this_month > 0 else 0
            cinema_trips = sum(1 for m in movies if int(m['cinema']) == 1)
            highest_rated = max(movies, key=lambda m: float(m['rating'])) if movies else None

        except Exception as e:
            app.logger.exception("Failed to load home monthly movies: %s", e)
            movies = []
            total_this_month = 0
            avg_rating = 0
            cinema_trips = 0
            highest_rated = None
            flash('Something went wrong, please refresh the page', category='error')
    else:
        return render_template('home.html', movies=[], total=0, avg_rating=0, cinema=0, highest_rated=None)
        
    return render_template('home.html', session=session, movies=movies, 
                           total=total_this_month, avg_rating=avg_rating, 
                           cinema=cinema_trips, highest_rated=highest_rated)

@app.route('/')
def animation():
    return render_template('animation.html', session=session)

@app.route('/lista')
@login_required
@cache.cached(timeout=120, key_prefix=make_user_cache_key)
def lista():
    year_now, _ = get_current_year_month()
    try:
        movies, _ = get_movies_paginated(session['id'], page=1, limit=50)
    except Exception as e:
        app.logger.exception("Failed to load user list: %s", e)
        movies = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('lista1.html', movies=movies, months=months, year_now=year_now, dict_months=dict_months)

@app.route('/api/watched_lookup')
@login_required
def api_watched_lookup():
    watched_set = get_watched_title_year_lookup(session['id'])
    lookup_list = [{"title": t, "year": y} for t, y in watched_set]
    return jsonify(lookup_list)


@app.route('/api/movies')
@login_required
def api_movies():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 50, type=int)
    
    username = request.args.get('username')
    user_id = session.get('id')
    
    if username:
        user_data = get_user_id(username)
        if user_data:
            user_id = user_data[0]['id']
        else:
            return jsonify({'movies': [], 'has_next': False}), 404
            
    search = request.args.get('search')
    movies, total_count = get_movies_paginated(user_id, page=page, limit=limit, search=search)
    
    serialized_movies = []
    for m in movies:
        m_copy = dict(m)
        if hasattr(m['v_date'], 'isoformat'):
            m_copy['v_date'] = m['v_date'].isoformat()
        serialized_movies.append(m_copy)
        
    has_next = (page * limit) < total_count
    return jsonify({'movies': serialized_movies, 'has_next': has_next})

@app.route('/list/<username>')
def lista_user(username):
    user = get_user_id(username)
    if not user:
        app.logger.warning("Friend list requested for unknown user: %s", username)
        flash('User not found', category='error')
        return redirect('/friends' if 'loggedin' in session else '/')

    id = user[0]['id']
    year_now, _ = get_current_year_month()
    try:
        movies, _ = get_movies_paginated(id, page=1, limit=50)
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
    user = get_user_id(username)
    if not user:
        app.logger.warning("Friend directors requested for unknown user: %s", username)
        flash('User not found', category='error')
        return redirect('/friends')

    id = user[0]['id']
    try:
        movies = get_movies_groupby_director(id)
        directors = get_directors(id)
    except Exception as e:
        app.logger.exception("Failed to load friend directors page for %s: %s", username, e)
        movies = []
        directors = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_directors.html', movies=movies, directors=directors, username=username)

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
    user = get_user_id(username)
    if not user:
        app.logger.warning("Friend genres requested for unknown user: %s", username)
        flash('User not found', category='error')
        return redirect('/friends')

    id = user[0]['id']
    try:
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
    return render_template('_genres.html', movies=movies, genres=final_genres, username=username)


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
    user = get_user_id(username)
    if not user:
        app.logger.warning("Friend years requested for unknown user: %s", username)
        flash('User not found', category='error')
        return redirect('/friends')

    id = user[0]['id']
    try:
        movies = get_movies_groupby_year(id)
        anni = get_years(id)
    except Exception as e:
        app.logger.exception("Failed to load friend years page for %s: %s", username, e)
        movies = []
        anni = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_years.html', movies=movies, years=anni, username=username)

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
    user = get_user_id(username)
    if not user:
        app.logger.warning("Friend ratings requested for unknown user: %s", username)
        flash('User not found', category='error')
        return redirect('/friends')

    id = user[0]['id']
    try:
        movies = get_movies_groupby_year(id)
        ratings = get_ratings(id)
    except Exception as e:
        app.logger.exception("Failed to load friend ratings page for %s: %s", username, e)
        movies = []
        ratings = []
        flash('Something went wrong, please refresh the page', category='error')
    return render_template('_ratings.html', movies=movies, ratings=ratings, username=username)

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
    
    # Calculate a basic taste match for each friend to display on their card
    # We will just fetch it directly to avoid too many heavy queries if there are many friends
    # For a large number of friends, this might be slow, but for now we'll do it.
    # Actually, the user asked for a "Compare" page, so we don't need to calculate match percent here!
    
    if request.method == "POST":
        name = request.form['name']
        users = get_user_name(name)
        if users == []:
            flash('No user found', category='error')
        else:
            return render_template('friends.html', users=users, friends=friends, session=session) 
            
    # Fetch real-time activity feed
    recent_activity = get_friend_activity(session['id'], limit=25)
    
    return render_template('friends.html', friends=friends, activity=recent_activity, session=session)

@app.route('/follow', methods=['GET', 'POST'])
@login_required
def follow():
    if request.method == "POST":
        friend_id = request.form['user_id']
        friend_username = request.form['username']
        insert_friends(friend_id, friend_username, session['id'])
        flash(f'You are now following {friend_username}', 'success')
        return redirect('/friends')
    return redirect('/friends')

@app.route('/unfollow', methods=['POST'])
@login_required
def unfollow():
    friend_id = request.form.get('user_id')
    friend_username = request.form.get('username')
    if friend_id:
        try:
            friend_id = int(friend_id)
        except ValueError:
            pass
        remove_friend(session['id'], friend_id)
        flash(f'You unfollowed {friend_username}', 'success')
    return redirect('/friends')

@app.route('/compare/<username>')
@login_required
def compare_taste(username):
    # Get friend user ID
    friend_data = get_user_name(username)
    if not friend_data:
        flash("User not found.", "error")
        return redirect('/friends')
        
    friend_id = friend_data[0]['id']
    
    # Calculate match
    match_data = get_taste_match(session['id'], friend_id)
    
    return render_template('compare.html', friend_username=username, match_data=match_data, session=session)


@app.route('/api/recommend_stream', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def recommend_stream():
    data = request.get_json() or {}
    user_request = data.get('user_request', '').strip()
    recommendation_mode = data.get('recommendation_mode', 'similar').strip().lower()
    history_profile = data.get('history_profile', 'balanced').strip().lower()
    selected_genres = data.get('preferred_genres', [])
    
    if not user_request:
        return jsonify({"error": "Prompt required"}), 400

    genres_str = ','.join(sorted(selected_genres))
    cache_key = f"ai_rec_{user_request}_{recommendation_mode}_{history_profile}_{genres_str}"
    
    cached_val = cache.get(cache_key)
    if cached_val:
        def stream_cached():
            import json
            yield f"data: {json.dumps({'token': cached_val})}\n\n"
        return Response(stream_with_context(stream_cached()), mimetype='text/event-stream')

    user_history = get_user_watch_history_summary(session['id'], history_profile=history_profile)
    
    api_key = os.environ.get('OPENROUTER_API_KEY')
    settings = _build_openrouter_settings()
    discover_config = _build_discover_config()

    from recommendation_service import get_ai_movie_recommendation_stream

    def generate():
        import json
        accumulated = ""
        try:
            for chunk in get_ai_movie_recommendation_stream(
                user_request,
                user_history,
                recommendation_mode=recommendation_mode,
                preferred_genres=selected_genres,
                history_profile=history_profile,
                api_key=api_key,
                app_base_url=os.environ.get('APP_BASE_URL', 'http://localhost:5000'),
                settings=settings,
                discover_config=discover_config,
                logger=app.logger
            ):
                if chunk.startswith("Error:"):
                    yield f"data: {json.dumps({'error': chunk})}\n\n"
                    return
                accumulated += chunk
                yield f"data: {json.dumps({'token': chunk})}\n\n"
            
            if accumulated and not "Error:" in accumulated:
                cache.set(cache_key, accumulated, timeout=3600)
                
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


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
            title = request.form["title"]
            title = clean_and_format(title)
            manual_director = request.form["director"].strip()
            year = request.form["year"]
            date = request.form["date"]
            rating = request.form["rating"]
            rewatch = request.form["rewatch"] # 0 false, 1 true
            tv_show = request.form["tv"] # 0 if movie, 1 if tv show
            which_season = request.form["season"]
            cinema = request.form["cinema"]
            
            if manual_director:
                manual_director = clean_and_capitalize_name(manual_director)
            
            if tv_show == '1':
                try:
                    season_num = int(which_season) if which_season else 1
                except ValueError:
                    season_num = 1
                details = tmdb_service.get_tv_details(title, year, season_num, manual_director)
            else:
                details = tmdb_service.get_movie_details(title, year, manual_director)
                
            if details:
                poster = details["poster"]
                genre = details["genre"]
                director = details["director"]
                title = details["title"]
            else:
                poster = "https://via.placeholder.com/200x300?text=No+Poster"
                genre = "Unknown"
                director = manual_director or "Unknown"
            
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
        movie_id = request.form.get('movie_id')
        if not movie_id and request.is_json:
            movie_id = request.json.get('movie_id')
            
        remove_movie_by_id(movie_id)
        clear_user_cache(session['id'])  # Clear cache after removing movie
        
        if request.is_json or request.accept_mimetypes.accept_json:
            return jsonify({'success': True, 'message': 'Movie removed'})
            
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
        
        if tv_show == '1':
            details = tmdb_service.get_tv_details(title, p_year, 1)
        else:
            details = tmdb_service.get_movie_details(title, p_year)
            
        poster = details["poster"] if details else "https://via.placeholder.com/200x300?text=No+Poster"
        
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