FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 medipos

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN DJANGO_ALLOW_INSECURE_KEY=1 DATABASE_URL=sqlite:////tmp/build.sqlite3 python manage.py collectstatic --noinput \
    && mkdir -p /app/media && chown -R medipos:medipos /app
USER medipos

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 CMD curl -fsS http://127.0.0.1:8000/api/health/ || exit 1
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
