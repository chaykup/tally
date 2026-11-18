# Built from the repo root by docker compose (the build context needs shared/).
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements-dev.txt /tmp/requirements-dev.txt
COPY services/auth/requirements.txt /tmp/requirements.txt
COPY shared /shared
RUN pip install --no-cache-dir -r /tmp/requirements.txt -r /tmp/requirements-dev.txt -e /shared

COPY services/auth /app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
