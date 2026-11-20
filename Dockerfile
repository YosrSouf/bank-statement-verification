FROM python:3.14-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt gunicorn==27.0.1

COPY app.py ./
COPY code/*.py ./code/
COPY frontend/app.py ./frontend/
COPY frontend/templates/ ./frontend/templates/
COPY frontend/static/ ./frontend/static/

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-10000} --timeout 180 'app:create_app()'"]
