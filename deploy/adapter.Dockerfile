FROM python:3.11-slim

WORKDIR /adapter

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ADAPTER_LOG_PATH=/data/adapter.log

ARG VCS_REF=unknown
LABEL org.opencontainers.image.revision="${VCS_REF}"

COPY openclaw/adapter/adapter.py ./

CMD ["python", "/adapter/adapter.py"]
