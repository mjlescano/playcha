# =============================================================================
# Stage 1 — Build dummy packages to skip heavy unused dependencies
# =============================================================================
FROM debian:bookworm-slim AS dummies

RUN apt-get update \
    && apt-get install -y --no-install-recommends equivs \
    && equivs-control libgl1-mesa-dri \
    && printf 'Section: misc\nPriority: optional\nStandards-Version: 3.9.2\nPackage: libgl1-mesa-dri\nVersion: 99.0.0\nDescription: dummy\n' >> libgl1-mesa-dri \
    && equivs-build libgl1-mesa-dri \
    && equivs-control adwaita-icon-theme \
    && printf 'Section: misc\nPriority: optional\nStandards-Version: 3.9.2\nPackage: adwaita-icon-theme\nVersion: 99.0.0\nDescription: dummy\n' >> adwaita-icon-theme \
    && equivs-build adwaita-icon-theme

# =============================================================================
# Stage 2 — Build the PyInstaller binary and collect the Camoufox browser
# =============================================================================
FROM python:3.12-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgtk-3-0 \
        libx11-xcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libasound2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libdbus-1-3 \
        libxkbcommon0 \
        libxshmfence1 \
        libgbm1 \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt pyinstaller

# Download the Camoufox browser
RUN python -m camoufox fetch

COPY src/ src/

# Create the PyInstaller entrypoint wrapper
RUN printf 'from playcha.app import main\nmain()\n' > entrypoint.py

# Build the single-directory bundle
RUN PYTHONPATH=src pyinstaller \
        --noconfirm \
        --clean \
        --name playcha \
        --paths src \
        --hidden-import playcha \
        --hidden-import playcha.app \
        --hidden-import playcha.config \
        --hidden-import playcha.dtos \
        --hidden-import playcha.sessions \
        --hidden-import playcha.solver \
        --hidden-import uvicorn \
        --hidden-import uvicorn.logging \
        --hidden-import uvicorn.loops \
        --hidden-import uvicorn.loops.auto \
        --hidden-import uvicorn.protocols \
        --hidden-import uvicorn.protocols.http \
        --hidden-import uvicorn.protocols.http.auto \
        --hidden-import uvicorn.protocols.websockets \
        --hidden-import uvicorn.protocols.websockets.auto \
        --hidden-import uvicorn.lifespan \
        --hidden-import uvicorn.lifespan.on \
        --collect-all playwright_captcha \
        --collect-all camoufox \
        --collect-all browserforge \
        --collect-all apify_fingerprint_datapoints \
        --collect-all language_tags \
        entrypoint.py

RUN mkdir -p /dist && mv dist/playcha /dist/playcha

# Copy the Camoufox browser files
RUN cp -r /root/.cache/camoufox /dist/camoufox


# =============================================================================
# Stage 3 — Minimal runtime image
# =============================================================================
FROM debian:bookworm-slim

ARG VERSION=dev
ARG REVISION=
LABEL org.opencontainers.image.source="https://github.com/mjlescano/playcha" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.revision="$REVISION"

COPY --from=dummies /*.deb /tmp/

RUN dpkg -i /tmp/libgl1-mesa-dri*.deb /tmp/adwaita-icon-theme*.deb \
    && rm /tmp/*.deb \
    && apt-get update && apt-get install -y --no-install-recommends \
        libgtk-3-0 \
        libx11-xcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libasound2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libdbus-1-3 \
        libxkbcommon0 \
        libxshmfence1 \
        libgbm1 \
        xvfb \
        dumb-init \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /dist/playcha /opt/playcha
COPY --from=builder /dist/camoufox /opt/camoufox

RUN useradd --home-dir /opt/playcha --shell /bin/sh playcha \
    && mkdir -p /opt/playcha/.cache \
    && ln -s /opt/camoufox /opt/playcha/.cache/camoufox \
    && chown -R playcha:playcha /opt/playcha

USER playcha

ENV PORT=8191
ENV HOST=0.0.0.0
ENV LOG_LEVEL=info
ENV HEADLESS=true
ENV CAMOUFOX_PATH=/opt/camoufox

EXPOSE 8191

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["/opt/playcha/playcha"]
