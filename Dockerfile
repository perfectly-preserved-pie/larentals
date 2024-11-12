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
RUN apt-get update && apt-get install -y curl

# Using uv to install packages because it's fast as fuck boiiii
# https://www.youtube.com/watch?v=6E7ZGCfruaw
# https://ryxcommar.com/2024/02/15/how-to-cut-your-python-docker-builds-in-half-with-uv/
ADD --chmod=655 https://astral.sh/uv/install.sh /install.sh
RUN /install.sh && rm /install.sh
RUN /root/.cargo/bin/uv pip install --system --no-cache -r requirements.txt

COPY . ./

# Run the app using gunicorn.
# Expose the port gunicorn is listening on (80).
# Set the number of workers to 10.
# Preload the app to avoid the overhead of loading the app for each worker. See https://www.joelsleppy.com/blog/gunicorn-application-preloading/
# Set the app to be the server variable in app.py.
CMD ["gunicorn", "-b", "0.0.0.0:80", "-k", "gevent", "--workers=10", "--preload", "app:server"]
