import pytest
from app import app
from flask_login import login_user
from database import get_enriched_friends, search_users_by_query

class MockUser:
    is_authenticated = True
    id = 1
    username = 'gio'
    def is_active(self): return True
    def is_anonymous(self): return False
    def get_id(self): return '1'

def test_search_users_by_query():
    res = search_users_by_query('gio', limit=5)
    assert isinstance(res, list)

def test_get_enriched_friends():
    friends = get_enriched_friends(1)
    assert isinstance(friends, list)
    if len(friends) > 0:
        f = friends[0]
        assert "user_id" in f
        assert "f_username" in f
        assert "film_count" in f
        assert "cinephile_level" in f
        assert "favorite_genre" in f
        assert "sync_score" in f

def test_friends_route_renders():
    with app.test_request_context('/friends'):
        login_user(MockUser())
        from routes.social import search_friends
        html = search_friends()
        assert "Friends" in html
        assert "find_user:" in html
        assert "Connections" in html

def test_api_users_search_ajax():
    with app.test_request_context('/api/users/search?q=gio'):
        login_user(MockUser())
        from routes.social import search_users_ajax
        resp = search_users_ajax()
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

def test_api_follow_ajax():
    with app.test_request_context('/api/follow_ajax', method='POST', json={"user_id": 99999, "username": "test_bot"}):
        login_user(MockUser())
        from routes.social import follow_ajax
        resp = follow_ajax()
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True

def test_api_unfollow_ajax():
    with app.test_request_context('/api/unfollow_ajax', method='POST', json={"user_id": 99999, "username": "test_bot"}):
        login_user(MockUser())
        from routes.social import unfollow_ajax
        resp = unfollow_ajax()
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True
