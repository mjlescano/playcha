FROM python:3.12-slim-bookworm

# System dependencies for Camoufox (Firefox) and Xvfb
RUN apt-get update && apt-get install -y --no-install-recommends \
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
        procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the Camoufox browser binary
RUN python -m camoufox fetch

# Create non-root user and move Camoufox cache to its home
RUN useradd --home-dir /app --shell /bin/sh playcha \
    && mkdir -p /app/.cache \
    && cp -r /root/.cache/camoufox /app/.cache/camoufox \
    && chown -R playcha:playcha /app

# Copy source
COPY src/ src/

ENV PYTHONPATH=/app/src
ENV PORT=8191
ENV HOST=0.0.0.0
ENV LOG_LEVEL=info
ENV HEADLESS=true

USER playcha

EXPOSE 8191

ENTRYPOINT ["/usr/bin/dumb-init", "--"]
CMD ["python", "-m", "playcha"]
