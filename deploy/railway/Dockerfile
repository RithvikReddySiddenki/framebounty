# Hosted demo backend: API + media worker in ONE container.
#
# Why one container: uploads live on local disk (STORAGE_ROOT). The worker must
# read the exact files the API wrote, and Railway volumes attach to a single
# service, so splitting API and worker into two services would break media
# verification. Mount a Railway volume at /data so uploads survive redeploys.
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY services/api/requirements.lock services/api/requirements.lock
RUN pip install --no-cache-dir -r services/api/requirements.lock
COPY services/api services/api
RUN pip install --no-cache-dir --no-deps ./services/api
COPY deploy/railway/start.sh /app/start.sh
RUN chmod +x /app/start.sh
ENV PYTHONUNBUFFERED=1
CMD ["/app/start.sh"]
