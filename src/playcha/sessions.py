from __future__ import annotations

import asyncio
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .config import BrowserType, settings

if TYPE_CHECKING:
    from .dtos import ProxyRequest

log = logging.getLogger(__name__)


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
    for candidate in ("firefox", "firefox.exe", "camoufox", "camoufox.exe"):
        binary = os.path.join(path, candidate)
        if os.path.isfile(binary):
            return binary
    log.warning("CAMOUFOX_PATH=%s does not contain a recognized browser binary", path)
    return None


# ---------------------------------------------------------------------------
# Camoufox launcher
# ---------------------------------------------------------------------------


async def _launch_camoufox(
    proxy: ProxyRequest | dict | None = None,
) -> tuple[Any, Any, Any]:
    """Launch a Camoufox browser and return (context_manager, context, page)."""
    try:
        from camoufox.async_api import AsyncCamoufox
    except ImportError as err:
        raise RuntimeError(
            "Camoufox is not installed. Install it with: pip install playcha[camoufox]"
        ) from err

    try:
        from playwright_captcha.utils.camoufox_add_init_script.add_init_script import (
            get_addon_path,
        )

        addon_path = os.path.abspath(get_addon_path())
    except Exception:
        addon_path = None

    headless: bool | str = settings.headless
    if headless and sys.platform == "linux":
        headless = "virtual"

    kwargs: dict[str, Any] = {
        "headless": headless,
        "humanize": True,
        "main_world_eval": True,
        "disable_coop": True,
        "i_know_what_im_doing": True,
        "config": {"forceScopeAccess": True},
    }

    if addon_path:
        kwargs["addons"] = [addon_path]

    exe_path = _resolve_camoufox_path()
    if exe_path:
        kwargs["executable_path"] = exe_path

    pw_proxy = _build_proxy_arg(proxy)
    if pw_proxy:
        kwargs["proxy"] = pw_proxy

    try:
        from camoufox.locale import geoip_allowed

        geoip_allowed()
        kwargs["geoip"] = True
    except Exception:
        pass

    ctx_mgr = AsyncCamoufox(**kwargs)
    context = await ctx_mgr.__aenter__()
    page = await context.new_page()
    return ctx_mgr, context, page


# ---------------------------------------------------------------------------
# Patchright launcher
# ---------------------------------------------------------------------------


class _PatchrightContextManager:
    """Wraps the Patchright playwright + browser lifecycle for cleanup."""

    def __init__(self, playwright: Any, browser: Any) -> None:
        self._playwright = playwright
        self._browser = browser

    async def __aexit__(self, *args: Any) -> None:
        await self._browser.close()
        await self._playwright.stop()


async def _launch_patchright(
    proxy: ProxyRequest | dict | None = None,
) -> tuple[Any, Any, Any]:
    """Launch a Patchright (Chromium) browser and return (context_manager, context, page).

    Patchright has a known bug where ``page.add_init_script`` breaks DNS
    resolution.  We work around this by monkey-patching the method to
    collect scripts, then exposing them on ``page._patchright_init_scripts``
    so they can be injected via ``page.evaluate`` after each navigation.
    See :func:`inject_patchright_init_scripts`.
    """
    try:
        from patchright.async_api import async_playwright
    except ImportError as err:
        raise RuntimeError(
            "Patchright is not installed. Install it with: pip install playcha[patchright]"
        ) from err

    pw = await async_playwright().start()

    launch_kwargs: dict[str, Any] = {
        "headless": settings.headless,
    }

    pw_proxy = _build_proxy_arg(proxy)
    if pw_proxy:
        launch_kwargs["proxy"] = pw_proxy

    browser = await pw.chromium.launch(**launch_kwargs)
    context = await browser.new_context()
    page = await context.new_page()

    _init_scripts: list[str] = []

    async def _fake_add_init_script(script: str, **_kwargs: Any) -> None:
        _init_scripts.append(script)

    page.add_init_script = _fake_add_init_script  # type: ignore[assignment]
    page._patchright_init_scripts = _init_scripts  # type: ignore[attr-defined]

    ctx_mgr = _PatchrightContextManager(pw, browser)
    return ctx_mgr, context, page


async def inject_patchright_init_scripts(page: Any) -> None:
    """Inject deferred init scripts collected by the Patchright workaround.

    Must be called after every ``page.goto`` / ``page.reload`` when using the
    Patchright backend so that ``unlockShadowRoot.js`` (and any other init
    scripts added by the solver) take effect.
    """
    scripts: list[str] | None = getattr(page, "_patchright_init_scripts", None)
    if not scripts:
        return
    for script in scripts:
        await page.evaluate(script)


# ---------------------------------------------------------------------------
# Public launcher (dispatches based on settings.browser)
# ---------------------------------------------------------------------------


async def launch_browser(
    proxy: ProxyRequest | dict | None = None,
) -> tuple[Any, Any, Any]:
    """Launch a browser and return (context_manager, context, page).

    The caller is responsible for closing via ``context_manager.__aexit__``.
    The browser backend is selected by the ``BROWSER`` setting.
    """
    if settings.browser == BrowserType.PATCHRIGHT:
        return await _launch_patchright(proxy)
    return await _launch_camoufox(proxy)


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
