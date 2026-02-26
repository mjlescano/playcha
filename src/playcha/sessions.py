from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from camoufox.async_api import AsyncCamoufox
from playwright_captcha.utils.camoufox_add_init_script.add_init_script import (
    get_addon_path,
)

from .config import settings

if TYPE_CHECKING:
    from .dtos import ProxyRequest

log = logging.getLogger(__name__)

ADDON_PATH = get_addon_path()


def _build_proxy_arg(proxy: ProxyRequest | dict | None) -> dict[str, Any] | None:
    """Convert a proxy request into the format Playwright expects."""
    if proxy is None:
        return None
    if isinstance(proxy, dict):
        url = proxy.get("url")
        username = proxy.get("username")
        password = proxy.get("password")
    else:
        url = proxy.url
        username = proxy.username
        password = proxy.password
    if not url:
        return None
    pw_proxy: dict[str, Any] = {"server": url}
    if username:
        pw_proxy["username"] = username
    if password:
        pw_proxy["password"] = password
    return pw_proxy


def _resolve_camoufox_path() -> str | None:
    """Resolve the Camoufox executable path from CAMOUFOX_PATH.

    Accepts either a direct path to the binary or a directory containing it.
    Returns the binary path, or None to let Camoufox auto-detect.
    """
    path = settings.camoufox_path
    if not path:
        return None
    if os.path.isfile(path):
        return path
    # If it's a directory, look for the binary inside it
    for candidate in ("firefox", "firefox.exe", "camoufox", "camoufox.exe"):
        binary = os.path.join(path, candidate)
        if os.path.isfile(binary):
            return binary
    log.warning("CAMOUFOX_PATH=%s does not contain a recognized browser binary", path)
    return None


async def launch_browser(
    proxy: ProxyRequest | dict | None = None,
) -> tuple[Any, Any, Any]:
    """Launch a Camoufox browser and return (context_manager, context, page).

    The caller is responsible for closing via ``context_manager.__aexit__``.
    ``AsyncCamoufox.__aenter__`` returns a ``BrowserContext`` with stealth
    settings already applied, so we use it directly instead of creating a
    second context.
    """
    headless: bool | str = settings.headless
    if headless and os.name != "nt":
        headless = "virtual"

    kwargs: dict[str, Any] = {
        "headless": headless,
        "humanize": True,
        "main_world_eval": True,
        "addons": [os.path.abspath(ADDON_PATH)],
    }

    exe_path = _resolve_camoufox_path()
    if exe_path:
        kwargs["executable_path"] = exe_path

    pw_proxy = _build_proxy_arg(proxy)
    if pw_proxy:
        kwargs["proxy"] = pw_proxy

    ctx_mgr = AsyncCamoufox(**kwargs)
    context = await ctx_mgr.__aenter__()
    page = await context.new_page()
    return ctx_mgr, context, page


@dataclass
class Session:
    session_id: str
    ctx_mgr: Any
    context: Any
    page: Any
    created_at: datetime = field(default_factory=datetime.now)

    def lifetime(self) -> timedelta:
        return datetime.now() - self.created_at


class SessionsStorage:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        session_id: str | None = None,
        proxy: ProxyRequest | dict | None = None,
    ) -> tuple[Session, bool]:
        session_id = session_id or str(uuid4())

        async with self._lock:
            if session_id in self._sessions:
                return self._sessions[session_id], False

            ctx_mgr, context, page = await launch_browser(proxy)
            session = Session(
                session_id=session_id,
                ctx_mgr=ctx_mgr,
                context=context,
                page=page,
            )
            self._sessions[session_id] = session
            log.info("Session created: %s", session_id)
            return session, True

    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    async def destroy(self, session_id: str) -> bool:
        async with self._lock:
            if session_id not in self._sessions:
                return False
            session = self._sessions.pop(session_id)
        try:
            await session.ctx_mgr.__aexit__(None, None, None)
        except Exception:
            log.warning("Error closing session %s", session_id, exc_info=True)
        log.info("Session destroyed: %s", session_id)
        return True

    async def get(
        self,
        session_id: str,
        ttl: timedelta | None = None,
        proxy: ProxyRequest | dict | None = None,
    ) -> tuple[Session, bool]:
        session, fresh = await self.create(session_id, proxy)

        if ttl is not None and not fresh and session.lifetime() > ttl:
            log.debug("Session %s expired (ttl=%s), recreating", session_id, ttl)
            await self.destroy(session_id)
            session, fresh = await self.create(session_id, proxy)

        return session, fresh

    def session_ids(self) -> list[str]:
        return list(self._sessions.keys())

    async def destroy_all(self) -> None:
        for sid in list(self._sessions.keys()):
            await self.destroy(sid)
