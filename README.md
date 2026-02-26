# Playcha

A FlareSolverr-compatible proxy server for bypassing Cloudflare and other browser challenges, built on **Playwright + Camoufox** instead of Selenium + undetected-chromedriver.

Drop-in replacement API — same `POST /v1` interface, same request/response shapes — so migrating from FlareSolverr is a one-line URL change.

> **Warning:** This project is not production ready. It is in an early experimental stage and has not been thoroughly tested against real-world Cloudflare challenges. APIs, configuration, and behavior may change without notice. Use at your own risk.

## Quick Start

### Docker (recommended)

```bash
docker compose up -d
```

Or with the Docker CLI:

```bash
docker run -d \
  --name playcha \
  -p 8191:8191 \
  -e LOG_LEVEL=info \
  --restart unless-stopped \
  playcha
```

Build the image first:

```bash
docker build -t playcha .
```

### From source

Requires Python 3.12+.

```bash
make install          # install dependencies
make fetch-browser    # download the Camoufox browser binary
make dev              # start the server
```

Or without Make:

```bash
pip install -r requirements.txt
python -m camoufox fetch
python -m playcha
```

## Usage

Playcha exposes the same API as FlareSolverr. Point your existing client at Playcha and it will work without code changes.

### Example: GET request

```bash
curl -L -X POST 'http://localhost:8191/v1' \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "cmd": "request.get",
    "url": "https://www.google.com/",
    "maxTimeout": 60000
  }'
```

### Example: POST request

```bash
curl -L -X POST 'http://localhost:8191/v1' \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "cmd": "request.post",
    "url": "https://example.com/login",
    "postData": "username=user&password=pass",
    "maxTimeout": 60000
  }'
```

## API Reference

All commands are sent as JSON to `POST /v1`.

### Commands

| Command | Description |
|---|---|
| `request.get` | Navigate to a URL, solve challenges, return HTML + cookies |
| `request.post` | Same as above but with POST data |
| `sessions.create` | Create a persistent browser session |
| `sessions.list` | List active session IDs |
| `sessions.destroy` | Destroy a session and free resources |

### Request Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `cmd` | string | *required* | The command to execute |
| `url` | string | — | Target URL (required for `request.*`) |
| `postData` | string | — | URL-encoded POST body (required for `request.post`) |
| `session` | string | — | Session ID. Omit for a one-off temporary browser |
| `session_ttl_minutes` | int | — | Auto-rotate sessions older than this |
| `maxTimeout` | int | `60000` | Max time to solve the challenge (ms) |
| `cookies` | list | — | Cookies to set before navigation |
| `returnOnlyCookies` | bool | `false` | Skip returning page HTML |
| `returnScreenshot` | bool | `false` | Return a base64 PNG screenshot |
| `proxy` | object | — | `{"url": "...", "username": "...", "password": "..."}` |
| `disableMedia` | bool | `false` | Block images, CSS, and fonts |
| `waitInSeconds` | int | — | Wait N seconds before capturing the response |

### Response Shape

```json
{
  "status": "ok",
  "message": "Challenge solved!",
  "solution": {
    "url": "https://example.com/",
    "status": 200,
    "headers": {},
    "response": "<!DOCTYPE html>...",
    "cookies": [
      {
        "name": "cf_clearance",
        "value": "...",
        "domain": ".example.com",
        "path": "/",
        "expires": 1700000000,
        "httpOnly": true,
        "secure": true,
        "sameSite": "None"
      }
    ],
    "userAgent": "Mozilla/5.0 ...",
    "screenshot": null,
    "turnstile_token": null
  },
  "startTimestamp": 1700000000000,
  "endTimestamp": 1700000005000,
  "version": "1.0.0"
}
```

### Additional Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Welcome message with version info |
| `/health` | GET | Health check (`{"status": "ok"}`) |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8191` | Listening port |
| `HOST` | `0.0.0.0` | Listening interface |
| `LOG_LEVEL` | `info` | Log verbosity (`debug`, `info`, `warning`, `error`) |
| `HEADLESS` | `true` | Run browser in headless mode |
| `CAMOUFOX_PATH` | *(auto)* | Custom path to Camoufox browser binary |
| `PROXY_URL` | — | Default proxy URL |
| `PROXY_USERNAME` | — | Default proxy username |
| `PROXY_PASSWORD` | — | Default proxy password |
| `CAPTCHA_SOLVER` | `click` | Solver type: `click`, `twocaptcha`, `tencaptcha`, `captchaai` |
| `TWO_CAPTCHA_API_KEY` | — | API key for 2Captcha solver |
| `TEN_CAPTCHA_API_KEY` | — | API key for 10Captcha solver |
| `CAPTCHA_AI_API_KEY` | — | API key for CaptchaAI solver |
| `TZ` | `UTC` | Timezone |

## Embedding as Portable Binaries

Playcha can be compiled into standalone binaries suitable for embedding into other Docker images. This produces two artifacts:

- **`playcha`** — the application binary (PyInstaller bundle)
- **`camoufox/`** — the Camoufox browser files

### Build the binaries

```bash
docker build -f Dockerfile.binary --target builder -t playcha-builder .
```

### Use in your own Dockerfile

```dockerfile
FROM your-base-image

