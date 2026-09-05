def test_home_route_for_anonymous_user_returns_ok(client):
    response = client.get("/home")
    assert response.status_code == 200


def test_login_route_returns_ok(client):
    response = client.get("/login")
    assert response.status_code == 200


def test_discover_route_redirects_when_anonymous(client):
    response = client.get("/discover")
    assert response.status_code == 302


def test_discover_renders_cosmos_for_logged_in_user(app_module, monkeypatch):
    from flask_login import login_user

    class MockUser:
        is_authenticated = True
        id = 42
        username = "test"
        def is_active(self): return True
        def is_anonymous(self): return False
        def get_id(self): return "42"

    monkeypatch.setattr(
        "services.cosmos_service.get_movies",
        lambda uid: [{"id": 1, "movie": "Blade Runner", "p_year": 1982, "director": "Ridley Scott", "genre": "Sci-Fi", "rating": 5, "poster": "", "tv_show": 0}],
    )
    monkeypatch.setattr(
        "services.cosmos_service.get_friends",
        lambda uid: [],
    )
    monkeypatch.setattr(
        "services.cosmos_service.get_or_create_personal_watchlist",
        lambda uid: None,
    )
    monkeypatch.setattr(
        "services.cosmos_service.get_watchlist_items",
        lambda wid: [],
    )

    with app_module.app.test_request_context("/discover", method="GET"):
        login_user(MockUser())
        from routes.social import discover
        response_html = discover()

    assert "cosmos-viewport" in response_html
    assert "cosmos-canvas" in response_html


class DummyOpenRouterResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class DummyOpenRouterErrorResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def raise_for_status(self):
        import requests

        raise requests.exceptions.HTTPError(
            f"{self.status_code} Error",
            response=self,
        )

    def json(self):
        return self._payload


def test_openrouter_response_is_formatted_to_html(app_module, monkeypatch):
    import recommendation_service

    monkeypatch.setattr(
        recommendation_service,
        "tmdb_get_movie_details",
        lambda title, year, manual_director=None: {
            "poster": "https://image.tmdb.org/t/p/w200/test.jpg",
            "genre": "Sci-Fi",
            "director": manual_director or "Ridley Scott",
            "title": title,
            "rating": 8.5,
        },
    )

    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert headers["Authorization"] == "Bearer test-openrouter-key"
        assert json["model"] == app_module.OPENROUTER_MODEL_ID
        expected_model_deadline = app_module.OPENROUTER_TOTAL_TIMEOUT
        if len([app_module.OPENROUTER_MODEL_ID, *app_module.OPENROUTER_MODEL_FALLBACKS]) > 1:
            expected_model_deadline = min(expected_model_deadline, app_module.OPENROUTER_MODEL_DEADLINE)
        expected_timeout = min(app_module.OPENROUTER_REQUEST_TIMEOUT, expected_model_deadline)
        assert abs(timeout - expected_timeout) < 0.2
        prompt = json["messages"][0]["content"]
        assert "Recommendation Mode: Similar" in prompt
        assert "History Lens: Balanced Mix" in prompt
        assert "Preferred Genres: No explicit genre pre-filter selected." in prompt
        return DummyOpenRouterResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "1. **Blade Runner (1982) - Ridley Scott**\nGenre: Sci-Fi\nWhy I recommend it: It matches your sci-fi ratings."
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("recommendation_service.requests.post", fake_post)

    response_html = app_module.get_ai_movie_recommendation("Need sci-fi", "History")

    assert "movie-gallery" in response_html
    assert "movie-frame" in response_html
    assert "Blade Runner" in response_html
    assert "1982" in response_html


def test_openrouter_prompt_uses_selected_mode_and_genres(app_module, monkeypatch):
    import recommendation_service

    monkeypatch.setattr(
        recommendation_service,
        "tmdb_get_movie_details",
        lambda title, year, manual_director=None: {
            "poster": "https://image.tmdb.org/t/p/w200/test.jpg",
            "genre": "Drama, Mystery",
            "director": manual_director or "Christopher Nolan",
            "title": title,
            "rating": 8.2,
        },
    )

    captured_prompt = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured_prompt["value"] = json["messages"][0]["content"]
        return DummyOpenRouterResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "1. **The Prestige (2006) - Christopher Nolan**\nGenre: Drama, Mystery\nWhy I recommend it: It aligns with your request."
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("recommendation_service.requests.post", fake_post)

    response_html = app_module.get_ai_movie_recommendation(
        "Need smart mysteries",
        "History",
        recommendation_mode="comfort",
        preferred_genres=["Drama", "Mystery"],
        history_profile="all_time",
    )

    assert "Recommendation Mode: Comfort" in captured_prompt["value"]
    assert "History Lens: All-Time Profile" in captured_prompt["value"]
    assert "Preferred Genres: Drama, Mystery" in captured_prompt["value"]
    assert "The Prestige" in response_html
    assert "2006" in response_html


