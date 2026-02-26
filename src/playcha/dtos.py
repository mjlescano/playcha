from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


STATUS_OK = "ok"
STATUS_ERROR = "error"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class ProxyRequest(BaseModel):
    url: str
    username: Optional[str] = None
    password: Optional[str] = None


class V1Request(BaseModel):
    cmd: str
    url: Optional[str] = None
    postData: Optional[str] = None
    session: Optional[str] = None
    session_ttl_minutes: Optional[int] = None
    maxTimeout: int = 60000
    cookies: Optional[list[dict[str, Any]]] = None
    returnOnlyCookies: bool = False
    returnScreenshot: bool = False
    proxy: Optional[ProxyRequest] = None
    disableMedia: bool = False
    waitInSeconds: Optional[int] = None


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class CookieResponse(BaseModel):
    name: str
    value: str
    domain: Optional[str] = None
    path: Optional[str] = None
    expires: Optional[float] = None
    size: Optional[int] = None
    httpOnly: Optional[bool] = None
    secure: Optional[bool] = None
    session: Optional[bool] = None
    sameSite: Optional[str] = None


class Solution(BaseModel):
    url: str = ""
    status: int = 200
    headers: Optional[dict[str, str]] = None
    response: Optional[str] = None
    cookies: list[CookieResponse] = Field(default_factory=list)
    userAgent: str = ""
    screenshot: Optional[str] = None
    turnstile_token: Optional[str] = None


class V1Response(BaseModel):
    status: str = STATUS_OK
    message: str = ""
    solution: Optional[Solution] = None
    session: Optional[str] = None
    sessions: Optional[list[str]] = None
    startTimestamp: int = 0
    endTimestamp: int = 0
    version: str = ""


class IndexResponse(BaseModel):
    msg: str = ""
    version: str = ""
    userAgent: str = ""


class HealthResponse(BaseModel):
    status: str = STATUS_OK