# Install required system libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgtk-3-0 libx11-xcb1 libasound2 libxcomposite1 libxdamage1 \
    libxrandr2 libpango-1.0-0 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 libgbm1 xvfb

# Copy Playcha binaries from the builder
COPY --from=playcha-builder /dist/playcha /usr/local/bin/playcha
COPY --from=playcha-builder /dist/camoufox /opt/camoufox

ENV CAMOUFOX_PATH=/opt/camoufox
```

## Development

```bash
make install-dev      # install package in editable mode with dev deps (ruff, pytest)
make lint             # check for lint errors
make fix              # auto-fix lint errors
make format           # format code
make check            # lint + format check (useful for CI)
```

## Migrating from FlareSolverr

Playcha is a drop-in replacement. To migrate:

1. **Change the URL** — point your client from `http://flaresolverr:8191/v1` to `http://playcha:8191/v1`.
2. **Same JSON body** — all request parameters are identical.
3. **Same response shape** — `status`, `solution`, `cookies`, `userAgent`, timestamps — all in the same format.
4. **Same environment variables** — `PORT`, `LOG_LEVEL`, `PROXY_URL`, etc. work the same way.

No code changes needed beyond updating the endpoint URL.

### Differences

| | FlareSolverr | Playcha |
|---|---|---|
| Browser | Chromium + undetected-chromedriver | Camoufox (stealth Firefox) |
| Automation | Selenium (sync) | Playwright (async) |
| Captcha solving | Tab-based click heuristics | playwright-captcha library |
| API solvers | None built-in | 2Captcha, 10Captcha, CaptchaAI |
| HTTP server | Bottle + Waitress (threads) | FastAPI + Uvicorn (async) |

## Why Camoufox over Selenium + undetected-chromedriver

Playcha uses Camoufox (a stealth Firefox build) with Playwright instead of Selenium + undetected-chromedriver. This choice delivers measurable improvements across several dimensions:

### Communication architecture

FlareSolverr uses Selenium WebDriver, which communicates with Chrome via the ChromeDriver binary over the WebDriver protocol (HTTP JSON Wire). Every browser action — click, navigate, read DOM — is a round-trip HTTP request between three processes: Python, ChromeDriver, and Chrome. Playcha uses Playwright, which communicates with Firefox over a single persistent WebSocket connection. This eliminates per-command HTTP overhead and reduces latency for every operation.

### Memory efficiency

Chromium's multi-process architecture (one process per tab, plus GPU and utility processes) creates a high baseline memory footprint of 150–300 MB per browser instance. Camoufox is a custom Firefox build that uses a more memory-efficient threading model, typically consuming 30–50% less RAM per instance for the same workload. When running multiple sessions, this difference compounds significantly.

### Concurrency model

FlareSolverr's Selenium approach is fundamentally synchronous — it wraps each request in `func_timeout`, blocking an entire OS thread per request. The Bottle/Waitress server handles concurrency via thread pooling, but each thread holds a complete browser instance. Playcha is async end-to-end: FastAPI handles requests on an asyncio event loop, and Playwright's async API manages browser sessions without the overhead of thread synchronization or the memory cost of per-thread stacks. This allows handling more concurrent requests with fewer system resources.

### Anti-detection and solve rates

undetected-chromedriver works by patching the ChromeDriver binary at runtime to remove `navigator.webdriver` flags and other automation indicators. This is inherently a cat-and-mouse game that breaks with each Chrome update. Camoufox takes a fundamentally different approach: it is a custom Firefox build with fingerprint spoofing built directly into the browser engine — canvas rendering, WebGL output, system fonts, screen resolution, timezone, and locale are all spoofed at the engine level. This makes detection significantly harder than patching an automation driver after the fact. Higher solve rates mean fewer retries, which translates directly to faster overall throughput and lower resource consumption.

### Cold start time

FlareSolverr downloads and patches ChromeDriver at runtime (undetected-chromedriver), adding several seconds to the first request or whenever Chrome updates. Camoufox's browser binary is pre-downloaded at build time via `camoufox fetch` and requires no runtime patching. First-request latency is determined only by browser launch time, not by driver setup.

### Image size

Chromium plus ChromeDriver in the FlareSolverr Docker image accounts for roughly 400–500 MB. Camoufox's Firefox build is more compact, and since Playwright communicates directly with the browser (no separate driver binary), the total browser footprint is smaller.

## License

MIT
