FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TEMP_DIR=/tmp/discord-video-bot \
    LOG_FILE=/app/logs/bot.log

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/logs /tmp/discord-video-bot \
    && useradd --create-home --shell /usr/sbin/nologin botuser \
    && chown -R botuser:botuser /app /tmp/discord-video-bot

USER botuser

CMD ["python", "main.py"]
