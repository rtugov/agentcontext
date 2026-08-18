FROM python:3.12-slim

LABEL org.opencontainers.image.title="AgentContext" \
      org.opencontainers.image.description="Local audit proxy and context viewer for AI coding agents" \
      org.opencontainers.image.version="0.0.1" \
      org.opencontainers.image.source="https://github.com/rtugov/agentcontext" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LLM_LOG_FILE=/data/requests.jsonl

WORKDIR /app

COPY ac-proxy/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt \
    && addgroup --system --gid 10001 agentcontext \
    && adduser --system --uid 10001 --ingroup agentcontext --no-create-home agentcontext \
    && mkdir /data \
    && chown agentcontext:agentcontext /data

COPY --chown=agentcontext:agentcontext ac-proxy/ac-proxy.py ./ac-proxy.py

USER 10001:10001

EXPOSE 8090
VOLUME ["/data"]

CMD ["python", "-m", "uvicorn", "ac-proxy:app", "--host", "0.0.0.0", "--port", "8090", "--no-access-log"]
