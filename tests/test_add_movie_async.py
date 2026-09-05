"""Tests for async background catalog enrichment and add_movie fast-path."""
from unittest.mock import patch, MagicMock
from routes.movies import _async_catalog_enrichment


def test_async_catalog_enrichment_runs_safely():
    """Verify that _async_catalog_enrichment runs smoothly and invokes catalog service without throwing."""
    with patch("services.catalog_service.fetch_and_enrich_from_tmdb") as mock_enrich, \
         patch("services.catalog_service.upsert_catalog_item") as mock_upsert:
        
        mock_enrich.return_value = {
            "title": "Inception",
            "year": 2010,
            "tmdb_id": 27205,
            "genres": "Action, Sci-Fi",
            "director": "Christopher Nolan"
        }
        
        # Test movie enrichment
        _async_catalog_enrichment("Inception", 2010, 27205, is_tv=False, director="Christopher Nolan", genre="Sci-Fi")
        
        assert mock_enrich.called
        assert mock_upsert.called
        assert mock_upsert.call_args[1].get("compute_embedding") is True


def test_async_catalog_enrichment_tv_season():
    """Verify that TV show triggers both show and season enrichment."""
    with patch("services.catalog_service.fetch_and_enrich_from_tmdb") as mock_enrich, \
         patch("services.catalog_service.upsert_catalog_item") as mock_upsert, \
         patch("services.catalog_service.fetch_and_enrich_tv_season") as mock_season_enrich, \
         patch("services.catalog_service.upsert_tv_season_catalog_item") as mock_season_upsert:
        
        mock_enrich.return_value = {
            "title": "Dark",
            "year": 2017,
            "tmdb_id": 70523,
            "genres": "Sci-Fi, Mystery"
        }
        mock_season_enrich.return_value = {
            "tmdb_id": 70523,
            "season_number": 1,
            "show_title": "Dark"
        }
        
        _async_catalog_enrichment("Dark", 2017, 70523, is_tv=True, season_num=1, director="Baran bo Odar")
        
        assert mock_enrich.called
        assert mock_upsert.called
        assert mock_season_enrich.called
        assert mock_season_upsert.called


def test_get_tv_seasons_list_standard_show():
    """Verify get_tv_seasons_list extracts seasons from standard TMDb TV response."""
    from services.tmdb_service import get_tv_seasons_list
    
    mock_details = {
        "name": "Breaking Bad",
        "overview": "A high school chemistry teacher diagnosed with cancer...",
        "poster_path": "/main.jpg",
        "seasons": [
            {"season_number": 0, "name": "Specials", "poster_path": "/s0.jpg", "episode_count": 5},
            {"season_number": 1, "name": "Season 1", "poster_path": "/s1.jpg", "episode_count": 7, "air_date": "2008-01-20"},
            {"season_number": 2, "name": "Season 2", "poster_path": "/s2.jpg", "episode_count": 13, "air_date": "2009-03-08"}
        ]
    }
    
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_details
        mock_get.return_value = mock_resp
        
        seasons = get_tv_seasons_list(1396, "Breaking Bad")
        
        assert len(seasons) == 2
        assert seasons[0]["season_number"] == 1
        assert seasons[0]["name"] == "Season 1"
        assert "s1.jpg" in seasons[0]["poster"]
        assert seasons[1]["season_number"] == 2
        assert seasons[1]["name"] == "Season 2"
        assert "s2.jpg" in seasons[1]["poster"]
