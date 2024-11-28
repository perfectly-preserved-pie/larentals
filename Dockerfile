FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Switch to root user to install dependencies
USER root

# Create the nonroot user and set permissions
RUN adduser --disabled-password --gecos "" nonroot && chown -R nonroot /app

# Copy everything into the working directory
COPY . /app

# Copy uv binary directly from the UV container image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install dependencies directly into the system environment using uv
RUN uv pip install --system --no-cache-dir -r requirements.txt

# Set ownership and permissions in a single step
RUN chown -R nonroot:nonroot /app && chmod -R 755 /app

# Switch back to non-root user
USER nonroot

# Install curl (if needed, uncomment this line)
# RUN apt-get update && apt-get install -y curl

# Run the app using gunicorn.
# Expose the port gunicorn is listening on (80).
# Set the number of workers to 10.
# Preload the app to avoid the overhead of loading the app for each worker.
CMD ["gunicorn", "-b", "0.0.0.0:80", "-k", "gevent", "--workers=10", "--preload", "app:server"]