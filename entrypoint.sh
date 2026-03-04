#!/bin/bash

echo "Starting application..."

python manage.py migrate --noinput || true

celery -A config worker --loglevel=info --concurrency=1 &

celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler &

exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers=1 \
    --threads=2 \
    --timeout=300 \
    --access-logfile - \
    --error-logfile -