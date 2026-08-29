FROM python:3.11-slim

WORKDIR /app

# Install the application with the PostgreSQL driver. The cloud deployment must
# not use SQLite: Cloud Run's filesystem is ephemeral and would silently erase
# every investigation on restart. psycopg[binary] needs no build toolchain.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir ".[postgres]"

RUN useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

# PORT is injected by Cloud Run and must be honored; 8000 is the local default.
# DATABASE_URL is deliberately left unset here so a cloud deployment cannot
# inherit a SQLite path by accident - it is supplied per environment.
ENV APP_HOST=0.0.0.0 \
    PORT=8000 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/v1/livez', timeout=2)"

# Shell form so ${PORT} expands at container start. Cloud Run sends concurrent
# requests to one instance, so a single uvicorn worker with the async app is
# the intended shape; horizontal scaling is Cloud Run's job, not uvicorn's.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
