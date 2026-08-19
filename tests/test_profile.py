"""Tests for profile stats calculation, profile rendering, and CSV export."""
import csv
import io
import pytest
from flask import render_template
from flask_login import login_user
from app import app
from utils import build_profile_stats, get_default_profile_stats
from routes.profile import export_csv


class MockUser:
    is_authenticated = True
    id = 1
    username = "gio_cinephile"
    def is_active(self): return True
    def is_anonymous(self): return False
    def get_id(self): return "1"


def test_build_profile_stats_enriched_fields(monkeypatch):
    sample_movies = [
        {"movie": "Dune: Part Two", "p_year": 2024, "director": "Denis Villeneuve", "genre": "Sci-Fi", "rating": 5, "cinema": 1, "rewatch": 0, "tv_show": 0, "v_date": None},
        {"movie": "Arrival", "p_year": 2016, "director": "Denis Villeneuve", "genre": "Sci-Fi", "rating": 5, "cinema": 0, "rewatch": 1, "tv_show": 0, "v_date": None},
        {"movie": "Oppenheimer", "p_year": 2023, "director": "Christopher Nolan", "genre": "Drama, History", "rating": 4, "cinema": 1, "rewatch": 0, "tv_show": 0, "v_date": None},
    ]
    monkeypatch.setattr("utils.get_movies", lambda uid: sample_movies)
    monkeypatch.setattr("utils.get_monthly_movies", lambda uid, m: [sample_movies[0]])

    stats = build_profile_stats(1)
    assert stats["length"] == 3
    assert stats["length_month"] == 1
    assert stats["avg_rating"] == 4.67
    assert stats["rewatch_count"] == 1
    assert stats["cinema_count"] == 2
    assert "cinephile_archetype" in stats
    assert "ratings_histogram" in stats
    assert len(stats["ratings_histogram"]) == 5
    assert len(stats["top_directors_ranked"]) >= 1
    assert stats["top_directors_ranked"][0]["director"] == "Denis Villeneuve"
    assert stats["top_directors_ranked"][0]["count"] == 2


def test_profile_html_renders_minimal(monkeypatch):
    sample_movies = [
        {"movie": "Blade Runner 2049", "p_year": 2017, "director": "Denis Villeneuve", "genre": "Sci-Fi", "rating": 5, "cinema": 1, "rewatch": 1, "tv_show": 0, "v_date": None},
    ]
    monkeypatch.setattr("utils.get_movies", lambda uid: sample_movies)
    monkeypatch.setattr("utils.get_monthly_movies", lambda uid, m: sample_movies)

    stats = build_profile_stats(1)
    user_dict = {"id": 1, "username": "gio_cinephile"}

    with app.app_context(), app.test_request_context("/profile"):
        html = render_template("profile.html", user=user_dict, **stats)
        assert "USER_PROFILE.db" in html
        assert "gio_cinephile" in html
        assert "TOTAL_LOGGED" in html
        assert "RATING SENTIMENT MATRIX" in html


def test_export_csv_endpoint(monkeypatch):
    sample_movies = [
        {"movie": "Interstellar", "p_year": 2014, "director": "Christopher Nolan", "genre": "Sci-Fi", "rating": 5, "cinema": 1, "rewatch": 1, "tv_show": 0, "v_date": "2024-01-15"},
    ]
    monkeypatch.setattr("routes.profile.get_movies", lambda uid: sample_movies)

    with app.test_request_context("/api/export_csv"):
        login_user(MockUser())
        resp = export_csv()
        assert resp.status_code == 200
        assert resp.mimetype == "text/csv"
        assert "attachment; filename=gio_cinephile_kineto_library.csv" in resp.headers.get("Content-Disposition", "")
        
        csv_text = resp.get_data(as_text=True)
        reader = list(csv.reader(io.StringIO(csv_text)))
        assert reader[0] == ["Title", "Year", "Director", "Genre", "Rating", "Watched Date", "Cinema", "Rewatch", "TV Show"]
        assert reader[1][0] == "Interstellar"
        assert reader[1][1] == "2014"


def test_api_movies_rating_filter(monkeypatch):
    mock_db = [
        {"id": 1, "movie": "M1", "director": "D1", "genre": "G1", "p_year": 2020, "v_date": "2024-01-01", "rating": 3, "cinema": 0, "rewatch": 0, "tv_show": 0, "poster": ""},
        {"id": 2, "movie": "M2", "director": "D2", "genre": "G2", "p_year": 2021, "v_date": "2024-01-02", "rating": 2, "cinema": 0, "rewatch": 0, "tv_show": 0, "poster": ""},
        {"id": 3, "movie": "M3", "director": "D3", "genre": "G3", "p_year": 2022, "v_date": "2024-01-03", "rating": 5, "cinema": 0, "rewatch": 0, "tv_show": 0, "poster": ""},
    ]

    def mock_get_movies_paginated(user_id, **kwargs):
        req_rating = kwargs.get("rating")
        filtered = [m for m in mock_db if req_rating is None or m["rating"] == req_rating]
        return filtered, len(filtered)

    monkeypatch.setattr("routes.main.get_movies_paginated", mock_get_movies_paginated)

    with app.test_request_context("/api/movies?rating=3"):
        login_user(MockUser())
        from routes.main import api_movies
        resp = api_movies()
        data = resp.get_json()
        assert data["total_count"] == 1
        assert data["movies"][0]["rating"] == 3

    with app.test_request_context("/api/movies?rating=2"):
        login_user(MockUser())
        from routes.main import api_movies
        resp = api_movies()
        data = resp.get_json()
        assert data["total_count"] == 1
        assert data["movies"][0]["rating"] == 2

