from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Optional

from playwright_captcha import CaptchaType, ClickSolver, FrameworkType

from .config import CaptchaSolverType, settings
from .dtos import (
    STATUS_ERROR,
    STATUS_OK,
    CookieResponse,
    ProxyRequest,
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


async def _wait_challenge_solved(page: Any, timeout_s: float) -> None:
    """Wait until challenge titles/selectors disappear or timeout."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        title = await page.title()
        still_challenging = False
        for t in CHALLENGE_TITLES:
            if title and title.lower() == t.lower():
                still_challenging = True
                break
        if not still_challenging:
            still_challenging = await _elements_exist(page, CHALLENGE_SELECTORS)
        if not still_challenging:
            return
        await asyncio.sleep(1)
    raise Exception(f"Challenge not solved within {timeout_s}s timeout.")


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
        from twocaptcha import AsyncTwoCaptcha
        from playwright_captcha import TwoCaptchaSolver

        if not settings.two_captcha_api_key:
            raise Exception("TWO_CAPTCHA_API_KEY is required for twocaptcha solver.")
        client = AsyncTwoCaptcha(settings.two_captcha_api_key)
        return TwoCaptchaSolver(
            framework=FRAMEWORK, page=page, async_two_captcha_client=client
        )

    if solver_type == CaptchaSolverType.TENCAPTCHA:
        from playwright_captcha.solvers.api.tencaptcha.tencaptcha_solver import (
            TenCaptchaSolver,
        )

        if not settings.ten_captcha_api_key:
            raise Exception("TEN_CAPTCHA_API_KEY is required for tencaptcha solver.")
        # TenCaptcha follows the same client pattern
        try:
            from tencaptcha import AsyncTenCaptcha
        except ImportError:
            raise Exception("Install tencaptcha package for tencaptcha solver.")
        client = AsyncTenCaptcha(settings.ten_captcha_api_key)
        return TenCaptchaSolver(
            framework=FRAMEWORK, page=page, async_ten_captcha_client=client
        )

    if solver_type == CaptchaSolverType.CAPTCHAAI:
        from playwright_captcha.solvers.api.captchaai.captchaai_solver import (
            CaptchaAISolver,
        )

        if not settings.captcha_ai_api_key:
            raise Exception("CAPTCHA_AI_API_KEY is required for captchaai solver.")
        try:
            from captchaai import AsyncCaptchaAI
        except ImportError:
            raise Exception("Install captchaai package for captchaai solver.")
        client = AsyncCaptchaAI(settings.captcha_ai_api_key)
        return CaptchaAISolver(
            framework=FRAMEWORK, page=page, async_captcha_ai_client=client
        )

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

            ttl = (
                timedelta(minutes=req.session_ttl_minutes)
                if req.session_ttl_minutes
                else None
            )
            session, fresh = await sessions.get(
                req.session, ttl=ttl, proxy=req.proxy
            )
            page = session.page
            session_id = session.session_id
            log.debug(
                "Using session %s (fresh=%s, lifetime=%s)",
                session_id,
                fresh,
                session.lifetime(),
            )
        else:
            proxy = req.proxy or settings.default_proxy
            ctx_mgr, _browser, page = await launch_browser(proxy)
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
            has_turnstile = await _detect_turnstile(page)
            captcha_type = _guess_captcha_type(await page.title(), has_turnstile)

            if settings.captcha_solver == CaptchaSolverType.CLICK:
                solver = ClickSolver(framework=FRAMEWORK, page=page)
                async with solver:
                    try:
                        await asyncio.wait_for(
                            solver.solve_captcha(
                                captcha_container=page,
                                captcha_type=captcha_type,
                            ),
                            timeout=timeout_s,
                        )
                    except asyncio.TimeoutError:
                        raise Exception(
                            f"Timeout after {timeout_s}s solving challenge."
                        )
            else:
                api_solver = await _get_api_solver(page)
                if api_solver is None:
                    raise Exception(
                        f"No solver configured for type {settings.captcha_solver}"
                    )
                async with api_solver:
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
                    except asyncio.TimeoutError:
                        raise Exception(
                            f"Timeout after {timeout_s}s solving challenge."
                        )

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
