#!/bin/sh
set -e

# Only the web container migrates, so workers never race each other on startup.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
