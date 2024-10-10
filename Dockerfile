# Build the dev image to install the requirements
FROM cgr.dev/chainguard/python:latest-dev AS dev

WORKDIR /app

# Copy the requirements file into the working directory
COPY requirements.txt /app/requirements.txt

# Copy uv binary directly from the UV container image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install dependencies using uv
RUN uv pip install --no-cache-dir -r requirements.txt

# Now build the final prod image
FROM cgr.dev/chainguard/python:latest AS prod

WORKDIR /app

# Copy only the necessary application files
COPY . /app

# Set the entrypoint to gunicorn for production
ENTRYPOINT ["gunicorn"]

# Run the app using gunicorn with gevent workers
CMD ["-b", "0.0.0.0:80", "-k", "gevent", "--workers=10", "--preload", "app:server"]