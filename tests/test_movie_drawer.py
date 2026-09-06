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


def test_api_media_details_route_with_tv_season(monkeypatch):
    """Test /api/media_details endpoint correctly augments TV season details."""
    import services.catalog_service as catalog_service
    fake_details = {
        "success": True,
        "tmdb_id": 203857,
        "title": "The Diplomat",
        "year": "2023",
        "poster": "https://image.tmdb.org/t/p/w500/series_poster.jpg",
        "overview": "Series overview",
        "trailer": None,
        "watch_providers": {"flatrate": [], "rent": []}
    }
    fake_season = {
        "season_key": "203857_s3",
        "tmdb_id": 203857,
        "season_number": 3,
        "show_title": "The Diplomat",
        "season_name": "Season 3",
        "year": 2025,
        "poster": "https://image.tmdb.org/t/p/w500/season3_poster.jpg",
        "overview": "Season 3 specific synopsis",
        "director": "Alex Graves",
        "lead_actors": "Keri Russell, Rufus Sewell",
        "episode_count": 8
    }

    monkeypatch.setattr(tmdb_service, "get_full_media_details", lambda **kwargs: fake_details)
    monkeypatch.setattr(catalog_service, "get_tv_season_catalog_item", lambda tmdb_id, season_num: fake_season)

    with app.test_client() as client:
        res = client.get('/api/media_details?tmdb_id=203857&season=3&tv=1')
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["season_number"] == 3
        assert data["season_name"] == "Season 3"
        assert "Season 3" in data["title"]
        assert data["poster"] == "https://image.tmdb.org/t/p/w500/season3_poster.jpg"
        assert data["overview"] == "Season 3 specific synopsis"
        assert data["director"] == "Alex Graves"
        assert data["runtime"] == "8 Episodes"
        assert len(data["cast"]) == 2
        assert data["cast"][0]["name"] == "Keri Russell"


def test_api_media_details_route_with_creator_and_director(monkeypatch):
    """Test /api/media_details endpoint returns both creator and director for dual display."""
    import services.catalog_service as catalog_service
    fake_details = {
        "success": True,
        "tmdb_id": 45790,
        "media_type": "tv",
        "title": "JoJo's Bizarre Adventure",
        "year": "2012",
        "creator": "Hirohiko Araki",
        "director": "Various Directors",
        "poster": "https://image.tmdb.org/t/p/w500/jojo.jpg"
    }
    fake_season = {
        "season_key": "45790_s2",
        "tmdb_id": 45790,
        "season_number": 2,
        "show_title": "JoJo's Bizarre Adventure",
        "season_name": "Stardust Crusaders",
        "year": 2014,
        "director": "Naokatsu Tsuda, Kenichi Suzuki",
        "creator": "Hirohiko Araki",
        "episode_count": 48
    }

    monkeypatch.setattr(tmdb_service, "get_full_media_details", lambda **kwargs: fake_details)
    monkeypatch.setattr(catalog_service, "get_tv_season_catalog_item", lambda tmdb_id, season_num: fake_season)

    with app.test_client() as client:
        res = client.get('/api/media_details?tmdb_id=45790&season=2&tv=1')
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert data["creator"] == "Hirohiko Araki"
        assert data["director"] == "Naokatsu Tsuda, Kenichi Suzuki"
        assert data["season_name"] == "Stardust Crusaders"


def test_extract_tv_season_director_prioritizes_creator_over_episodic_directors():
    """Verify extract_tv_season_director chooses Series Creator over multi-director episodic tallies."""
    from services.catalog_service import extract_tv_season_director
    
    # 8 episodes split between Alex Graves (4), Tucker Gates (2), Liza Johnson (2)
    season_data = {
        "credits": {"crew": []},
        "episodes": [
            {"episode_number": 1, "crew": [{"job": "Director", "name": "Alex Graves"}]},
            {"episode_number": 2, "crew": [{"job": "Director", "name": "Alex Graves"}]},
            {"episode_number": 3, "crew": [{"job": "Director", "name": "Tucker Gates"}]},
            {"episode_number": 4, "crew": [{"job": "Director", "name": "Tucker Gates"}]},
            {"episode_number": 5, "crew": [{"job": "Director", "name": "Liza Johnson"}]},
            {"episode_number": 6, "crew": [{"job": "Director", "name": "Liza Johnson"}]},
            {"episode_number": 7, "crew": [{"job": "Director", "name": "Alex Graves"}]},
            {"episode_number": 8, "crew": [{"job": "Director", "name": "Alex Graves"}]},
        ]
    }
    series_data = {
        "created_by": [{"id": 1, "name": "Debora Cahn"}]
    }
    
    extracted = extract_tv_season_director(season_data, series_data)
    assert extracted == "Debora Cahn"


