# Builder: stable runtime python (hardened, with Socket Firewall)
FROM dhi.io/python:3.13-sfw-dev AS builder

# Copy uv binary in for building only
COPY --from=dhi.io/uv:0.10-dev /usr/local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY . /app

# Runtime: stable runtime python (hardened)
FROM dhi.io/python:3.13 AS runtime
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY . /app

# Datasets and JS assets need to be writable by the non-root user (65532)
RUN mkdir -p /app/assets/datasets \
 && touch /app/assets/dashExtensions_default.js \
 && chown 65532:65532 /app/assets \
 && chown 65532:65532 /app/assets/dashExtensions_default.js \
 && chown -R 65532:65532 /app/assets/datasets \
 && chmod 755 /app/assets \
 && chmod 664 /app/assets/dashExtensions_default.js \
 && chmod 755 /app/assets/datasets \
 && test -f /app/assets/datasets/larentals.db \
 && chown 65532:65532 /app/assets/datasets/larentals.db \
 && chmod 664 /app/assets/datasets/larentals.db

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["gunicorn"]
CMD ["-b", "0.0.0.0:8080", "--workers=10", "--preload", "app:server"]
