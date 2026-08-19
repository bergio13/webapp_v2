"""Tests for the In-App Movie Detail Drawer and /api/media_details endpoint."""
import pytest
from app import app
from services import tmdb_service

def test_api_media_details_missing_params():
    with app.test_client() as client:
        res = client.get('/api/media_details')
        assert res.status_code == 400
        data = res.get_json()
        assert data.get('success') is False

def test_get_full_media_details_structure(monkeypatch):
    """Test get_full_media_details parsing with mocked TMDB response."""
    sample_tmdb_response = {
        "id": 12345,
        "title": "Cyberpunk Odyssey",
        "original_title": "Cyberpunk Odyssey (Original)",
        "tagline": "The future is closer than you think.",
        "overview": "A thrilling cyber tale across the matrix.",
        "release_date": "2024-11-15",
        "runtime": 135,
        "vote_average": 8.4,
        "poster_path": "/sample_poster.jpg",
        "backdrop_path": "/sample_backdrop.jpg",
        "genres": [{"id": 878, "name": "Sci-Fi"}, {"id": 28, "name": "Action"}],
        "credits": {
            "crew": [{"job": "Director", "name": "Elena Vance"}],
            "cast": [
                {"name": "Deckard Shaw", "character": "Agent Zero", "profile_path": "/actor1.jpg"}
            ]
        },
        "videos": {
            "results": [
                {
                    "site": "YouTube",
                    "type": "Trailer",
                    "official": True,
                    "key": "abc123xyz",
                    "name": "Official Main Trailer"
                }
            ]
        },
        "watch/providers": {
            "results": {
                "IT": {
                    "link": "https://www.justwatch.com/it/sample",
                    "flatrate": [{"provider_name": "Netflix", "logo_path": "/netflix.jpg"}],
                    "rent": [{"provider_name": "Apple TV", "logo_path": "/appletv.jpg"}]
                }
            }
        }
    }

    class MockResponse:
        status_code = 200
        def json(self):
            return sample_tmdb_response

    import requests
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockResponse())

    res = tmdb_service.get_full_media_details(tmdb_id=12345, country="IT")
    assert res["success"] is True
    assert res["title"] == "Cyberpunk Odyssey"
    assert res["director"] == "Elena Vance"
    assert res["formatted_runtime"] == "2h 15m"
    assert res["trailer"]["key"] == "abc123xyz"
    assert "https://www.youtube-nocookie.com/embed/abc123xyz" in res["trailer"]["embed_url"]
    assert len(res["watch_providers"]["flatrate"]) == 1
    assert res["watch_providers"]["flatrate"][0]["name"] == "Netflix"
    assert len(res["cast"]) == 1
    assert res["cast"][0]["name"] == "Deckard Shaw"

def test_api_media_details_route_success(monkeypatch):
    """Test /api/media_details endpoint returns JSON structure."""
    fake_details = {
        "success": True,
        "id": 999,
        "title": "Mock Film",
        "year": "2024",
        "trailer": {"key": "testkey", "embed_url": "https://www.youtube-nocookie.com/embed/testkey"},
        "watch_providers": {"flatrate": [], "rent": []}
    }

    monkeypatch.setattr(tmdb_service, "get_full_media_details", lambda **kwargs: fake_details)

    with app.test_client() as client:
        res = client.get('/api/media_details?title=Mock%20Film&year=2024&country=IT')
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["title"] == "Mock Film"
        assert data["trailer"]["key"] == "testkey"
