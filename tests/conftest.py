from __future__ import annotations

import asyncio
import os
import socket
from pathlib import Path

import httpx
import pytest
import uvicorn
from aiohttp import web

MOCK_PAGES = Path(__file__).parent / "mock_pages"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Mock target server
# ---------------------------------------------------------------------------


async def _handle_plain(request: web.Request) -> web.Response:
    html = (MOCK_PAGES / "plain.html").read_text()
    return web.Response(text=html, content_type="text/html")


async def _handle_challenge(request: web.Request) -> web.Response:
    html = (MOCK_PAGES / "challenge.html").read_text()
    return web.Response(text=html, content_type="text/html")


async def _handle_submit(request: web.Request) -> web.Response:
    body = await request.text()
    html = f"""<!DOCTYPE html>
<html><head><title>POST Result</title></head>
<body><pre id="post-data">{body}</pre></body></html>"""
    return web.Response(text=html, content_type="text/html")


async def _handle_set_cookies(request: web.Request) -> web.Response:
    html = (MOCK_PAGES / "plain.html").read_text()
    resp = web.Response(text=html, content_type="text/html")
    resp.set_cookie("test_cookie", "cookie_value", path="/")
    resp.set_cookie("session_id", "abc123", path="/", httponly=True)
    return resp


async def _handle_screenshot_test(request: web.Request) -> web.Response:
    html = """<!DOCTYPE html>
<html><head><title>Screenshot Test</title></head>
<body style="background:#2563eb;color:#fff;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0;">
<h1 id="content">Screenshot OK</h1></body></html>"""
    return web.Response(text=html, content_type="text/html")


@pytest.fixture(scope="session")
def mock_server_url(request):
    """Start an aiohttp mock server on a free port (runs for the whole session)."""
    port = _free_port()
    app = web.Application()
    app.router.add_get("/plain", _handle_plain)
    app.router.add_get("/challenge", _handle_challenge)
    app.router.add_post("/submit", _handle_submit)
    app.router.add_get("/set-cookies", _handle_set_cookies)
    app.router.add_get("/screenshot-test", _handle_screenshot_test)

    loop = asyncio.new_event_loop()

    runner = web.AppRunner(app)
    loop.run_until_complete(runner.setup())
    site = web.TCPSite(runner, "127.0.0.1", port)
    loop.run_until_complete(site.start())

    import threading

    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}"
    yield url

    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5)
    loop.run_until_complete(runner.cleanup())
    loop.close()


# ---------------------------------------------------------------------------
# Playcha server
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def playcha_url():
    """Start the real Playcha FastAPI app on a free port."""
    os.environ["HEADLESS"] = "true"

    port = _free_port()

    from playcha.app import app

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    import threading

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for startup
    import time

    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            httpx.get(f"{url}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.2)
    else:
        raise RuntimeError("Playcha server failed to start")

    yield url

    server.should_exit = True
    thread.join(timeout=10)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def client(playcha_url):
    """Synchronous httpx client pointed at the Playcha server."""
    with httpx.Client(base_url=playcha_url, timeout=120) as c:
        yield c
