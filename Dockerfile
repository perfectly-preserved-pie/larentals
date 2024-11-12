FROM python:3.11-slim

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

# Install curl
#RUN apt-get update && apt-get install -y curl

# Run the app using gunicorn.
# Expose the port gunicorn is listening on (80).
# Set the number of workers to 10.
# Preload the app to avoid the overhead of loading the app for each worker. See https://www.joelsleppy.com/blog/gunicorn-application-preloading/
# Set the app to be the server variable in app.py.
CMD ["gunicorn", "-b", "0.0.0.0:80", "-k", "gevent", "--workers=10", "--preload", "app:server"]
