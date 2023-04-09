FROM python:3.11-slim

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY . ./

# Run the app using gunicorn.
# Expose the port gunicorn is listening on (80).
# Set the number of workers to 4.
# Preload the app to avoid the overhead of loading the app for each worker. See https://www.joelsleppy.com/blog/gunicorn-application-preloading/
# Set the app to be the server variable in app.py.
CMD ["gunicorn", "-b", "0.0.0.0:80", "--workers=4", "--preload", "app:server"]