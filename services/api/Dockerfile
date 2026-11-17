FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY services/api/requirements.lock /app/services/api/requirements.lock
RUN pip install --no-cache-dir -r services/api/requirements.lock
COPY services/api /app/services/api
RUN pip install --no-cache-dir --no-deps /app/services/api && useradd --create-home --uid 10001 worker && mkdir -p /app/.local/media && chown -R worker:worker /app/.local
USER worker
CMD ["python", "-m", "framebounty.worker"]
