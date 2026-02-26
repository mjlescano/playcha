"""Tests for session lifecycle: create, list, destroy, and request with session."""


def test_session_create(client):
    resp = client.post(
        "/v1",
        json={
            "cmd": "sessions.create",
            "session": "test-session-1",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["message"] == "Session created successfully."
    assert data["session"] == "test-session-1"


def test_session_create_duplicate(client):
    # Ensure it exists first
    client.post(
        "/v1",
        json={
            "cmd": "sessions.create",
            "session": "test-session-dup",
        },
    )
    resp = client.post(
        "/v1",
        json={
            "cmd": "sessions.create",
            "session": "test-session-dup",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["message"] == "Session already exists."


def test_session_list_includes_created(client):
    client.post(
        "/v1",
        json={
            "cmd": "sessions.create",
            "session": "test-session-list",
        },
    )
    resp = client.post("/v1", json={"cmd": "sessions.list"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "test-session-list" in data["sessions"]


def test_session_destroy(client):
    client.post(
        "/v1",
        json={
            "cmd": "sessions.create",
            "session": "test-session-destroy",
        },
    )
    resp = client.post(
        "/v1",
        json={
            "cmd": "sessions.destroy",
            "session": "test-session-destroy",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["message"] == "The session has been removed."


def test_session_destroy_nonexistent(client):
    resp = client.post(
        "/v1",
        json={
            "cmd": "sessions.destroy",
            "session": "does-not-exist",
        },
    )
    assert resp.status_code == 500
    data = resp.json()
    assert data["status"] == "error"
    assert "doesn't exist" in data["message"]


def test_session_list_after_destroy(client):
    client.post(
        "/v1",
        json={
            "cmd": "sessions.create",
            "session": "test-session-gone",
        },
    )
    client.post(
        "/v1",
        json={
            "cmd": "sessions.destroy",
            "session": "test-session-gone",
        },
    )
    resp = client.post("/v1", json={"cmd": "sessions.list"})
    data = resp.json()
    assert "test-session-gone" not in data["sessions"]


def test_request_with_session(client, mock_server_url):
    client.post(
        "/v1",
        json={
            "cmd": "sessions.create",
            "session": "test-session-req",
        },
    )

    resp1 = client.post(
        "/v1",
        json={
            "cmd": "request.get",
            "url": f"{mock_server_url}/plain",
            "session": "test-session-req",
            "maxTimeout": 30000,
        },
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "ok"
    ua1 = data1["solution"]["userAgent"]

    resp2 = client.post(
        "/v1",
        json={
            "cmd": "request.get",
            "url": f"{mock_server_url}/plain",
            "session": "test-session-req",
            "maxTimeout": 30000,
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    ua2 = data2["solution"]["userAgent"]

    # Same session should produce the same user agent
    assert ua1 == ua2

    # Clean up
    client.post(
        "/v1",
        json={
            "cmd": "sessions.destroy",
            "session": "test-session-req",
        },
    )
