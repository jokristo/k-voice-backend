# K-Voice API — image production (ffmpeg + Python)
FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY main.py .
COPY scripts ./scripts

RUN chmod +x scripts/render_start.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STORAGE_LOCAL_PATH=/data/storage

EXPOSE 8000

CMD ["scripts/render_start.sh"]
