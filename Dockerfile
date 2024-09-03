FROM cgr.dev/chainguard/python:latest-dev

COPY requirements.txt .

# Switch to root user to install packages
USER root

# Install curl
RUN apk update && apk add --no-cache curl

# Using uv to install packages because it's fast as fuck boiiii
# https://www.youtube.com/watch?v=6E7ZGCfruaw
# https://docs.astral.sh/uv/guides/integration/docker/
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
RUN uv pip install --system -r requirements.txt

COPY . ./

# Run the app using gunicorn.
# Expose the port gunicorn is listening on (80).
# Set the number of workers to 10.
# Preload the app to avoid the overhead of loading the app for each worker. See https://www.joelsleppy.com/blog/gunicorn-application-preloading/
# Set the app to be the server variable in app.py.
CMD ["/usr/bin/gunicorn", "-b", "0.0.0.0:80", "-k", "gevent", "--workers=10", "--preload", "app:server"]
