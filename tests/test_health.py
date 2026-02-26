"""Tests for the index and health endpoints (no browser needed)."""


def test_index(client):
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["msg"] == "Playcha is ready!"
    assert "version" in data


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
