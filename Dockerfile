# Build the dev image to install the requirements
FROM cgr.dev/chainguard/python:latest-dev AS dev

WORKDIR /app

# Copy the requirements file into the working directory
COPY requirements.txt /app/requirements.txt

# Copy uv binary directly from the UV container image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Create virtual environment and install dependencies using uv
RUN python -m venv venv \
    && source venv/bin/activate \
    && uv pip install --no-cache-dir -r requirements.txt

# Set entrypoint to bash for interactive shell in dev
ENTRYPOINT ["/bin/bash"]

# Now build the final prod image
FROM cgr.dev/chainguard/python:latest AS prod

WORKDIR /app

# Copy the virtual environment from the dev stage
COPY --from=dev /app/venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Copy the rest of the app
COPY . /app

# Set the entrypoint to gunicorn for production
ENTRYPOINT ["gunicorn"]

# Run the app using gunicorn with gevent workers
CMD ["-b", "0.0.0.0:80", "-k", "gevent", "--workers=10", "--preload", "app:server"]
