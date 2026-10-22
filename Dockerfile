FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WAREHOUSE_HOST=0.0.0.0 \
    WAREHOUSE_PORT=8000 \
    WAREHOUSE_DB_PATH=/app/data/warehouse.sqlite3 \
    FORWARDED_ALLOW_IPS=*

WORKDIR /app

RUN groupadd --system app \
    && useradd --system --gid app --uid 10001 --create-home app

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY --chown=app:app server ./server
COPY --chown=app:app frontend ./frontend

RUN mkdir -p /app/data && chown -R app:app /app/data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

CMD ["python", "-m", "server"]
