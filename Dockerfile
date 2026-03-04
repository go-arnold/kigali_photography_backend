FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN mkdir -p /app/logs

RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpq-dev \
    curl \
    bash \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn

COPY . .

RUN chmod -R 755 /app \
    && find /app -type f -name "*.sh" -exec chmod +x {} \;

RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]