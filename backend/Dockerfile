# syntax=docker/dockerfile:1
# Imagem do backend (web + worker, mesmo código; o comando muda no compose).
# Build a partir da RAIZ do repo: docker build -f backend/Dockerfile .

# --- estágio 1: build do frontend ------------------------------------------
FROM node:26-alpine AS frontend-build
# redes com inspeção de SSL (proxy corporativo) podem precisar de
# NPM_CI_ARGS=--strict-ssl=false no build (ver README "Produção em containers")
ARG NPM_CI_ARGS=""
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci $NPM_CI_ARGS
COPY frontend/ ./
RUN npm run build

# --- estágio 2: runtime ------------------------------------------------------
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
# redes com inspeção de SSL podem precisar de
# PIP_EXTRA_ARGS="--trusted-host pypi.org --trusted-host files.pythonhosted.org"
# (o ideal é injetar a CA corporativa; ver README "Produção em containers")
ARG PIP_EXTRA_ARGS=""
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install $PIP_EXTRA_ARGS -r backend/requirements.txt

# backend + migrations (o alembic.ini fica na raiz do repo, então vem junto)
COPY backend/ backend/
COPY alembic.ini alembic.ini

# build do React servido pelo próprio FastAPI (main.py monta ../frontend/dist)
COPY --from=frontend-build /build/dist frontend/dist

EXPOSE 8011
# o serviço `worker` sobrescreve o comando no compose:
#   python -m backend.app.worker
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8011"]
