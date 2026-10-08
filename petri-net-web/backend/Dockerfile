# stage 1: сборка фронтенда (Vue 3 + Vite, D-042)
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# stage 2: приложение
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY backend/pyproject.toml ./
COPY backend/src ./src
RUN pip install ".[dev]"

COPY backend/tests ./tests
COPY --from=frontend /build/dist ./static
COPY .env.example ./.env.example

EXPOSE 8000
CMD ["uvicorn", "petrinet.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
