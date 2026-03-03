"""Tests for the main app routes."""


def test_index_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Home Dashboard" in resp.text
    assert "grid-stack" in resp.text
