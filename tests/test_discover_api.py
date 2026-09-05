"""
test_discover_api.py — API integration tests for Cosmos endpoints
"""

import pytest
from flask_login import login_user


class MockUser:
    is_authenticated = True
    id = 42
    username = "cinephile_tester"
    def is_active(self): return True
    def is_anonymous(self): return False
    def get_id(self): return "42"


def test_api_cosmos_galaxy_endpoint(app_module, monkeypatch):
    monkeypatch.setattr(
        "services.cosmos_service.get_movies",
        lambda uid: [
            {"id": 10, "movie": "Solaris", "p_year": 1972, "director": "Andrei Tarkovsky", "genre": "Sci-Fi, Drama", "rating": 5, "poster": "", "tv_show": 0},
            {"id": 11, "movie": "Stalker", "p_year": 1979, "director": "Andrei Tarkovsky", "genre": "Sci-Fi, Drama", "rating": 5, "poster": "", "tv_show": 0}
        ]
    )
    monkeypatch.setattr("services.cosmos_service.get_friends", lambda uid: [])
    monkeypatch.setattr("services.cosmos_service.get_or_create_personal_watchlist", lambda uid: None)
    monkeypatch.setattr("services.cosmos_service.get_watchlist_items", lambda wid: [])

    app = app_module.app
    with app.test_request_context("/api/cosmos/galaxy"):
        login_user(MockUser())
        from routes.social import cosmos_galaxy
        resp = cosmos_galaxy()
        data = resp.get_json()

        assert data["success"] is True
        assert "stars" in data
        assert len(data["stars"]) >= 2
        assert "sectors" in data
        assert "stats" in data
        assert data["stats"]["watched_stars"] == 2


def test_api_cosmos_probe_endpoint(app_module, monkeypatch):
    monkeypatch.setattr(
        "services.cosmos_service.get_movies",
        lambda uid: [
            {"id": 10, "movie": "Solaris", "p_year": 1972, "director": "Andrei Tarkovsky", "genre": "Sci-Fi, Drama", "rating": 5, "poster": "", "tv_show": 0}
        ]
    )
    monkeypatch.setattr("services.cosmos_service.get_friends", lambda uid: [])
    monkeypatch.setattr("services.cosmos_service.get_or_create_personal_watchlist", lambda uid: None)
    monkeypatch.setattr("services.cosmos_service.get_watchlist_items", lambda wid: [])

    app = app_module.app
    with app.test_request_context("/api/cosmos/probe", method="POST", json={"x": 50.0, "y": -30.0, "limit": 4}):
        login_user(MockUser())
        from routes.social import cosmos_probe
        resp = cosmos_probe()
        data = resp.get_json()

        assert data["success"] is True
        assert "recommendations" in data
        assert len(data["recommendations"]) <= 4
