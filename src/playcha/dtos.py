from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

STATUS_OK = "ok"
STATUS_ERROR = "error"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class ProxyRequest(BaseModel):
    url: str
    username: str | None = None
    password: str | None = None


class V1Request(BaseModel):
    cmd: str
    url: str | None = None
    postData: str | None = None
    session: str | None = None
    session_ttl_minutes: int | None = None
    maxTimeout: int = 60000
    cookies: list[dict[str, Any]] | None = None
    returnOnlyCookies: bool = False
    returnScreenshot: bool = False
    proxy: ProxyRequest | None = None
    disableMedia: bool = False
    waitInSeconds: int | None = None


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class CookieResponse(BaseModel):
    name: str
    value: str
    domain: str | None = None
    path: str | None = None
    expires: float | None = None
    size: int | None = None
    httpOnly: bool | None = None
    secure: bool | None = None
    session: bool | None = None
    sameSite: str | None = None


class Solution(BaseModel):
    url: str = ""
    status: int = 200
    headers: dict[str, str] | None = None
    response: str | None = None
    cookies: list[CookieResponse] = Field(default_factory=list)
    userAgent: str = ""
    screenshot: str | None = None
    turnstile_token: str | None = None


class V1Response(BaseModel):
    status: str = STATUS_OK
    message: str = ""
    solution: Solution | None = None
    session: str | None = None
    sessions: list[str] | None = None
    startTimestamp: int = 0
    endTimestamp: int = 0
    version: str = ""


class IndexResponse(BaseModel):
    msg: str = ""
    version: str = ""
    userAgent: str = ""


class HealthResponse(BaseModel):
    status: str = STATUS_OK
