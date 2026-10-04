#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py seed_portfolio
exec gunicorn photo_portfolio.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --timeout 120 --access-logfile - --error-logfile -
