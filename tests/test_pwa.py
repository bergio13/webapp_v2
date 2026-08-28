import os
import json
from app import app


def test_manifest_endpoint():
    """Test that /manifest.json returns valid PWA web manifest JSON."""
    client = app.test_client()
    response = client.get("/manifest.json")

    assert response.status_code == 200
    assert "application/manifest+json" in response.headers.get("Content-Type", "") or "json" in response.headers.get("Content-Type", "")

    data = json.loads(response.data.decode("utf-8"))
    assert data["name"] == "Kineto // Cinema & TV Tracker"
    assert data["short_name"] == "Kineto"
    assert data["display"] == "standalone"
    assert data["theme_color"] == "#23232e"
    assert data["background_color"] == "#141418"
    assert data["start_url"] == "/home?source=pwa"
    assert data["scope"] == "/"

    # Check icons
    assert "icons" in data and len(data["icons"]) >= 3
    icon_srcs = [i["src"] for i in data["icons"]]
    assert "/static/icons/icon-192x192.png" in icon_srcs
    assert "/static/icons/icon-512x512.png" in icon_srcs
    assert "/static/icons/icon-maskable-512x512.png" in icon_srcs

    # Check shortcuts
    assert "shortcuts" in data and len(data["shortcuts"]) >= 3


def test_service_worker_endpoint():
    """Test that /sw.js is served with proper headers and root scope."""
    client = app.test_client()
    response = client.get("/sw.js")

    assert response.status_code == 200
    assert "javascript" in response.headers.get("Content-Type", "")
    assert response.headers.get("Service-Worker-Allowed") == "/"
    assert "kineto-static" in response.data.decode("utf-8")


def test_offline_fallback_endpoint():
    """Test that /offline renders the offline fallback page."""
    client = app.test_client()
    response = client.get("/offline")

    assert response.status_code == 200
    content = response.data.decode("utf-8")
    assert "Signal Interrupted" in content or "OFFLINE" in content


def test_pwa_icons_exist_on_disk():
    """Verify that all required PWA icons exist in static/icons/."""
    icons = [
        "icon-192x192.png",
        "icon-512x512.png",
        "icon-maskable-512x512.png",
        "apple-touch-icon.png",
        "favicon-32x32.png",
        "favicon-16x16.png",
    ]

    for icon in icons:
        path = os.path.join("static", "icons", icon)
        assert os.path.exists(path), f"Missing icon: {path}"
        assert os.path.getsize(path) > 0, f"Icon is empty: {path}"
