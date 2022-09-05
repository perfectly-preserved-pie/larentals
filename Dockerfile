FROM python:3.10

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY . ./

CMD ["gunicorn", "-b", "0.0.0.0:9208", "--workers=4", "--reload", "app:server"]
