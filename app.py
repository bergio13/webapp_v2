from flask import Flask, render_template, jsonify, request, flash, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
import requests
import re
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
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        return "<p>Sorry, recommendation service is not configured.</p><p><strong>Error:</strong> OPENROUTER_API_KEY is not configured.</p>"

    return service_get_ai_movie_recommendation(
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


def format_ai_response_to_html(text, watched_lookup=None):
    """Convert AI response text to HTML with better formatting."""
    return service_format_ai_response_to_html(text, watched_lookup=watched_lookup)

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