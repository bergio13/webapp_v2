"""AI / OpenRouter helpers.

All OpenRouter constants, setting-parsers, and the recommendation wrapper live
here so blueprints can import from a single, focused module.
"""
import json
import logging
import os

from recommendation_service import (
    DiscoverConfig,
    OpenRouterSettings,
    format_ai_response_to_html as _format_ai_response_to_html,
    get_ai_movie_recommendation as _get_ai_movie_recommendation,
)

from extensions import cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings file loader
# ---------------------------------------------------------------------------

OPENROUTER_SETTINGS_FILE = os.environ.get("OPENROUTER_SETTINGS_FILE", "openrouter_settings.json")


def _load_openrouter_settings(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
            logger.warning("OpenRouter settings file %s is not a JSON object; ignoring", path)
            return {}
    except FileNotFoundError:
        return {}
    except Exception:
        logger.exception("Failed to read OpenRouter settings file %s", path)
        return {}


_FILE_SETTINGS: dict = _load_openrouter_settings(OPENROUTER_SETTINGS_FILE)


# ---------------------------------------------------------------------------
# Setting value resolvers
# ---------------------------------------------------------------------------

def _setting_value(name: str, default=None):
    raw = os.environ.get(name)
    if raw is not None and raw.strip():
        return raw.strip()
    val = _FILE_SETTINGS.get(name, default)
    return default if val is None else val


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _setting_value(name, default)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _env_optional_float(name: str):
    raw = _setting_value(name, None)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _env_list(name: str) -> list:
    raw = _setting_value(name, [])
    if isinstance(raw, list):
        return [str(i).strip() for i in raw if str(i).strip()]
    if isinstance(raw, str):
        return [i.strip() for i in raw.split(",") if i.strip()]
    return []


def _env_int(name: str, default: int) -> int:
    try:
        return int(_setting_value(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_setting_value(name, default))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# OpenRouter constants
# ---------------------------------------------------------------------------

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL_ID = str(_setting_value("OPENROUTER_MODEL_ID", "google/gemini-3.6-flash")).strip()
OPENROUTER_MODEL_FALLBACKS = _env_list("OPENROUTER_MODEL_FALLBACKS")
OPENROUTER_REQUEST_TIMEOUT = _env_float("OPENROUTER_REQUEST_TIMEOUT", 30)
OPENROUTER_TOTAL_TIMEOUT = _env_float("OPENROUTER_TOTAL_TIMEOUT", 20)
OPENROUTER_MODEL_DEADLINE = _env_float("OPENROUTER_MODEL_DEADLINE", 8)
OPENROUTER_MAX_COMPLETION_TOKENS = _env_int(
    "OPENROUTER_MAX_COMPLETION_TOKENS",
    _env_int("OPENROUTER_MAX_TOKENS", 550),
)
OPENROUTER_MAX_ATTEMPTS = _env_int("OPENROUTER_MAX_ATTEMPTS", 3)
OPENROUTER_RETRY_BASE_DELAY = _env_float("OPENROUTER_RETRY_BASE_DELAY", 0.35)
OPENROUTER_RETRY_MAX_DELAY = _env_float("OPENROUTER_RETRY_MAX_DELAY", 1.5)
OPENROUTER_RETRY_429_MAX_DELAY = _env_float("OPENROUTER_RETRY_429_MAX_DELAY", 6)
OPENROUTER_RETRY_JITTER = _env_float("OPENROUTER_RETRY_JITTER", 0.15)
OPENROUTER_PROVIDER_SORT = str(_setting_value("OPENROUTER_PROVIDER_SORT", "latency")).strip()
OPENROUTER_PROVIDER_ALLOW_FALLBACKS = _env_bool("OPENROUTER_PROVIDER_ALLOW_FALLBACKS", True)
OPENROUTER_PROVIDER_REQUIRE_PARAMETERS = _env_bool("OPENROUTER_PROVIDER_REQUIRE_PARAMETERS", False)
OPENROUTER_PROVIDER_ONLY = _env_list("OPENROUTER_PROVIDER_ONLY")
OPENROUTER_PROVIDER_IGNORE = _env_list("OPENROUTER_PROVIDER_IGNORE")
OPENROUTER_PREFERRED_MAX_LATENCY = _env_optional_float("OPENROUTER_PREFERRED_MAX_LATENCY")
OPENROUTER_PREFERRED_MIN_THROUGHPUT = _env_optional_float("OPENROUTER_PREFERRED_MIN_THROUGHPUT")
OPENROUTER_SERVICE_TIER = str(_setting_value("OPENROUTER_SERVICE_TIER", "")).strip()

# ---------------------------------------------------------------------------
# Discover-mode constants
# ---------------------------------------------------------------------------

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
    "Action", "Adventure", "Animation", "Comedy", "Crime",
    "Documentary", "Drama", "Fantasy", "History", "Horror",
    "Mystery", "Romance", "Sci-Fi", "Thriller", "War", "Western",
]

# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

def build_openrouter_settings() -> OpenRouterSettings:
    """Create an ``OpenRouterSettings`` payload for the recommendation service."""
    import sys
    webapp = sys.modules.get("app")
    def _get(name, default):
        if webapp and hasattr(webapp, name):
            return getattr(webapp, name)
        return globals().get(name, default)

    return OpenRouterSettings(
        api_url=_get("OPENROUTER_API_URL", OPENROUTER_API_URL),
        model_id=_get("OPENROUTER_MODEL_ID", OPENROUTER_MODEL_ID),
        model_fallbacks=_get("OPENROUTER_MODEL_FALLBACKS", OPENROUTER_MODEL_FALLBACKS),
        request_timeout=_get("OPENROUTER_REQUEST_TIMEOUT", OPENROUTER_REQUEST_TIMEOUT),
        total_timeout=_get("OPENROUTER_TOTAL_TIMEOUT", OPENROUTER_TOTAL_TIMEOUT),
        model_deadline=_get("OPENROUTER_MODEL_DEADLINE", OPENROUTER_MODEL_DEADLINE),
        max_completion_tokens=_get("OPENROUTER_MAX_COMPLETION_TOKENS", OPENROUTER_MAX_COMPLETION_TOKENS),
        max_attempts=_get("OPENROUTER_MAX_ATTEMPTS", OPENROUTER_MAX_ATTEMPTS),
        retry_base_delay=_get("OPENROUTER_RETRY_BASE_DELAY", OPENROUTER_RETRY_BASE_DELAY),
        retry_max_delay=_get("OPENROUTER_RETRY_MAX_DELAY", OPENROUTER_RETRY_MAX_DELAY),
        retry_429_max_delay=_get("OPENROUTER_RETRY_429_MAX_DELAY", OPENROUTER_RETRY_429_MAX_DELAY),
        retry_jitter=_get("OPENROUTER_RETRY_JITTER", OPENROUTER_RETRY_JITTER),
        provider_sort=_get("OPENROUTER_PROVIDER_SORT", OPENROUTER_PROVIDER_SORT),
        provider_allow_fallbacks=_get("OPENROUTER_PROVIDER_ALLOW_FALLBACKS", OPENROUTER_PROVIDER_ALLOW_FALLBACKS),
        provider_require_parameters=_get("OPENROUTER_PROVIDER_REQUIRE_PARAMETERS", OPENROUTER_PROVIDER_REQUIRE_PARAMETERS),
        provider_only=_get("OPENROUTER_PROVIDER_ONLY", OPENROUTER_PROVIDER_ONLY),
        provider_ignore=_get("OPENROUTER_PROVIDER_IGNORE", OPENROUTER_PROVIDER_IGNORE),
        preferred_max_latency=_get("OPENROUTER_PREFERRED_MAX_LATENCY", OPENROUTER_PREFERRED_MAX_LATENCY),
        preferred_min_throughput=_get("OPENROUTER_PREFERRED_MIN_THROUGHPUT", OPENROUTER_PREFERRED_MIN_THROUGHPUT),
        service_tier=_get("OPENROUTER_SERVICE_TIER", OPENROUTER_SERVICE_TIER),
    )


def build_discover_config() -> DiscoverConfig:
    """Create a ``DiscoverConfig`` payload for the recommendation service."""
    return DiscoverConfig(
        mode_labels=DISCOVER_MODE_LABELS,
        mode_prompts=DISCOVER_MODE_PROMPTS,
        history_profile_labels=DISCOVER_HISTORY_PROFILE_LABELS,
        history_profile_prompts=DISCOVER_HISTORY_PROFILE_PROMPTS,
        available_genres=DISCOVER_AVAILABLE_GENRES,
    )


# ---------------------------------------------------------------------------
# Public recommendation API
# ---------------------------------------------------------------------------

def get_ai_movie_recommendation(
    user_request: str,
    user_history: str,
    recommendation_mode: str = "similar",
    preferred_genres=None,
    watched_lookup=None,
    history_profile: str = "balanced",
) -> str:
    """Get AI movie recommendations, with a 1-hour cache on successful results."""
    genres_str = ",".join(sorted(preferred_genres or []))
    cache_key = f"ai_rec_{user_request}_{recommendation_mode}_{history_profile}_{genres_str}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return "<p>Sorry, recommendation service is not configured.</p><p><strong>Error:</strong> OPENROUTER_API_KEY is not configured.</p>"

    result = _get_ai_movie_recommendation(
        user_request,
        user_history,
        recommendation_mode=recommendation_mode,
        preferred_genres=preferred_genres,
        watched_lookup=watched_lookup,
        history_profile=history_profile,
        api_key=api_key,
        app_base_url=os.environ.get("APP_BASE_URL", "http://localhost:5000"),
        settings=build_openrouter_settings(),
        discover_config=build_discover_config(),
        logger=logger,
    )
    if result and "Error:" not in result and "rate-limited" not in result:
        cache.set(cache_key, result, timeout=3600)
    return result


def format_ai_response_to_html(text: str, watched_lookup=None) -> str:
    """Convert raw AI response text to formatted HTML."""
    return _format_ai_response_to_html(text, watched_lookup=watched_lookup)
