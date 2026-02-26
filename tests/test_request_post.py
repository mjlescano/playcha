"""Tests for the request.post command with a real Camoufox browser."""


def test_post_echoes_body(client, mock_server_url):
    resp = client.post(
        "/v1",
        json={
            "cmd": "request.post",
            "url": f"{mock_server_url}/submit",
            "postData": "username=testuser&password=secret",
            "maxTimeout": 30000,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"

    html = data["solution"]["response"]
    assert "username=testuser" in html
    assert "password=secret" in html


def test_post_missing_post_data(client, mock_server_url):
    resp = client.post(
        "/v1",
        json={
            "cmd": "request.post",
            "url": f"{mock_server_url}/submit",
            "maxTimeout": 30000,
        },
    )
    assert resp.status_code == 500
    data = resp.json()
    assert data["status"] == "error"
    assert "postData" in data["message"]


def test_post_missing_url(client):
    resp = client.post(
        "/v1",
        json={
            "cmd": "request.post",
            "postData": "foo=bar",
            "maxTimeout": 30000,
        },
    )
    assert resp.status_code == 500
    data = resp.json()
    assert data["status"] == "error"
    assert "url" in data["message"].lower()
