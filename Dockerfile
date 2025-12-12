ARG TARGETPLATFORM=linux/arm64/v8

FROM --platform=${TARGETPLATFORM} python:3.11-slim

# 1) Prep directory and non-root user
WORKDIR /app
USER root
RUN adduser --disabled-password --gecos "" nonroot \
    && chown -R nonroot /app

# 1.5) Install minimal runtime dependencies needed for TLS/HTTPS downloads and building wheels
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates build-essential python3-dev \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 2) Bring in the uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 3) Copy manifest, lockfile 
COPY pyproject.toml uv.lock /app/

# 4) Copy source files
COPY . /app

# 5) Fix permissions
RUN chown -R nonroot:nonroot /app \
    && chmod -R 755 /app

# 6) Switch to non-root
USER nonroot

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# 7) Use uv at runtime to run the app
CMD ["uv", "run", "--", "gunicorn", "-b", "0.0.0.0:8080", "-k", "gevent", "--workers=10", "--preload", "app:server"]
