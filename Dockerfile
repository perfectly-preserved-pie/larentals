# Build the dev image to install the requirements
FROM cgr.dev/chainguard/python:latest-dev AS dev

WORKDIR /app

# Switch to root user to install dependencies
USER root

# Copy everything into the working directory
COPY . /app

# Copy uv binary directly from the UV container image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install dependencies directly into the system environment using uv
RUN uv pip install --system --no-cache-dir -r requirements.txt

# Switch back to non-root user
USER nonroot

# Set entrypoint to bash for interactive shell in dev
ENTRYPOINT ["/bin/bash"]

# Now build the final prod image
FROM cgr.dev/chainguard/python:latest AS prod

WORKDIR /app

# Copy the application code from the dev stage
COPY --from=dev /app /app

# Copy the installed Python packages from dev stage
COPY --from=dev /usr/lib/python3.12/site-packages /usr/lib/python3.12/site-packages

# Copy the gunicorn binary from dev stage
COPY --from=dev /usr/bin/gunicorn /usr/bin/gunicorn

# Set the entrypoint to gunicorn for production
ENTRYPOINT ["gunicorn"]

# Run the app using gunicorn with gevent workers
CMD ["-b", "0.0.0.0:80", "-k", "gevent", "--workers=10", "--preload", "app:server"]
