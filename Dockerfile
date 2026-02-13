FROM dhi.io/uv:0.10-dev AS builder

# Force uv to use uv-managed Python (not the image's system Python)
ENV UV_PYTHON_PREFERENCE=only-managed
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python

WORKDIR /app
COPY pyproject.toml uv.lock ./

# Install a stable Python and sync using it
RUN uv python install 3.13
RUN uv sync --frozen --python 3.13

COPY . /app

FROM dhi.io/uv:0.10 AS runtime
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY . /app
ENV PATH="/app/.venv/bin:$PATH"
CMD ["gunicorn", "-b", "0.0.0.0:8080", "--workers=10", "--preload", "app:server"]
