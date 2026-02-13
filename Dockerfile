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

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["gunicorn"]
CMD ["-b", "0.0.0.0:8080", "--workers=10", "--preload", "app:server"]
