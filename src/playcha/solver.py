from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

from playwright_captcha import CaptchaType, ClickSolver, FrameworkType

from .config import CaptchaSolverType, settings
from .dtos import (
    STATUS_OK,
    CookieResponse,
    Solution,
    V1Request,
    V1Response,
)
from .sessions import SessionsStorage, launch_browser

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Challenge detection heuristics (ported from FlareSolverr)
# ---------------------------------------------------------------------------

ACCESS_DENIED_TITLES = [
    "Access denied",
    "Attention Required! | Cloudflare",
]

ACCESS_DENIED_SELECTORS = [
    "div.cf-error-title span.cf-code-label span",
    "#cf-error-details div.cf-error-overview h1",
]

CHALLENGE_TITLES = [
    "Just a moment...",
    "DDoS-Guard",
]

CHALLENGE_SELECTORS = [
    "#cf-challenge-running",
    ".ray_id",
    ".attack-box",
    "#cf-please-wait",
    "#challenge-spinner",
    "#trk_jschal_js",
    "#turnstile-wrapper",
    ".lds-ring",
    "td.info #js_info",
    "div.vc div.text-box h2",
]

TURNSTILE_SELECTORS = [
    "input[name='cf-turnstile-response']",
]

FRAMEWORK = FrameworkType.CAMOUFOX


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _elements_exist(page: Any, selectors: list[str]) -> bool:
    for sel in selectors:
        try:
            els = await page.query_selector_all(sel)
            if els:
                return True
        except Exception:
            pass
    return False


async def _detect_challenge(page: Any) -> bool:
    title = await page.title()
    for t in ACCESS_DENIED_TITLES:
        if title and title.startswith(t):
            raise Exception(
                "Cloudflare has blocked this request. "
                "Probably your IP is banned for this site, check in your web browser."
            )
    if await _elements_exist(page, ACCESS_DENIED_SELECTORS):
        raise Exception(
            "Cloudflare has blocked this request. "
            "Probably your IP is banned for this site, check in your web browser."
        )

    for t in CHALLENGE_TITLES:
        if title and title.lower() == t.lower():
            log.info("Challenge detected. Title: %s", title)
            return True
    if await _elements_exist(page, CHALLENGE_SELECTORS):
        log.info("Challenge detected via selector.")
        return True

    return False


async def _detect_turnstile(page: Any) -> bool:
    return await _elements_exist(page, TURNSTILE_SELECTORS)


async def _challenge_still_present(page: Any) -> bool:
    """Check whether a Cloudflare challenge page is still showing."""
    title = await page.title()
    for t in CHALLENGE_TITLES:
        if title and title.lower() == t.lower():
            return True
    return await _elements_exist(page, CHALLENGE_SELECTORS)


