FROM python:3.11-slim

# 1) Prep directory and non-root user
WORKDIR /app
USER root
RUN adduser --disabled-password --gecos "" nonroot \
    && chown -R nonroot /app

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

# 7) Use uv run to lock, sync, then invoke Gunicorn
#    Note the “--” to separate uv flags from the Gunicorn command
CMD ["uv", "run", "--", "gunicorn", "-b", "0.0.0.0:8080", "-k", "gevent", "--workers=10", "--preload", "app:server"]
