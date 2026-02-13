FROM dhi.io/python:3.13-sfw-dev AS builder
COPY --from=dhi.io/uv:0.10-dev /usr/local/bin/uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY . /app

# JS files and the datasets directory need to be writable by the non-root user in the runtime image, so we set permissions here in the builder stage
RUN mkdir -p /app/assets/datasets \
 && touch /app/assets/dashExtensions_default.js \
 && chown 65532:65532 /app/assets \
 && chown 65532:65532 /app/assets/dashExtensions_default.js \
 && chown -R 65532:65532 /app/assets/datasets \
 && chmod 755 /app/assets \
 && chmod 664 /app/assets/dashExtensions_default.js \
 && chmod 755 /app/assets/datasets

FROM dhi.io/python:3.13 AS runtime
WORKDIR /app

# Copy the whole prepared app tree including its permsissions from the builder stage
COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["gunicorn"]
CMD ["--chdir", "/app", "-b", "0.0.0.0:8080", "--workers=10", "--preload", "app:server"]
