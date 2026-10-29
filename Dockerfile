FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./

RUN mkdir -p /var/sewasetu/uploads /var/log/sewasetu

EXPOSE 10000
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 4 --timeout 30 app:app"]
