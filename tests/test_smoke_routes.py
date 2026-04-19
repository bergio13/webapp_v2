def test_home_route_for_anonymous_user_returns_ok(client):
    response = client.get("/home")
    assert response.status_code == 200


def test_login_route_returns_ok(client):
    response = client.get("/login")
    assert response.status_code == 200


def test_discover_route_redirects_when_anonymous(client):
    response = client.get("/discover")
    assert response.status_code == 302


def test_discover_post_renders_recommendations_for_logged_in_user(client, app_module, monkeypatch):
    with client.session_transaction() as active_session:
        active_session["loggedin"] = True
        active_session["id"] = 42

    captured = {}

    monkeypatch.setattr(
        app_module,
        "get_user_watch_history_summary",
        lambda *_args, **_kwargs: "History",
    )

    monkeypatch.setattr(
        app_module,
        "get_watched_title_year_lookup",
        lambda *_args, **_kwargs: {("test movie", 2024)},
    )

    def fake_get_ai_movie_recommendation(
        user_request,
        user_history,
        recommendation_mode="similar",
        preferred_genres=None,
        watched_lookup=None,
        history_profile="balanced",
    ):
        captured["user_request"] = user_request
        captured["user_history"] = user_history
        captured["recommendation_mode"] = recommendation_mode
        captured["preferred_genres"] = preferred_genres
        captured["watched_lookup"] = watched_lookup
        captured["history_profile"] = history_profile
        return "<ol><li><strong>Test Movie (2024) - Director</strong></li></ol>"

    monkeypatch.setattr(
        app_module,
        "get_ai_movie_recommendation",
        fake_get_ai_movie_recommendation,
    )

    response = client.post(
        "/discover",
        data={
            "user_request": "Find me sci-fi",
            "recommendation_mode": "comfort",
            "history_profile": "recent",
            "preferred_genres": ["Sci-Fi", "Thriller"],
        },
    )

    assert response.status_code == 200
    assert b"Test Movie (2024) - Director" in response.data
    assert captured["user_request"] == "Find me sci-fi"
    assert captured["user_history"] == "History"
    assert captured["recommendation_mode"] == "comfort"
    assert captured["preferred_genres"] == ["Sci-Fi", "Thriller"]
    assert captured["watched_lookup"] == {("test movie", 2024)}
    assert captured["history_profile"] == "recent"


class DummyOpenRouterResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_openrouter_response_is_formatted_to_html(app_module, monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert headers["Authorization"] == "Bearer test-openrouter-key"
        assert json["model"] == "openrouter/free"
        assert timeout == 30
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

    monkeypatch.setattr(app_module.requests, "post", fake_post)

    response_html = app_module.get_ai_movie_recommendation("Need sci-fi", "History")

    assert "<ol>" in response_html
    assert "Blade Runner (1982) - Ridley Scott" in response_html


def test_openrouter_prompt_uses_selected_mode_and_genres(app_module, monkeypatch):
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

    monkeypatch.setattr(app_module.requests, "post", fake_post)

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
    assert "The Prestige (2006) - Christopher Nolan" in response_html


def test_openrouter_response_with_content_array_is_formatted(app_module, monkeypatch):
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

    monkeypatch.setattr(app_module.requests, "post", fake_post)

    response_html = app_module.get_ai_movie_recommendation("Need sci-fi", "History")

    assert "<ol>" in response_html
    assert "Arrival (2016) - Denis Villeneuve" in response_html


def test_openrouter_error_payload_returns_clear_error(app_module, monkeypatch):
    def fake_post(*_args, **_kwargs):
        return DummyOpenRouterResponse(
            {
                "error": {
                    "message": "No provider available for openrouter/free right now"
                }
            }
        )

    monkeypatch.setattr(app_module.requests, "post", fake_post)

    response_html = app_module.get_ai_movie_recommendation("Need sci-fi", "History")

    assert "OpenRouter error" in response_html
    assert "No provider available for openrouter/free right now" in response_html


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
