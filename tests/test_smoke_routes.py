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

    monkeypatch.setattr(
        app_module,
        "get_user_watch_history_summary",
        lambda *_args, **_kwargs: "History",
    )
    monkeypatch.setattr(
        app_module,
        "get_ai_movie_recommendation",
        lambda *_args, **_kwargs: "<ol><li><strong>Test Movie (2024) - Director</strong></li></ol>",
    )

    response = client.post(
        "/discover",
        data={"user_request": "Find me sci-fi", "history_percentage": "40"},
    )

    assert response.status_code == 200
    assert b"Test Movie (2024) - Director" in response.data


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
