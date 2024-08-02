FROM cgr.dev/chainguard/python:latest-dev

COPY requirements.txt .

# Run as root to install curl
USER root

# Install curl
RUN apk update && apk add curl

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
