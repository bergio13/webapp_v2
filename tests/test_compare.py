import pytest
from app import app
from flask_login import login_user
from database import get_taste_match

class MockUser:
    is_authenticated = True
    id = 1
    username = 'gio'
    def is_active(self): return True
    def is_anonymous(self): return False
    def get_id(self): return '1'

def test_get_taste_match_structure():
    match = get_taste_match(1, 16)
    assert isinstance(match, dict)
    assert "match_percent" in match
    assert "shared_count" in match
    assert "shared_movies" in match
    assert "mutual_favorites" in match
    assert "biggest_debates" in match
    assert "recommendations_for_you" in match
    assert "recommendations_for_friend" in match
    assert "genre_comparison" in match
    assert "library_overlap" in match
    assert "rating_similarity" in match
    assert "agreement_rate" in match
    assert "harsher_critic" in match

def test_get_taste_match_shared_pair():
    # User 15 and 16 have multiple shared movies
    match = get_taste_match(15, 16)
    assert match["shared_count"] > 0
    assert len(match["shared_movies"]) == match["shared_count"]
    assert 0 <= match["match_percent"] <= 100
    assert 0 <= match["agreement_rate"] <= 100

def test_compare_route_renders():
    with app.test_request_context('/compare/Luckosky'):
        login_user(MockUser())
        from routes.social import compare_taste
        html = compare_taste('Luckosky')
        assert "TASTE_SYNC_PROTOCOL.db" in html
        assert "SYNC INDEX" in html
        assert "SHARED FILMS" in html
        assert "GENRE SYNERGY" in html
        assert "MUTUAL FAVORITES" not in html
        assert "RECOMMENDATIONS" not in html
        assert "CINEMATIC SOULMATES" not in html

def test_format_display_title():
    from utils import format_display_title, clean_and_format
    assert format_display_title("superstore, Season 4") == "Superstore, Season 4"
    assert format_display_title("superstore, Season 2") == "Superstore, Season 2"
    assert format_display_title("superstore") == "Superstore"
    assert format_display_title("marty supreme") == "Marty Supreme"
    assert format_display_title("Superstore, Season 4") == "Superstore, Season 4"
    assert clean_and_format("superstore") == "Superstore"
    assert clean_and_format("marty supreme") == "Marty Supreme"
