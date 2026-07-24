FROM node:22-alpine AS frontend-deps

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund


FROM frontend-deps AS frontend-builder
COPY frontend/ ./
RUN npm run build


FROM frontend-builder AS frontend-check
RUN npm run test \
    && touch /frontend-check-passed


FROM python:3.11-slim AS python-deps

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

COPY requirements.lock ./

RUN pip install --no-cache-dir \
    --index-url "${PIP_INDEX_URL}" \
    --trusted-host "${PIP_TRUSTED_HOST}" \
    --prefix=/python-deps \
    -r requirements.lock


FROM python:3.11-slim AS backend-check

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////tmp/smartcore-test.sqlite \
    AUTH_SECRET_FILE=/tmp/smartcore-test-auth-secret \
    SCHEDULER_ENABLED=false

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

COPY requirements-dev.lock ./
RUN pip install --no-cache-dir \
    --index-url "${PIP_INDEX_URL}" \
    --trusted-host "${PIP_TRUSTED_HOST}" \
    -r requirements-dev.lock

COPY pyproject.toml ./
COPY app/__init__.py ./app/__init__.py
COPY app/server ./app/server
COPY tests ./tests
COPY openclaw ./openclaw

RUN ruff check app/server tests \
    && pytest -q \
    && touch /backend-check-passed


FROM scratch AS verification

COPY --from=backend-check /backend-check-passed /
COPY --from=frontend-check /frontend-check-passed /


FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG VCS_REF=unknown
LABEL org.opencontainers.image.revision="${VCS_REF}"

COPY --from=python-deps /python-deps /usr/local
COPY app/__init__.py ./app/__init__.py
COPY app/server ./app/server
COPY --from=frontend-builder /frontend/dist ./app/server/web/dist

EXPOSE 8000

CMD ["uvicorn", "app.server.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
