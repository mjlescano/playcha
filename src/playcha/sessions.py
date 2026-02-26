from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from camoufox.async_api import AsyncCamoufox
from playwright_captcha.utils.camoufox_add_init_script.add_init_script import (
    get_addon_path,
)

from .config import settings
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


async def launch_browser(
    proxy: ProxyRequest | dict | None = None,
) -> tuple[Any, Any, Any]:
    """Launch a Camoufox browser and return (context_manager, browser, page).

    The caller is responsible for closing via ``context_manager.__aexit__``.
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

    if settings.camoufox_path:
        kwargs["executable_path"] = settings.camoufox_path

    pw_proxy = _build_proxy_arg(proxy)
    if pw_proxy:
        kwargs["proxy"] = pw_proxy

    ctx_mgr = AsyncCamoufox(**kwargs)
    browser = await ctx_mgr.__aenter__()
    context = await browser.new_context()
    page = await context.new_page()
    return ctx_mgr, browser, page


@dataclass
class Session:
    session_id: str
    ctx_mgr: Any
    browser: Any
    page: Any
    created_at: datetime = field(default_factory=datetime.now)

    def lifetime(self) -> timedelta:
        return datetime.now() - self.created_at


class SessionsStorage:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def create(
        self,
        session_id: str | None = None,
        proxy: ProxyRequest | dict | None = None,
    ) -> tuple[Session, bool]:
        session_id = session_id or str(uuid4())

        if session_id in self._sessions:
            return self._sessions[session_id], False

        ctx_mgr, browser, page = await launch_browser(proxy)
        session = Session(
            session_id=session_id,
            ctx_mgr=ctx_mgr,
            browser=browser,
            page=page,
        )
        self._sessions[session_id] = session
        log.info("Session created: %s", session_id)
        return session, True

    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    async def destroy(self, session_id: str) -> bool:
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