def test_openrouter_response_with_content_array_is_formatted(app_module, monkeypatch):
    import recommendation_service

    monkeypatch.setattr(
        recommendation_service,
        "tmdb_get_movie_details",
        lambda title, year, manual_director=None: {
            "poster": "https://image.tmdb.org/t/p/w200/test.jpg",
            "genre": "Sci-Fi",
            "director": manual_director or "Denis Villeneuve",
            "title": title,
            "rating": 8.1,
        },
    )

    def fake_post(*_args, **_kwargs):
        return DummyOpenRouterResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "1. **Arrival (2016) - Denis Villeneuve**\nGenre: Sci-Fi\nWhy I recommend it: Strong cerebral sci-fi match.",
                                }
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("recommendation_service.requests.post", fake_post)

    response_html = app_module.get_ai_movie_recommendation("Need sci-fi", "History")

    assert "movie-gallery" in response_html
    assert "movie-frame" in response_html
    assert "Arrival" in response_html
    assert "2016" in response_html


def test_openrouter_error_payload_returns_clear_error(app_module, monkeypatch):
    def fake_post(*_args, **_kwargs):
        return DummyOpenRouterResponse(
            {
                "error": {
                    "message": "No provider available for openrouter/free right now"
                }
            }
        )

    monkeypatch.setattr("recommendation_service.requests.post", fake_post)

    response_html = app_module.get_ai_movie_recommendation("Need sci-fi", "History")

    assert "OpenRouter error" in response_html
    assert "No provider available for openrouter/free right now" in response_html


def test_openrouter_429_returns_user_friendly_rate_limit_message(app_module, monkeypatch):
    monkeypatch.setattr(app_module, "OPENROUTER_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(app_module, "OPENROUTER_MODEL_FALLBACKS", [])

    def fake_post(*_args, **_kwargs):
        return DummyOpenRouterErrorResponse(
            status_code=429,
            payload={"error": {"message": "Too many requests, please retry after 7s"}},
            headers={"Retry-After": "7"},
        )

    monkeypatch.setattr("recommendation_service.requests.post", fake_post)

    response_html = app_module.get_ai_movie_recommendation("Need sci-fi", "History")

    assert "temporarily rate-limited" in response_html
    assert "about 7 seconds" in response_html


def test_openrouter_switches_to_fallback_model_on_primary_rate_limit(app_module, monkeypatch):
    import recommendation_service

    monkeypatch.setattr(
        recommendation_service,
        "tmdb_get_movie_details",
        lambda title, year, manual_director=None: {
            "poster": "https://image.tmdb.org/t/p/w200/test.jpg",
            "genre": "Sci-Fi",
            "director": manual_director or "Denis Villeneuve",
            "title": title,
            "rating": 8.1,
        },
    )

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(app_module, "OPENROUTER_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(app_module, "OPENROUTER_MODEL_ID", "primary/free-model:free")
    monkeypatch.setattr(app_module, "OPENROUTER_MODEL_FALLBACKS", ["fallback/free-model:free"])

    seen_models = []

    def fake_post(_url, headers=None, json=None, timeout=None):
        seen_models.append(json["model"])
        if len(seen_models) == 1:
            return DummyOpenRouterErrorResponse(
                status_code=429,
                payload={"error": {"message": "Too many requests"}},
                headers={"Retry-After": "1"},
            )

        return DummyOpenRouterResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "1. **Arrival (2016) - Denis Villeneuve**\nGenre: Sci-Fi\nWhy I recommend it: fallback model succeeded."
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("recommendation_service.requests.post", fake_post)

    response_html = app_module.get_ai_movie_recommendation("Need sci-fi", "History")

    assert "movie-gallery" in response_html
    assert "Arrival" in response_html
    assert "2016" in response_html
    assert seen_models == ["primary/free-model:free", "fallback/free-model:free"]


def test_openrouter_missing_key_returns_config_error(app_module, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    response_html = app_module.get_ai_movie_recommendation("Need sci-fi", "History")

    assert "OPENROUTER_API_KEY is not configured" in response_html


def test_format_response_adds_dedup_badge_for_strict_title_year_match(app_module):
    source = "1. **Blade Runner (1982) - Ridley Scott**\nGenre: Sci-Fi\nWhy I recommend it: Classic sci-fi."
    html = app_module.format_ai_response_to_html(
        source,
        watched_lookup={("blade runner", 1982)},
    )

    assert "already-watched-badge" in html


def test_format_response_does_not_add_dedup_badge_for_different_year(app_module):
    source = "1. **Blade Runner (1982) - Ridley Scott**\nGenre: Sci-Fi\nWhy I recommend it: Classic sci-fi."
    html = app_module.format_ai_response_to_html(
        source,
        watched_lookup={("blade runner", 1983)},
    )

    assert "already-watched-badge" not in html
