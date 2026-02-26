from __future__ import annotations

import logging
import sys
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .config import settings
from .dtos import (
    STATUS_ERROR,
    STATUS_OK,
    HealthResponse,
    IndexResponse,
    ProxyRequest,
    V1Request,
    V1Response,
)
from .sessions import SessionsStorage
from .solver import resolve_challenge

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.sessions = SessionsStorage()
    log.info("Listening on %s:%d", settings.host, settings.port)
    yield
    log.info("Shutting down — destroying all sessions...")
    await app.state.sessions.destroy_all()


app = FastAPI(title="Playcha", version=__version__, lifespan=lifespan)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def index():
    return IndexResponse(
        msg="Playcha is ready!",
        version=__version__,
        userAgent="",
    )


@app.get("/health")
async def health():
    return HealthResponse(status=STATUS_OK)


@app.post("/v1")
async def controller_v1(req: V1Request, request: Request):
    start_ts = int(time.time() * 1000)
    log.info("Incoming request => POST /v1 cmd=%s", req.cmd)

    try:
        res = await _handle_v1(req, request.app.state.sessions)
    except Exception as e:
        log.error("Error handling request: %s", e, exc_info=True)
        res = V1Response(status=STATUS_ERROR, message=f"Error: {e}")

    res.startTimestamp = start_ts
    res.endTimestamp = int(time.time() * 1000)
    res.version = __version__

    elapsed = (res.endTimestamp - res.startTimestamp) / 1000
    log.info("Response in %.2fs (status=%s)", elapsed, res.status)

    status_code = 500 if res.status == STATUS_ERROR else 200
    return JSONResponse(content=res.model_dump(exclude_none=True), status_code=status_code)


# ---------------------------------------------------------------------------
# Command dispatcher
# ---------------------------------------------------------------------------


async def _handle_v1(req: V1Request, sessions: SessionsStorage) -> V1Response:
    if not req.cmd:
        raise Exception("Request parameter 'cmd' is mandatory.")

    if req.proxy is None and settings.default_proxy:
        req.proxy = ProxyRequest(**settings.default_proxy)

    if req.maxTimeout < 1:
        req.maxTimeout = 60000

    if req.cmd == "sessions.create":
        return await _cmd_sessions_create(req, sessions)
    if req.cmd == "sessions.list":
        return await _cmd_sessions_list(sessions)
    if req.cmd == "sessions.destroy":
        return await _cmd_sessions_destroy(req, sessions)
    if req.cmd == "request.get":
        return await _cmd_request_get(req, sessions)
    if req.cmd == "request.post":
        return await _cmd_request_post(req, sessions)

    raise Exception(f"Request parameter 'cmd' = '{req.cmd}' is invalid.")


# ---------------------------------------------------------------------------
# Session commands
# ---------------------------------------------------------------------------


async def _cmd_sessions_create(req: V1Request, sessions: SessionsStorage) -> V1Response:
    session, fresh = await sessions.create(session_id=req.session, proxy=req.proxy)
    return V1Response(
        status=STATUS_OK,
        message="Session created successfully." if fresh else "Session already exists.",
        session=session.session_id,
    )


async def _cmd_sessions_list(sessions: SessionsStorage) -> V1Response:
    return V1Response(
        status=STATUS_OK,
        message="",
        sessions=sessions.session_ids(),
    )


async def _cmd_sessions_destroy(req: V1Request, sessions: SessionsStorage) -> V1Response:
    if not req.session:
        raise Exception("Request parameter 'session' is mandatory for sessions.destroy.")
    existed = await sessions.destroy(req.session)
    if not existed:
        raise Exception("The session doesn't exist.")
    return V1Response(
        status=STATUS_OK,
        message="The session has been removed.",
    )


# ---------------------------------------------------------------------------
# Request commands
# ---------------------------------------------------------------------------


async def _cmd_request_get(req: V1Request, sessions: SessionsStorage) -> V1Response:
    if not req.url:
        raise Exception("Request parameter 'url' is mandatory in 'request.get' command.")
    if req.postData:
        raise Exception("Cannot use 'postData' when sending a GET request.")
    return await resolve_challenge(req, "GET", sessions)


async def _cmd_request_post(req: V1Request, sessions: SessionsStorage) -> V1Response:
    if not req.url:
        raise Exception("Request parameter 'url' is mandatory in 'request.post' command.")
    if not req.postData:
        raise Exception("Request parameter 'postData' is mandatory in 'request.post' command.")
    return await resolve_challenge(req, "POST", sessions)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    log_level = settings.log_level.upper()

    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        level=log_level,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    log.info("Playcha %s", __version__)

    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_config=None,
    )

    server = uvicorn.Server(config)

    config.configure_logging()
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    server.run()


if __name__ == "__main__":
    main()
