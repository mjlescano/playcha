"""Tests for challenge detection and auto-resolution on a mock CF page."""


def test_challenge_detected_and_solved(client, mock_server_url):
    resp = client.post(
        "/v1",
        json={
            "cmd": "request.get",
            "url": f"{mock_server_url}/challenge",
            "maxTimeout": 30000,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "Challenge solved" in data["message"] or "Challenge not detected" in data["message"]

    solution = data["solution"]
    assert solution["status"] == 200
    assert len(solution["userAgent"]) > 0
    # After the challenge auto-resolves, the page should have the solved content
    if "Challenge solved" in data["message"]:
        assert "Challenge passed!" in solution.get("response", "")
