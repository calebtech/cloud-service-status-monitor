FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY config ./config

RUN useradd --create-home --uid 1000 monitor \
    && mkdir -p /app/data \
    && chown -R monitor:monitor /app

USER monitor

VOLUME ["/app/data"]

ENTRYPOINT ["python", "-m", "cloud_status_monitor"]
CMD ["--config", "/app/config/config.yaml", "--serve", "--host", "0.0.0.0", "--port", "8080"]
EXPOSE 8080
