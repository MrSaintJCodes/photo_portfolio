#!/bin/sh
set -eu

python manage.py migrate --noinput
python manage.py import_portfolio_photos --source-dir content/photos
exec gunicorn photo_portfolio.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --timeout 120 --access-logfile - --error-logfile -
