# Hosted API + verification worker + explicitly enabled chain worker.
# Supabase holds private media; /data preserves the mainnet operator gas ledger.
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tini && rm -rf /var/lib/apt/lists/*
COPY services/api/requirements.lock services/api/requirements.lock
RUN pip install --no-cache-dir -r services/api/requirements.lock
COPY services/api services/api
RUN pip install --no-cache-dir --no-deps ./services/api
COPY deploy/railway/start.sh /app/start.sh
RUN chmod +x /app/start.sh
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/start.sh"]
