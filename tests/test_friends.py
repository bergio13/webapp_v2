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


def test_friends_activity_cinema_and_rewatch_tags(monkeypatch):
    from flask import render_template
    test_activity = [
        {'id': 1, 'movie': 'Dune', 'director': 'Denis', 'p_year': 2024, 'rating': 5, 'cinema': 0, 'rewatch': 0, 'tv_show': 0, 'poster': '', 'f_username': 'alice'},
        {'id': 2, 'movie': 'Tenet', 'director': 'Nolan', 'p_year': 2020, 'rating': 4, 'cinema': '0', 'rewatch': '0', 'tv_show': '0', 'poster': '', 'f_username': 'bob'},
        {'id': 3, 'movie': 'Oppenheimer', 'director': 'Nolan', 'p_year': 2023, 'rating': 5, 'cinema': 1, 'rewatch': 1, 'tv_show': 0, 'poster': '', 'f_username': 'charlie'},
        {'id': 4, 'movie': 'Barbie', 'director': 'Gerwig', 'p_year': 2023, 'rating': 4, 'cinema': '1', 'rewatch': '1', 'tv_show': 0, 'poster': '', 'f_username': 'dana'}
    ]
    monkeypatch.setattr("routes.social.get_friend_activity", lambda uid, limit=30: test_activity)
    monkeypatch.setattr("routes.social.get_enriched_friends", lambda uid: [])

    with app.test_request_context('/friends'):
        login_user(MockUser())
        from routes.social import search_friends
        html = search_friends()
        assert 'data-cinema="0"' in html
        assert 'data-cinema="1"' in html
        assert 'data-rewatch="0"' in html
        assert 'data-rewatch="1"' in html
        assert html.count('CINEMA</span>') == 2
        assert html.count('REWATCH</span>') == 2
