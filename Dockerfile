FROM dhi.io/python:3.13.18-sfw-dev AS builder
COPY --from=dhi.io/uv:0.13-dev /usr/local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY . /app

# JS files and runtime data need to be writable by the non-root user in the runtime image.
RUN mkdir -p /app/data/runtime \
 && touch /app/assets/dashExtensions_default.js \
 && chown 65532:65532 /app/assets \
 && chown 65532:65532 /app/assets/dashExtensions_default.js \
 && chown -R 65532:65532 /app/data \
 && chmod 755 /app/assets \
 && chmod 664 /app/assets/dashExtensions_default.js \
 && chmod 755 /app/data /app/data/runtime

FROM dhi.io/python:3.13.18 AS runtime
WORKDIR /app

# Copy the whole prepared app tree including its permsissions from the builder stage
COPY --from=builder /app /app

# Use the runtime interpreter. Launchers in the copied environment point to
# the builder's Python path, which is absent from the runtime image.
ENV PYTHONPATH="/app/.venv/lib/python3.13/site-packages"
# Override with LOG_LEVEL=DEBUG when per-call diagnostics are needed.
ENV LOG_LEVEL=INFO
ARG SITE_PAGE_LASTMOD={}
ENV SITE_PAGE_LASTMOD=$SITE_PAGE_LASTMOD

ENTRYPOINT ["python3", "-m", "gunicorn"]
CMD ["--config", "/app/gunicorn.conf.py", "--chdir", "/app", "-b", "0.0.0.0:8080", "--worker-class=gthread", "--workers=10", "--threads=8", "--timeout=60", "--keep-alive=5", "--preload", "app:server"]
