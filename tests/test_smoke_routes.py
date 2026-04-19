def test_home_route_for_anonymous_user_returns_ok(client):
    response = client.get("/home")
    assert response.status_code == 200


def test_login_route_returns_ok(client):
    response = client.get("/login")
    assert response.status_code == 200
