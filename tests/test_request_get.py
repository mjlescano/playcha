"""Tests for the request.get command with a real Camoufox browser."""

import base64
import time


def test_get_plain_page(client, mock_server_url):
    resp = client.post(
        "/v1",
        json={
            "cmd": "request.get",
            "url": f"{mock_server_url}/plain",
            "maxTimeout": 30000,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["message"] == "Challenge not detected!"

    solution = data["solution"]
    assert "Hello from Playcha test server" in solution["response"]
    assert solution["url"].endswith("/plain")
    assert solution["status"] == 200
    assert isinstance(solution["cookies"], list)
    assert len(solution["userAgent"]) > 0


def test_get_return_only_cookies(client, mock_server_url):
    resp = client.post(
        "/v1",
        json={
            "cmd": "request.get",
            "url": f"{mock_server_url}/set-cookies",
            "maxTimeout": 30000,
            "returnOnlyCookies": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"

    solution = data["solution"]
    assert "response" not in solution or solution.get("response") is None
    assert isinstance(solution["cookies"], list)
    assert len(solution["cookies"]) > 0


def test_get_with_screenshot(client, mock_server_url):
    resp = client.post(
        "/v1",
        json={
            "cmd": "request.get",
            "url": f"{mock_server_url}/screenshot-test",
            "maxTimeout": 30000,
            "returnScreenshot": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"

    screenshot = data["solution"]["screenshot"]
    assert screenshot is not None
    raw = base64.b64decode(screenshot)
    # PNG files start with the PNG magic bytes
    assert raw[:4] == b"\x89PNG"


def test_get_with_disable_media(client, mock_server_url):
    resp = client.post(
        "/v1",
        json={
            "cmd": "request.get",
            "url": f"{mock_server_url}/plain",
            "maxTimeout": 30000,
            "disableMedia": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "Hello from Playcha test server" in data["solution"]["response"]


def test_get_set_cookies(client, mock_server_url):
    resp = client.post(
        "/v1",
        json={
            "cmd": "request.get",
            "url": f"{mock_server_url}/set-cookies",
            "maxTimeout": 30000,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"

    cookie_names = [c["name"] for c in data["solution"]["cookies"]]
    assert "test_cookie" in cookie_names
    assert "session_id" in cookie_names

    test_cookie = next(c for c in data["solution"]["cookies"] if c["name"] == "test_cookie")
    assert test_cookie["value"] == "cookie_value"


def test_get_wait_in_seconds(client, mock_server_url):
    start = time.monotonic()
    resp = client.post(
        "/v1",
        json={
            "cmd": "request.get",
            "url": f"{mock_server_url}/plain",
            "maxTimeout": 30000,
            "waitInSeconds": 2,
        },
    )
    elapsed = time.monotonic() - start
    assert resp.status_code == 200
    assert elapsed >= 2.0


def test_get_missing_url(client):
    resp = client.post(
        "/v1",
        json={
            "cmd": "request.get",
            "maxTimeout": 30000,
        },
    )
    assert resp.status_code == 500
    data = resp.json()
    assert data["status"] == "error"
    assert "url" in data["message"].lower()


def test_get_with_post_data_rejected(client, mock_server_url):
    resp = client.post(
        "/v1",
        json={
            "cmd": "request.get",
            "url": f"{mock_server_url}/plain",
            "postData": "foo=bar",
            "maxTimeout": 30000,
        },
    )
    assert resp.status_code == 500
    data = resp.json()
    assert data["status"] == "error"
    assert "postData" in data["message"] or "postBody" in data["message"]