async def _wait_challenge_solved(page: Any, timeout_s: float) -> None:
    """Wait until challenge titles/selectors disappear or timeout."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if not await _challenge_still_present(page):
            return
        await asyncio.sleep(1)
    raise Exception(f"Challenge not solved within {timeout_s}s timeout.")


CF_IFRAME_SELECTOR = 'iframe[src*="challenges.cloudflare.com"]'


async def _wait_for_challenge_ready(page: Any, timeout_s: float) -> bool:
    """Wait for the CF challenge iframe to appear, or for the challenge to auto-solve.

    Returns True if the challenge needs interactive solving (iframe appeared),
    False if the challenge resolved itself (JS-only challenge or timed out without iframe).
    """
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if not await _challenge_still_present(page):
            log.debug("Challenge auto-solved (JS-only challenge).")
            return False
        try:
            iframe = await page.query_selector(CF_IFRAME_SELECTOR)
            if iframe:
                log.debug("CF challenge iframe found in DOM.")
                return True
        except Exception:
            pass
        await asyncio.sleep(1)
    if not await _challenge_still_present(page):
        log.debug("Challenge resolved during wait.")
        return False
    log.debug("No CF iframe appeared within %ds, challenge still present.", timeout_s)
    return False


async def _extract_cookies(page: Any) -> list[CookieResponse]:
    context = page.context
    raw_cookies = await context.cookies()
    result: list[CookieResponse] = []
    for c in raw_cookies:
        result.append(
            CookieResponse(
                name=c.get("name", ""),
                value=c.get("value", ""),
                domain=c.get("domain"),
                path=c.get("path"),
                expires=c.get("expires"),
                httpOnly=c.get("httpOnly"),
                secure=c.get("secure"),
                sameSite=c.get("sameSite"),
            )
        )
    return result


async def _get_user_agent(page: Any) -> str:
    try:
        return await page.evaluate("() => navigator.userAgent")
    except Exception:
        return ""


async def _block_media(page: Any) -> None:
    """Intercept and abort requests for images, CSS, and fonts."""
    blocked = {"image", "stylesheet", "font"}

    async def handler(route: Any) -> None:
        if route.request.resource_type in blocked:
            await route.abort()
        else:
            await route.continue_()

    await page.route("**/*", handler)


async def _get_api_solver(page: Any) -> Any:
    """Build an API-based solver if configured."""
    solver_type = settings.captcha_solver

    if solver_type == CaptchaSolverType.TWOCAPTCHA:
        from playwright_captcha import TwoCaptchaSolver
        from twocaptcha import AsyncTwoCaptcha

        if not settings.two_captcha_api_key:
            raise Exception("TWO_CAPTCHA_API_KEY is required for twocaptcha solver.")
        client = AsyncTwoCaptcha(settings.two_captcha_api_key)
        return TwoCaptchaSolver(framework=FRAMEWORK, page=page, async_two_captcha_client=client)

    if solver_type == CaptchaSolverType.TENCAPTCHA:
        if not settings.ten_captcha_api_key:
            raise Exception("TEN_CAPTCHA_API_KEY is required for tencaptcha solver.")
        try:
            from playwright_captcha.solvers.api.tencaptcha.tencaptcha_solver import (  # type: ignore[import-not-found]
                TenCaptchaSolver,
            )
            from tencaptcha import AsyncTenCaptcha  # type: ignore[import-not-found]
        except ImportError as err:
            raise Exception("Install tencaptcha package for tencaptcha solver.") from err
        client = AsyncTenCaptcha(settings.ten_captcha_api_key)
        return TenCaptchaSolver(framework=FRAMEWORK, page=page, async_ten_captcha_client=client)

    if solver_type == CaptchaSolverType.CAPTCHAAI:
        if not settings.captcha_ai_api_key:
            raise Exception("CAPTCHA_AI_API_KEY is required for captchaai solver.")
        try:
            from captchaai import AsyncCaptchaAI  # type: ignore[import-not-found]
            from playwright_captcha.solvers.api.captchaai.captchaai_solver import (  # type: ignore[import-not-found]
                CaptchaAISolver,
            )
        except ImportError as err:
            raise Exception("Install captchaai package for captchaai solver.") from err
        client = AsyncCaptchaAI(settings.captcha_ai_api_key)
        return CaptchaAISolver(framework=FRAMEWORK, page=page, async_captcha_ai_client=client)

    return None


def _guess_captcha_type(page_title: str, has_turnstile: bool) -> CaptchaType:
    """Best-effort guess of captcha type from page signals."""
    title_lower = (page_title or "").lower()
    if "just a moment" in title_lower or has_turnstile:
        if has_turnstile:
            return CaptchaType.CLOUDFLARE_TURNSTILE
        return CaptchaType.CLOUDFLARE_INTERSTITIAL
    return CaptchaType.CLOUDFLARE_INTERSTITIAL


# ---------------------------------------------------------------------------
# Core resolution
# ---------------------------------------------------------------------------


async def _solve_challenge(page: Any, timeout_s: float) -> str | None:
    """Handle a detected Cloudflare challenge.

    Waits for a Turnstile iframe to appear (interactive challenge) or for
    the challenge to auto-solve (JS-only challenge).  When an iframe is
    found, the configured solver is used.  JS-only challenges are given the
    full timeout to resolve on their own.

    Returns a turnstile token string if one was captured, else None.
    """
    turnstile_token: str | None = None
    iframe_wait = min(timeout_s / 2, 15)

    needs_solver = await _wait_for_challenge_ready(page, iframe_wait)
    if not needs_solver:
        return None

    has_turnstile = await _detect_turnstile(page)
    captcha_type = _guess_captcha_type(await page.title(), has_turnstile)

    if settings.captcha_solver == CaptchaSolverType.CLICK:
        solver = ClickSolver(
            framework=FRAMEWORK, page=page, max_attempts=5, attempt_delay=8,
        )
        async with solver:
            # Reload so the init scripts (unlockShadowRoot etc.) run
            # before the Cloudflare challenge JS executes.
            log.debug("Reloading page so init scripts run before CF challenge JS...")
            await page.reload(wait_until="domcontentloaded")

            # After reload, wait again for the iframe or auto-solve
            needs_solver = await _wait_for_challenge_ready(page, iframe_wait)
            if needs_solver:
                try:
                    await asyncio.wait_for(
                        solver.solve_captcha(
                            captcha_container=page,
                            captcha_type=captcha_type,
                        ),
                        timeout=timeout_s,
                    )
                except TimeoutError as err:
                    raise Exception(
                        f"Timeout after {timeout_s}s solving challenge."
                    ) from err
    else:
        api_solver = await _get_api_solver(page)
        if api_solver is None:
            raise Exception(f"No solver configured for type {settings.captcha_solver}")
        async with api_solver:
            log.debug("Reloading page so init scripts run before CF challenge JS...")
            await page.reload(wait_until="domcontentloaded")

            needs_solver = await _wait_for_challenge_ready(page, iframe_wait)
            if needs_solver:
                try:
                    result = await asyncio.wait_for(
                        api_solver.solve_captcha(
                            captcha_container=page,
                            captcha_type=captcha_type,
                        ),
                        timeout=timeout_s,
                    )
                    if isinstance(result, str):
                        turnstile_token = result
                except TimeoutError as err:
                    raise Exception(
                        f"Timeout after {timeout_s}s solving challenge."
                    ) from err

    return turnstile_token


async def resolve_challenge(
    req: V1Request,
    method: str,
    sessions: SessionsStorage,
) -> V1Response:
    timeout_s = max(req.maxTimeout / 1000, 5)

    ctx_mgr = None
    page = None
    session_id: str | None = None
    try:
        if req.session:
            from datetime import timedelta

            ttl = timedelta(minutes=req.session_ttl_minutes) if req.session_ttl_minutes else None
            session, fresh = await sessions.get(req.session, ttl=ttl, proxy=req.proxy)
            page = session.page
            session_id = session.session_id
            log.debug(
                "Using session %s (fresh=%s, lifetime=%s)",
                session_id,
                fresh,
                session.lifetime(),
            )
        else:
            ctx_mgr, _context, page = await launch_browser(req.proxy)
            log.debug("Temporary browser launched for request.")

        if req.disableMedia:
            await _block_media(page)

        # Navigate
        if method == "POST" and req.postData:
            await _navigate_post(page, req.url, req.postData)
        else:
            await page.goto(req.url, wait_until="domcontentloaded")

        # Apply cookies if provided, then reload
        if req.cookies:
            for cookie in req.cookies:
                await page.context.add_cookies([cookie])
            if method == "POST" and req.postData:
                await _navigate_post(page, req.url, req.postData)
            else:
                await page.goto(req.url, wait_until="domcontentloaded")

        # Detect and solve challenge
        challenge_found = await _detect_challenge(page)
        turnstile_token: str | None = None

        if challenge_found:
            turnstile_token = await _solve_challenge(page, timeout_s)

            # Wait for challenge artifacts to disappear
            try:
                await _wait_challenge_solved(page, min(timeout_s, 15))
            except Exception:
                log.warning("Challenge selectors did not fully clear.")

            log.info("Challenge solved!")
            message = "Challenge solved!"
        else:
            log.info("Challenge not detected!")
            message = "Challenge not detected!"

        # Gather the response
        if turnstile_token is None and await _detect_turnstile(page):
            try:
                el = await page.query_selector(TURNSTILE_SELECTORS[0])
                if el:
                    turnstile_token = await el.get_attribute("value")
            except Exception:
                pass

        solution = Solution(
            url=page.url,
            status=200,
            cookies=await _extract_cookies(page),
            userAgent=await _get_user_agent(page),
            turnstile_token=turnstile_token,
        )

        if not req.returnOnlyCookies:
            solution.headers = {}

            if req.waitInSeconds and req.waitInSeconds > 0:
                log.info("Waiting %ds before capturing response...", req.waitInSeconds)
                await asyncio.sleep(req.waitInSeconds)

            solution.response = await page.content()

        if req.returnScreenshot:
            raw = await page.screenshot(type="png")
            solution.screenshot = base64.b64encode(raw).decode()

        return V1Response(status=STATUS_OK, message=message, solution=solution)

    finally:
        if ctx_mgr is not None:
            try:
                await ctx_mgr.__aexit__(None, None, None)
            except Exception:
                log.warning("Error closing temporary browser", exc_info=True)


async def _navigate_post(page: Any, url: str, post_data: str) -> None:
    """Navigate to a URL via POST using Playwright route interception."""

    async def intercept(route: Any) -> None:
        await route.continue_(
            method="POST",
            post_data=post_data,
            headers={
                **route.request.headers,
                "content-type": "application/x-www-form-urlencoded",
            },
        )

    await page.route(url, intercept)
    await page.goto(url, wait_until="domcontentloaded")
    await page.unroute(url, intercept)
