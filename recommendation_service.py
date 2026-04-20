import random
import re
import time
from dataclasses import dataclass
from typing import Optional, Sequence

import requests


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


def build_watched_title_year_lookup(movies):
    """Build a strict (title, year) set for already watched movies."""
    watched_lookup = set()
    for movie in movies or []:
        normalized_title = normalize_title_for_match(movie.get("movie"))
        year = parse_year(movie.get("p_year"))
        if normalized_title and year:
            watched_lookup.add((normalized_title, year))
    return watched_lookup


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
    for idx, movie in enumerate(selected_movies, 1):
        rating_text = f"{movie['rating']}/10" if movie["rating"] else "unrated"
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
        summary += f"\nAverage rating in this lens: {avg_rating:.1f}/10\n"
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
    provider = {
        "allow_fallbacks": settings.provider_allow_fallbacks,
        "require_parameters": settings.provider_require_parameters,
    }

    if settings.provider_sort:
        provider["sort"] = settings.provider_sort
    if settings.provider_only:
        provider["only"] = list(settings.provider_only)
    if settings.provider_ignore:
        provider["ignore"] = list(settings.provider_ignore)
    if settings.preferred_max_latency is not None:
        provider["preferred_max_latency"] = settings.preferred_max_latency
    if settings.preferred_min_throughput is not None:
        provider["preferred_min_throughput"] = settings.preferred_min_throughput

    return provider


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

    try:
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
            "HTTP-Referer": app_base_url,
            "X-Title": "Kineto",
        }
        model_candidates = _build_openrouter_model_candidates(settings)
        if not model_candidates:
            raise RuntimeError("No OpenRouter model candidates configured")

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
    """Convert AI response text to HTML with better formatting."""
    watched_lookup = watched_lookup or set()

    lines = text.split("\n")
    html_lines = []
    in_list = False
    current_item_open = False

    for raw_line in lines:
        line = raw_line.strip()

        title_match = re.match(r"^\d+\.\s*\*\*(.*?)\*\*", line)
        if title_match:
            if not in_list:
                html_lines.append("<ol>")
                in_list = True

            if current_item_open:
                html_lines.append("</li>")

            heading = title_match.group(1)
            recommended_title, recommended_year = extract_title_year_from_heading(heading)
            normalized_title = normalize_title_for_match(recommended_title)
            show_dedup_badge = (
                normalized_title
                and recommended_year
                and (normalized_title, recommended_year) in watched_lookup
            )
            dedup_badge = " <span class=\"already-watched-badge\">Already watched</span>" if show_dedup_badge else ""

            html_lines.append(f"<li><strong>{heading}</strong>{dedup_badge}")
            current_item_open = True
        elif line.startswith("Genre:") or line.startswith("Why I recommend it:"):
            line = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", line)
            line = re.sub(r"\*(.*?)\*", r"<em>\1</em>", line)
            html_lines.append(f"<p>{line}</p>")
        elif line and not re.match(r"^\d+\.", line):
            line = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", line)
            line = re.sub(r"\*(.*?)\*", r"<em>\1</em>", line)
            if line:
                html_lines.append(f"<p>{line}</p>")

    if current_item_open:
        html_lines.append("</li>")
    if in_list:
        html_lines.append("</ol>")

    return "\n".join(html_lines)