def test_extract_tv_season_director_preserves_anime_series_director():
    """Verify anime Series Director / Chief Director in season crew is preserved."""
    from services.catalog_service import extract_tv_season_director
    
    season_data = {
        "credits": {
            "crew": [
                {"job": "Chief Director", "name": "Naokatsu Tsuda"},
                {"job": "Series Director", "name": "Kenichi Suzuki"}
            ]
        },
        "episodes": []
    }
    series_data = {
        "created_by": [{"id": 1, "name": "Hirohiko Araki"}]
    }
    
    extracted = extract_tv_season_director(season_data, series_data)
    assert "Naokatsu Tsuda" in extracted
    assert "Kenichi Suzuki" in extracted


def test_tmdb_fallback_search_prioritizes_tv_over_compilation_movie(monkeypatch):
    """Verify that searching for a TV show with a season air year that matches a compilation movie still chooses the TV show."""
    mock_search_results = [
        {"id": 1429, "title": "Attack on Titan", "year": "2013", "type": "tv"},
        {"id": 295830, "title": "Attack on Titan", "year": "2015", "type": "movie"},
        {"id": 714194, "title": "Attack on Titan: Chronicle", "year": "2020", "type": "movie"},
    ]
    monkeypatch.setattr(tmdb_service, "search_titles", lambda query, is_tv=False, limit=8: mock_search_results)
    
    class MockResponse:
        status_code = 200
        def json(self):
            return {
                "id": 1429,
                "name": "Attack on Titan",
                "first_air_date": "2013-04-07",
                "overview": "Several hundred years ago, humans were nearly exterminated by titans...",
                "poster_path": "/aot.jpg",
                "backdrop_path": None,
                "genres": [{"name": "Animation"}],
                "vote_average": 8.7,
                "created_by": [{"name": "Hajime Isayama"}],
                "credits": {"crew": [], "cast": []},
                "videos": {"results": []},
                "watch/providers": {"results": {}}
            }

    import requests
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockResponse())
    monkeypatch.setattr(tmdb_service.tmdb, "api_key", "fake_key")

    details = tmdb_service.get_full_media_details(title="Attack on Titan", year="2020", is_tv=True)
    assert details["success"] is True
    assert details["tmdb_id"] == 1429
    assert details["media_type"] == "tv"
    assert details["title"] == "Attack on Titan"


def test_api_media_details_does_not_accumulate_season_titles(monkeypatch):
    """Verify that opening multiple seasons of the same TV show sequentially does not accumulate '- Season X - Season Y' in the title."""
    import services.catalog_service as catalog_service
    fake_details = {
        "success": True,
        "tmdb_id": 62649,
        "media_type": "tv",
        "title": "Superstore",
        "year": "2015",
        "poster": "https://image.tmdb.org/t/p/w500/superstore.jpg"
    }

    def fake_get_season(tmdb_id, s_num):
        return {
            "season_key": f"{tmdb_id}_s{s_num}",
            "tmdb_id": tmdb_id,
            "season_number": s_num,
            "show_title": "Superstore",
            "season_name": f"Season {s_num}",
            "year": 2015 + s_num,
            "poster": f"https://image.tmdb.org/t/p/w500/superstore_s{s_num}.jpg"
        }

    monkeypatch.setattr(tmdb_service, "get_full_media_details", lambda **kwargs: fake_details)
    monkeypatch.setattr(catalog_service, "get_tv_season_catalog_item", fake_get_season)

    with app.test_client() as client:
        res6 = client.get('/api/media_details?tmdb_id=62649&season=6&tv=1')
        assert res6.get_json()["title"] == "Superstore - Season 6"

        res5 = client.get('/api/media_details?tmdb_id=62649&season=5&tv=1')
        assert res5.get_json()["title"] == "Superstore - Season 5"

        res4 = client.get('/api/media_details?tmdb_id=62649&season=4&tv=1')
        assert res4.get_json()["title"] == "Superstore - Season 4"

        res3 = client.get('/api/media_details?tmdb_id=62649&season=3&tv=1')
        assert res3.get_json()["title"] == "Superstore - Season 3"





