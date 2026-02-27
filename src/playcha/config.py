from __future__ import annotations

import os
from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings


class BrowserType(StrEnum):
    CAMOUFOX = "camoufox"
    PATCHRIGHT = "patchright"


class CaptchaSolverType(StrEnum):
    CLICK = "click"
    TWOCAPTCHA = "twocaptcha"
    TENCAPTCHA = "tencaptcha"
    CAPTCHAAI = "captchaai"


class Settings(BaseSettings):
    port: int = Field(default=8191)
    host: str = Field(default="0.0.0.0")
    log_level: str = Field(default="info")

    browser: BrowserType = Field(default=BrowserType.CAMOUFOX)
    headless: bool = Field(default=True)
    camoufox_path: str | None = Field(default=None)

    proxy_url: str | None = Field(default=None)
    proxy_username: str | None = Field(default=None)
    proxy_password: str | None = Field(default=None)

    captcha_solver: CaptchaSolverType = Field(default=CaptchaSolverType.CLICK)
    two_captcha_api_key: str | None = Field(default=None)
    ten_captcha_api_key: str | None = Field(default=None)
    captcha_ai_api_key: str | None = Field(default=None)

    tz: str = Field(default="UTC")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def default_proxy(self) -> dict | None:
        if not self.proxy_url:
            return None
        proxy: dict = {"url": self.proxy_url}
        if self.proxy_username:
            proxy["username"] = self.proxy_username
        if self.proxy_password:
            proxy["password"] = self.proxy_password
        return proxy


def get_settings() -> Settings:
    return Settings()


settings = get_settings()

if settings.tz:
    os.environ.setdefault("TZ", settings.tz)
